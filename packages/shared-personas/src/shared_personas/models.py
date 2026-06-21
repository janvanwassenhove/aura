"""Persona models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Persona(StrEnum):
    WORK = "work"
    HOME = "home"
    PRESENTATION = "presentation"
    SILENT_DESK = "silent_desk"
    DEMO = "demo"


class GestureProfile(BaseModel):
    amplitude: float = Field(ge=0.0, le=1.0)
    motion_ids: list[str]
    inter_cue_ms: int = Field(ge=0)


class PersonaConfig(BaseModel):
    name: Persona
    voice_style: str
    gesture_profile: GestureProfile
    system_prompt_template: str
