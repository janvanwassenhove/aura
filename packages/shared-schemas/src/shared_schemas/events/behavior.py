"""Behavior engine events."""

from __future__ import annotations

from typing import Literal

from shared_schemas.events.base import BaseEvent


class BehaviorStateChanged(BaseEvent):
    event_type: Literal["BehaviorStateChanged"] = "BehaviorStateChanged"
    from_state: str
    to_state: str


class BehaviorPlanned(BaseEvent):
    event_type: Literal["BehaviorPlanned"] = "BehaviorPlanned"
    behavior_state: str


class SpeechPlaybackStarted(BaseEvent):
    event_type: Literal["SpeechPlaybackStarted"] = "SpeechPlaybackStarted"
    text_length: int


class SpeechPlaybackCompleted(BaseEvent):
    event_type: Literal["SpeechPlaybackCompleted"] = "SpeechPlaybackCompleted"


class MotionStarted(BaseEvent):
    event_type: Literal["MotionStarted"] = "MotionStarted"
    motion_id: str


class MotionCompleted(BaseEvent):
    event_type: Literal["MotionCompleted"] = "MotionCompleted"
    motion_id: str


class MotionFailed(BaseEvent):
    event_type: Literal["MotionFailed"] = "MotionFailed"
    motion_id: str
    reason: str
