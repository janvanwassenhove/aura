"""U205: the co-presenter runner — drives a Scenario's beats live.

The runner is deliberately thin and dependency-injected, so the beat logic can
be tested with fakes and the messy parts (real robot speech, the LLM, the event
bus, PowerPoint) stay outside it.

Three inputs fire beats:
  - next()        the presenter advances by hand      → the next `manual` beat
  - on_slide(n)   a slide became active (PowerPoint)   → beats triggered `slide:n`
  - on_speech(t)  the presenter said something         → armed `keyword:` beats

Each beat runs by its mode:
  - speak      say `text` verbatim (+ optional gesture)
  - improvise  ask the generator for a fresh line about `topic`, then say it
  - chime_in   an armed improvise: only fires from a keyword, at most once
  - silent     do nothing — hand the floor back to the presenter
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from shared_schemas.presentation.models import Beat, Scenario

logger = logging.getLogger(__name__)

# generate(topic, guardrails, engine) -> spoken line
Generator = Callable[[str, str, str], Awaitable[str]]


class ScenarioRunner:
    def __init__(
        self,
        scenario: Scenario,
        *,
        speak: Callable[[str], Awaitable[Any]],
        generate: Generator,
        gesture: Callable[[str], Awaitable[Any]] | None = None,
        on_event: Callable[[dict], Awaitable[Any]] | None = None,
    ) -> None:
        self._scenario = scenario
        self._speak = speak
        self._generate = generate
        self._gesture = gesture
        self._on_event = on_event

        self._manual_order = [b for b in scenario.beats if b.trigger_kind == "manual"]
        self._manual_pos = 0
        self._current_slide: int | None = None
        self._fired: set[str] = set()      # beat ids that have run (once-guard)
        # U267: rehearsal — walk the whole show with the robot MUTE.
        #
        # The console has had a "Rehearse" button since D2, and it promised
        # "beats fire, but nothing is sent". Nothing of the sort existed here:
        # the flag lived in the browser, changed a label, and the robot spoke
        # every line out loud anyway. Asked as "not clear what rehearsal is
        # doing" — because it was doing nothing.
        #
        # Beats still fire, still emit, still generate their improvised lines
        # (the line is the thing you most want to read beforehand). Only the
        # two outputs that reach the room — voice and motion — are held back.
        self.rehearsing = False
        # U269: why the last line was not heard, if it was not. Empty means
        # the last thing he tried to say actually left the speaker.
        self.last_speech_error = ""

    # -- state ---------------------------------------------------------

    @property
    def title(self) -> str:
        return self._scenario.title

    @property
    def current_slide(self) -> int | None:
        return self._current_slide

    def status(self) -> dict:
        return {
            "title": self._scenario.title,
            "pptx": self._scenario.pptx,
            "current_slide": self._current_slide,
            "manual_pos": self._manual_pos,
            "manual_total": len(self._manual_order),
            # U267: the console counted "beat N of M" from manual_pos/manual_total,
            # which only ever described the HAND-ADVANCED beats. One manual beat
            # in a scenario, fire it, and the HUD read "beat 2 of 1". The whole
            # show's size and how much of it has run are separate facts, so they
            # are separate fields now.
            "beats_total": len(self._scenario.beats),
            "rehearsing": self.rehearsing,
            "speech_error": self.last_speech_error,
            "fired": sorted(self._fired),
            "armed_keywords": [
                b.trigger_value for b in self._scenario.beats
                if b.trigger_kind == "keyword" and b.id not in self._fired
            ],
        }

    # -- triggers ------------------------------------------------------

    async def next(self) -> Beat | None:
        """Fire the next hand-advanced beat, or None when they're exhausted."""
        while self._manual_pos < len(self._manual_order):
            beat = self._manual_order[self._manual_pos]
            self._manual_pos += 1
            if beat.id not in self._fired:
                await self._fire(beat)
                return beat
        return None

    async def on_slide(self, slide_number: int) -> list[Beat]:
        """A slide became active — fire any beats bound to it."""
        self._current_slide = slide_number
        fired: list[Beat] = []
        for beat in self._scenario.beats:
            if beat.slide_number == slide_number and beat.id not in self._fired:
                await self._fire(beat)
                fired.append(beat)
        return fired

    async def on_speech(self, text: str) -> list[Beat]:
        """The presenter spoke — fire armed keyword beats whose word appears.

        Case-insensitive substring match. `once` beats never fire twice, so a
        topic mentioned repeatedly gets at most one remark from the robot.
        """
        low = (text or "").lower()
        fired: list[Beat] = []
        for beat in self._scenario.beats:
            if beat.trigger_kind != "keyword":
                continue
            if beat.once and beat.id in self._fired:
                continue
            if beat.trigger_value.lower() in low:
                await self._fire(beat)
                fired.append(beat)
        return fired

    # -- execution -----------------------------------------------------

    async def _fire(self, beat: Beat) -> None:
        self._fired.add(beat.id)
        logger.info("beat %r fired (mode=%s trigger=%s)", beat.id, beat.mode, beat.trigger)
        await self._emit({"type": "beat_started", "beat": beat.id, "mode": beat.mode})

        spoken = ""
        if beat.mode == "silent":
            pass
        elif beat.mode == "speak":
            spoken = beat.text
            await self._say(beat.id, beat.text)
        else:  # improvise or chime_in
            try:
                spoken = (await self._generate(beat.topic, beat.guardrails, beat.engine)) or ""
            except Exception as exc:  # noqa: BLE001 — a dead beat must not kill the talk
                logger.warning("beat %r generation failed: %s", beat.id, exc)
                spoken = ""
            if spoken:
                await self._say(beat.id, spoken)

        if beat.gesture and self._gesture is not None and beat.mode != "silent" \
                and not self.rehearsing:
            try:
                await self._gesture(beat.gesture)
            except Exception as exc:  # noqa: BLE001
                logger.debug("gesture %r failed: %s", beat.gesture, exc)

        await self._emit({"type": "beat_done", "beat": beat.id, "spoken": spoken})

    async def _say(self, beat_id: str, text: str) -> None:
        """Speak a line — unless this is a rehearsal, when the room hears nothing.

        U265: NEVER let a failed speaker eat beat_done. The subtitle event is
        derived from beat_done, and subtitles are exactly what saves the talk
        when the robot's audio fails — losing them at that moment is losing
        both channels at once. Found live: a beat showed as fired while no
        PresentationBeatFired ever went out.
        """
        if self.rehearsing:
            return
        try:
            await self._speak(text)
            self.last_speech_error = ""
        except Exception as exc:  # noqa: BLE001 — the show must go on
            logger.warning("beat %r speech failed: %s", beat_id, exc)
            # U269: going on is right; going on SILENTLY is not. The console
            # said "all beats done" while the room heard nothing, and nothing
            # anywhere said why. The reason now rides along in the status.
            self.last_speech_error = str(exc) or exc.__class__.__name__

    async def _emit(self, event: dict) -> None:
        if self._on_event is not None:
            try:
                await self._on_event(event)
            except Exception as exc:  # noqa: BLE001
                logger.debug("scenario event sink failed: %s", exc)
