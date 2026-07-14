"""Perception events (U18). The robot's camera (on the Pi) is 🔒 hardware; the
recognition/matching logic and these events are built and tested without it."""

from __future__ import annotations

from typing import Literal

from shared_schemas.events.base import BaseEvent


class GestureDetected(BaseEvent):
    """A hand gesture seen by the robot camera (U36e). Transient — never stored."""

    event_type: Literal["GestureDetected"] = "GestureDetected"
    gesture: str  # e.g. "open_palm" (a wave/hi), "thumbs_up"
    confidence: float = 0.0


class PersonRecognized(BaseEvent):
    """Emitted when the perception layer matches (or fails to match) a face.

    `person_id`/`display_name` are None for an unknown face. `known` lets the
    brain react: greet by name + suggest a mode for a known person, stay guarded
    for a stranger.
    """

    event_type: Literal["PersonRecognized"] = "PersonRecognized"
    person_id: str | None = None
    display_name: str | None = None
    confidence: float = 0.0
    known: bool = False
