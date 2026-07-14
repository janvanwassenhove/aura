"""Hands-free voice loop (U47): wake-word start + follow-up conversation.

Runs continuously on the robot's microphone. Behaviour is driven by env so the
Settings panel can change it live:

  VOICE_MODE = off | wake_word      (off → the loop idles; use the mic button)
  WAKE_WORD  = the word that starts a conversation (default: the assistant name)

Flow:
  1. Capture a short window from the robot mic. If it's near-silence (raw peak
     below a threshold) skip it — no transcription cost.
  2. Otherwise transcribe. If we're inside a FOLLOW-UP window (just after the
     robot spoke) the speech is taken as a reply — no wake word needed, so you
     can just answer. Outside that window the wake word must appear; the command
     is whatever follows it (or the next utterance if the wake word was alone).
  3. Run the pipeline turn; the reply is spoken on the robot (embodiment). Each
     spoken reply — including a recognition greeting — opens a fresh follow-up
     window, so a greeting naturally turns into a conversation.

Echo guard: while the robot is speaking its own reply, the loop waits (estimated
from the reply length) so it doesn't transcribe its own voice.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Whisper hallucinates set phrases from silence/noise. Reject these outright.
_HALLUCINATIONS = {
    "you", "thank you", "thank you.", "thanks", "thanks for watching",
    "thanks for watching!", "bye", "bye.", "okay", "ok", ".", "..", "...",
    "sous-titres réalisés par la communauté d'amara.org", "amara.org",
    "untertitel", "untertitelung", "字幕", "字幕by", "so", "yeah", "the",
    "merci", "merci d'avoir regardé", "bedankt voor het kijken",
}

# Accented Latin letters we still treat as "Latin" for the script check.
_LATIN_EXTRA = set("àâäáãéèêëíìîïóòôöõúùûüçñ’'-")


def is_plausible_command(text: str) -> bool:
    """Guard against Whisper hallucinations on ambient noise/silence.

    Rejects empty/very short strings, known hallucination phrases, and — for
    Latin-script languages — transcripts that are mostly non-Latin (e.g. the
    stray Cyrillic 'Бурын' hallucinated from room noise).
    """
    t = (text or "").strip()
    if len(t) < 3:
        return False
    if t.lower() in _HALLUCINATIONS:
        return False
    lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").lower()
    if lang in ("auto", "en", "nl", "fr"):
        letters = [c for c in t if c.isalpha()]
        if letters:
            latin = sum(1 for c in letters if c.isascii() or c.lower() in _LATIN_EXTRA)
            if latin / len(letters) < 0.6:
                return False
    return True


class VoiceLoop:
    def __init__(
        self,
        robot: Any,          # RobotClient (needs .listen() -> (wav, peak))
        pipeline: Any,       # OrchestratorPipeline
        bus: Any,
        session_id: str = "default",
        default_wake_word: str = "aura",
        window_s: float = 4.0,
        followup_s: float = 9.0,
        speech_peak: float = 0.03,
    ) -> None:
        self._robot = robot
        self._pipeline = pipeline
        self._bus = bus
        self._session_id = session_id
        self._default_wake = default_wake_word
        self._window_s = window_s
        self._followup_s = followup_s
        self._speech_peak = float(os.environ.get("VOICE_SPEECH_PEAK", speech_peak))
        self._task: asyncio.Task | None = None
        self._followup_until = 0.0
        self._speaking_until = 0.0
        # U54: barge-in — while the robot talks, a clearly louder voice (the
        # user is closer to the mic than the robot's own speaker echo) cuts the
        # wait and is handled as a reply immediately.
        self._barge_factor = float(os.environ.get("BARGE_IN_FACTOR", "3.0"))
        # U67: follow-up windows may CHAIN at most this many turns without the
        # wake word. Music/TV near the mic otherwise becomes a self-sustaining
        # conversation: lyrics enter a follow-up window, the reply opens the
        # next window, and so on forever (the 'Nordmeer' incident).
        self._max_followup_chain = int(os.environ.get("FOLLOWUP_CHAIN_MAX", "2"))
        self._followup_chain = 0

    @property
    def _barge_in(self) -> bool:
        return os.environ.get("BARGE_IN", "true").lower() == "true"

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("VoiceLoop started (wake word default=%r)", self._default_wake)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def note_spoken(self, text: str) -> None:
        """Called when the robot speaks: guard against echo + open a follow-up
        window so the user can reply without the wake word. The follow-up
        chain is capped (U67) — after a few wake-word-less turns the wake word
        is required again, so ambient audio can't talk to itself forever."""
        now = time.monotonic()
        speak_s = min(12.0, 1.0 + len(text or "") / 15.0)  # ~15 chars/sec
        self._speaking_until = now + speak_s
        if self._followup_chain < self._max_followup_chain:
            self._followup_until = self._speaking_until + self._followup_s
        else:
            self._followup_until = 0.0  # chain exhausted → wake word required

    # -- config (read live so the Settings toggle applies) -------------

    @property
    def _mode(self) -> str:
        return os.environ.get("VOICE_MODE", "off").lower()

    @property
    def _wake(self) -> str:
        return os.environ.get("WAKE_WORD", self._default_wake).strip().lower()

    # -- main loop -----------------------------------------------------

    async def _run(self) -> None:
        from aura_brain import voice

        while True:
            try:
                if self._mode != "wake_word":
                    await asyncio.sleep(1.5)
                    continue

                now = time.monotonic()
                in_barge = False
                if now < self._speaking_until:  # robot is talking
                    if not self._barge_in:
                        await asyncio.sleep(self._speaking_until - now)
                        continue
                    # U54: barge-in — keep listening in short windows; only a
                    # clearly-louder voice counts (filters the robot's own echo).
                    wav, peak = await self._robot.listen(min(2.0, self._window_s))
                    if peak < self._speech_peak * self._barge_factor:
                        continue
                    self._speaking_until = 0.0  # user interrupted → stop waiting
                    self._followup_until = time.monotonic() + self._followup_s
                    in_barge = True
                else:
                    wav, peak = await self._robot.listen(self._window_s)
                    if peak < self._speech_peak:
                        continue  # silence — cheap skip, no STT

                text = (await voice.transcribe(wav, filename="robot.wav") or "").strip()
                if not is_plausible_command(text):
                    if text:
                        logger.debug("voice loop ignored implausible transcript: %r", text)
                    continue

                in_followup = in_barge or time.monotonic() < self._followup_until
                command = self._extract_command(text, in_followup)
                if command is None:
                    continue
                # U67: track the wake-word-less chain. Hearing the wake word
                # resets it — a real user re-engaging restores full flow.
                if self._wake and self._wake in text.lower():
                    self._followup_chain = 0
                elif in_followup:
                    self._followup_chain += 1
                if not command:  # wake word heard but nothing after it
                    command = await self._capture_command()
                    if not is_plausible_command(command):
                        continue

                await self._handle(command)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the loop must never die
                logger.debug("voice loop tick failed: %s", exc)
                await asyncio.sleep(1.0)

    def _extract_command(self, text: str, in_followup: bool) -> str | None:
        """Return the command text, '' if only the wake word was said, or None
        if this utterance should be ignored."""
        if in_followup:
            return text
        lower = text.lower()
        wake = self._wake
        if wake and wake in lower:
            return text[lower.index(wake) + len(wake):].lstrip(" ,.!?-").strip()
        return None  # no wake word, not in follow-up → ignore

    async def _capture_command(self) -> str:
        from aura_brain import voice

        wav, peak = await self._robot.listen(self._window_s)
        if peak < self._speech_peak:
            return ""
        return (await voice.transcribe(wav, filename="robot.wav") or "").strip()

    async def _handle(self, command: str) -> None:
        from shared_schemas.events.audio import TranscriptUpdated

        await self._bus.publish(TranscriptUpdated(
            session_id=self._session_id, transcript=command, is_final=True,
        ))
        logger.info("VoiceLoop heard: %r", command)
        await self._pipeline.orchestrate(command, self._session_id)
        # The reply's ResponseDrafted → note_spoken opens the follow-up window.
