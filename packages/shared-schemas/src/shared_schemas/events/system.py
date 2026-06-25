"""System-level and infrastructure events."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from shared_schemas.events.base import BaseEvent


class BackendHeartbeatOk(BaseEvent):
    event_type: Literal["BackendHeartbeatOk"] = "BackendHeartbeatOk"
    session_id: str = ""
    service: str
    latency_ms: float


class BackendHeartbeatFailed(BaseEvent):
    event_type: Literal["BackendHeartbeatFailed"] = "BackendHeartbeatFailed"
    session_id: str = ""
    service: str
    consecutive_failures: int


class OfflineRequestQueued(BaseEvent):
    event_type: Literal["OfflineRequestQueued"] = "OfflineRequestQueued"
    session_id: str = ""
    queue_depth: int


class OfflineQueueSyncStarted(BaseEvent):
    event_type: Literal["OfflineQueueSyncStarted"] = "OfflineQueueSyncStarted"
    session_id: str = ""


class OfflineQueueSyncCompleted(BaseEvent):
    event_type: Literal["OfflineQueueSyncCompleted"] = "OfflineQueueSyncCompleted"
    session_id: str = ""
    synced_count: int


class TurnLatencyMeasured(BaseEvent):
    """Per-turn latency, emitted for the operator console (Phase 3.5, U23).

    first_audio_ms is the voice headline (time-to-first-spoken-word); it stays
    None for text turns until the streaming voice path (U24) lands.
    """

    event_type: Literal["TurnLatencyMeasured"] = "TurnLatencyMeasured"
    total_ms: float
    llm_ms: float = 0.0
    tool_ms: float = 0.0
    first_audio_ms: float | None = None


class ReminderTriggered(BaseEvent):
    event_type: Literal["ReminderTriggered"] = "ReminderTriggered"
    reminder_id: UUID
    message: str


class PresentationCueReceived(BaseEvent):
    event_type: Literal["PresentationCueReceived"] = "PresentationCueReceived"
    slide_number: int
    cue_text: str
