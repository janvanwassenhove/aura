"""Audio and transcription events."""

from __future__ import annotations

from typing import Literal

from shared_schemas.events.base import BaseEvent


class AudioInputStarted(BaseEvent):
    event_type: Literal["AudioInputStarted"] = "AudioInputStarted"


class UserSpeechDetected(BaseEvent):
    event_type: Literal["UserSpeechDetected"] = "UserSpeechDetected"
    transcript: str


class TranscriptUpdated(BaseEvent):
    event_type: Literal["TranscriptUpdated"] = "TranscriptUpdated"
    transcript: str
    is_final: bool = False
