"""Presentation script Pydantic models.

Two layers:
  - SlideScript / PresentationScript (U80): one verbatim speech cue per slide.
    The robot reads a scripted deck aloud.
  - Beat / Scenario (U205): a *co-presenter*. Each beat has a MODE (speak
    verbatim / improvise on a topic / chime in when it hears a keyword / stay
    silent) and a TRIGGER (advance by hand / a specific slide / a spoken
    keyword). This is what makes it feel like presenting *with* the robot
    rather than having it read a script.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from shared_schemas.presentation.vocals import (
    PERSONA_ID,
    VoiceSegment,
    persona_marker_problem,
    split_persona_segments,
)


class SlideScript(BaseModel):
    """A single slide's script entry."""

    slide_index: int = Field(..., ge=0, description="0-based slide index")
    speech_cue: str = Field(..., min_length=1, description="Text AURA speaks verbatim")
    motion_cue: str | None = Field(None, description="Optional gesture name (e.g. 'nod')")
    notes: str = Field("", description="Presenter notes (not spoken)")


class PresentationScript(BaseModel):
    """Full presentation script — one SlideScript per slide."""

    title: str = ""
    slides: list[SlideScript] = Field(default_factory=list)

    def get_slide(self, index: int) -> SlideScript | None:
        """Return the SlideScript for *index*, or None if out of range."""
        for slide in self.slides:
            if slide.slide_index == index:
                return slide
        return None


# ----------------------------------------------------------------------------
# U205: the co-presenter beat model
# ----------------------------------------------------------------------------

BeatMode = Literal["speak", "improvise", "chime_in", "silent"]


# U352: when the projector overlay is on screen and when it is not.
#
# "hidden" describes a state and "hide" an action; a scenario-level default
# reads naturally as the first and a beat as the second, and people reach for
# either in both places. Refusing one of them teaches nothing, so both are
# accepted everywhere and normalised here.
_OVERLAY_SHOW = ("show", "shown")
_OVERLAY_HIDE = ("hide", "hidden")


def _overlay_word(value: str) -> bool | None:
    """True (show), False (hide), or None for "not mentioned".

    Raises ValueError on a word that is neither — an overlay that silently
    ignored a typo would leave the robot on the projector through the one
    moment the scenario was written to clear it.
    """
    word = (value or "").strip().lower()
    if not word:
        return None
    if word in _OVERLAY_SHOW:
        return True
    if word in _OVERLAY_HIDE:
        return False
    raise ValueError(f"overlay must be shown or hidden, not {value!r}")


class Beat(BaseModel):
    """One moment in the presentation the robot participates in."""

    id: str = Field(..., min_length=1)
    # "manual" (advance by hand) | "slide:N" (a slide became active) |
    # "keyword:foo bar" (the presenter said this).
    trigger: str = Field("manual")
    mode: BeatMode = "speak"

    text: str = ""          # spoken verbatim when mode == speak
    topic: str = ""         # what to talk about when improvise / chime_in
    guardrails: str = ""    # extra constraints for improvise / chime_in
    gesture: str | None = None
    # "" inherit the persona/global engine; else force pipeline/realtime for
    # this beat (a beat that needs a tool lookup must be "pipeline" — U203).
    engine: str = ""
    once: bool = True       # chime_in: fire at most once per run
    # U352: show or hide the projector overlay from this beat onwards. Empty
    # means "leave it as it is" — which is why a scenario written before this
    # existed still shows the overlay for its whole length.
    overlay: str = ""
    # U349: which character speaks this beat — a brain character id, e.g.
    # "dry_tech_butler". Empty means the presentation's own voice (Present →
    # Persona). It sets the voice AND the way the line is written when the beat
    # improvises. Within `text`, `[persona:other_id]` hands the line over
    # mid-sentence and `[persona]` hands it back.
    persona: str = ""

    @property
    def trigger_kind(self) -> str:
        return self.trigger.split(":", 1)[0].strip().lower()

    @property
    def trigger_value(self) -> str:
        return self.trigger.split(":", 1)[1].strip() if ":" in self.trigger else ""

    @property
    def slide_number(self) -> int | None:
        if self.trigger_kind == "slide":
            try:
                return int(self.trigger_value)
            except ValueError:
                return None
        return None

    @property
    def overlay_change(self) -> bool | None:
        """True to show, False to hide, None to leave the overlay alone."""
        return _overlay_word(self.overlay)

    def speech_segments(self, text: str | None = None) -> list[VoiceSegment]:
        """This beat's line, cut up by who says which part (U349).

        `text` overrides the beat's own — improvise and chime_in have no
        written line, but what the LLM hands back still comes out in this
        beat's persona.
        """
        return split_persona_segments(
            self.text if text is None else text, self.persona)

    @model_validator(mode="after")
    def _check(self) -> Beat:
        if self.trigger_kind not in ("manual", "slide", "keyword"):
            raise ValueError(f"unknown trigger {self.trigger!r}")
        if self.trigger_kind == "slide" and self.slide_number is None:
            raise ValueError(f"slide trigger needs a number: {self.trigger!r}")
        if self.trigger_kind == "keyword" and not self.trigger_value:
            raise ValueError("keyword trigger needs a word")
        if self.mode == "speak" and not self.text.strip():
            raise ValueError(f"beat {self.id!r}: speak mode needs 'text'")
        if self.mode in ("improvise", "chime_in") and not self.topic.strip():
            raise ValueError(f"beat {self.id!r}: {self.mode} mode needs 'topic'")
        # chime_in is armed by hearing a keyword — any other trigger can't arm it.
        if self.mode == "chime_in" and self.trigger_kind != "keyword":
            raise ValueError(f"beat {self.id!r}: chime_in must use a keyword trigger")
        if self.engine and self.engine not in ("pipeline", "realtime"):
            raise ValueError(f"beat {self.id!r}: engine must be pipeline or realtime")
        # U349: a marker that is nearly right is prose, and prose is read out
        # loud. Catching it here puts it on the presenter's screen instead of
        # in the room.
        if self.persona and not PERSONA_ID.match(self.persona):
            raise ValueError(
                f"beat {self.id!r}: persona must be an id like 'dry_tech_butler'")
        if problem := persona_marker_problem(self.text):
            raise ValueError(f"beat {self.id!r}: {problem}")
        try:
            _overlay_word(self.overlay)
        except ValueError as exc:
            raise ValueError(f"beat {self.id!r}: {exc}") from exc
        return self


class Scenario(BaseModel):
    """A full co-presenter scenario — the beats for one talk."""

    title: str = ""
    pptx: str = ""          # informational: the deck this scenario accompanies
    # U352: where the overlay starts. "hidden" makes the whole talk start clear
    # so it appears only at the beats that ask for it; empty or "shown" is the
    # behaviour every scenario had before this field existed.
    overlay: str = ""
    beats: list[Beat] = Field(default_factory=list)

    @property
    def overlay_starts_visible(self) -> bool:
        """Whether the overlay is on screen before any beat has fired."""
        return _overlay_word(self.overlay) is not False

    @model_validator(mode="after")
    def _unique_ids(self) -> Scenario:
        _overlay_word(self.overlay)
        seen: set[str] = set()
        for b in self.beats:
            if b.id in seen:
                raise ValueError(f"duplicate beat id {b.id!r}")
            seen.add(b.id)
        return self
