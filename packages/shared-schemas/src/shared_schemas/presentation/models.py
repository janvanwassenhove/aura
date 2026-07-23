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
        return self


class Scenario(BaseModel):
    """A full co-presenter scenario — the beats for one talk."""

    title: str = ""
    pptx: str = ""          # informational: the deck this scenario accompanies
    beats: list[Beat] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Scenario:
        seen: set[str] = set()
        for b in self.beats:
            if b.id in seen:
                raise ValueError(f"duplicate beat id {b.id!r}")
            seen.add(b.id)
        return self
