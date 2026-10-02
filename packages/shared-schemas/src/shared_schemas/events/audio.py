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


class SpeechAudioReady(BaseEvent):
    """U364: a line has been synthesized and is waiting to be played HERE.

    Published only when the owner has chosen to hear him through the laptop
    rather than the robot's own speaker. It carries an id, not the audio: the
    bytes are fetched once over HTTP (`GET /speech/{utterance_id}.wav`), which
    keeps a few hundred kilobytes per line off the event bus and lets the
    console hand the URL straight to an `<audio>` element.

    `text` rides along so the console can show what is being said without
    waiting for the audio to arrive.
    """

    event_type: Literal["SpeechAudioReady"] = "SpeechAudioReady"
    utterance_id: str
    text: str = ""
