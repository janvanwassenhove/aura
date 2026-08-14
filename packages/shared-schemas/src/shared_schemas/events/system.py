"""System-level and infrastructure events."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from shared_schemas.events.base import BaseEvent


class MaintenanceReport(BaseEvent):
    """Periodic self-check by the brain's maintenance loop (U36g)."""

    event_type: Literal["MaintenanceReport"] = "MaintenanceReport"
    healthy: bool = True
    checks: dict[str, str] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)


class SkillProposalRaised(BaseEvent):
    """U250: the assistant brought a skill up ITSELF.

    Until now a proposal waited behind a button, so a skill could die at the
    same step every day and nothing said a word. This is the assistant asking:
    here is what keeps going wrong, here is what I would write instead — may I?

    It is a QUESTION, never a change. Nothing is saved until the owner applies
    it through the ordinary save path, exactly as with every skill write since
    U59.
    """

    event_type: Literal["SkillProposalRaised"] = "SkillProposalRaised"
    kind: str = "rewrite"          # "rewrite" | "new"
    skill: str = ""                # existing skill, or the topic for a new one
    reason: str = ""               # why this came up, in the owner's terms
    rationale: str = ""            # what the rewrite changes and why
    current_body: str = ""
    proposed_body: str = ""
    description: str = ""          # new skills only
    triggers: list[str] = Field(default_factory=list)   # new skills only


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


class PresentationBeatFired(BaseEvent):
    """U206: a co-presenter beat ran — the presenter view shows `spoken` as the
    live subtitle. `spoken` is empty for a silent beat."""

    event_type: Literal["PresentationBeatFired"] = "PresentationBeatFired"
    beat_id: str
    mode: str
    spoken: str = ""
    slide_number: int | None = None
