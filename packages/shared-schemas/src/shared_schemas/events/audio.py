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


class SpeechAudioStopped(BaseEvent):
    """U385: stop playing him on this laptop, now, and drop what is queued.

    Every way of silencing him — barge-in, the realtime cut, the panic stop —
    used to stop the robot's speaker and nothing else. With his voice routed to
    the laptop (U364) that left the laptop talking after Stop was pressed.
    Published on every stop, whichever speaker is in use: a console that is not
    playing anything simply has nothing to stop.
    """

    event_type: Literal["SpeechAudioStopped"] = "SpeechAudioStopped"


class SpeechLineStarted(BaseEvent):
    """U400: the laptop has started playing a line — now, not when it was offered.

    The window that plays a line (`SpeechAudioReady`) says so through the brain,
    because the window that subtitles it is another one: the projector overlay
    has its own store, and only an explicit channel reaches it. `duration_s` is
    what the player measured; 0 when it could not tell.
    """

    event_type: Literal["SpeechLineStarted"] = "SpeechLineStarted"
    utterance_id: str
    duration_s: float = 0.0

