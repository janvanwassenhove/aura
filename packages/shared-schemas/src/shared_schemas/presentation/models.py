"""Presentation script Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
