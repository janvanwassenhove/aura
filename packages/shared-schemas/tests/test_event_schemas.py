"""Tests for shared-schemas event types (spec 003 T012)."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from shared_schemas.events import (
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    AudioInputStarted,
    BackendHeartbeatFailed,
    BackendHeartbeatOk,
    BaseEvent,
    BehaviorPlanned,
    BehaviorStateChanged,
    IntentRecognized,
    MotionCompleted,
    MotionFailed,
    MotionStarted,
    OfflineQueueSyncCompleted,
    OfflineQueueSyncStarted,
    OfflineRequestQueued,
    PresentationCueReceived,
    ReminderTriggered,
    ResponseDrafted,
    RobotConnected,
    RobotDisconnected,
    RobotModeChanged,
    SpeechPlaybackCompleted,
    SpeechPlaybackStarted,
    ToolCallFailed,
    ToolCallRequested,
    ToolCallSucceeded,
    TranscriptUpdated,
    UserSpeechDetected,
)
from shared_schemas.robot.models import RobotMode


# Minimal valid kwargs for each event type
_SESSION = "test-session"
_ADAPTER = "fake"


def _instances() -> list[BaseEvent]:
    return [
        RobotConnected(session_id=_SESSION, adapter_name=_ADAPTER),
        RobotDisconnected(session_id=_SESSION),
        RobotModeChanged(session_id=_SESSION, from_mode=RobotMode.ONLINE, to_mode=RobotMode.DEGRADED),
        AudioInputStarted(session_id=_SESSION),
        UserSpeechDetected(session_id=_SESSION, transcript="hello"),
        TranscriptUpdated(session_id=_SESSION, transcript="hello", is_final=True),
        IntentRecognized(session_id=_SESSION, intent="greet"),
        ResponseDrafted(session_id=_SESSION, response_text="Hi there"),
        ToolCallRequested(session_id=_SESSION, tool_name="get_unread_mail"),
        ToolCallSucceeded(session_id=_SESSION, tool_name="get_unread_mail", result_summary="2 mails"),
        ToolCallFailed(session_id=_SESSION, tool_name="get_unread_mail", error_code="timeout"),
        ApprovalRequested(session_id=_SESSION, approval_id=__import__("uuid").uuid4(), tool_name="send_mail"),
        ApprovalGranted(session_id=_SESSION, approval_id=__import__("uuid").uuid4()),
        ApprovalDenied(session_id=_SESSION, approval_id=__import__("uuid").uuid4()),
        BehaviorStateChanged(session_id=_SESSION, from_state="idle", to_state="listening"),
        BehaviorPlanned(session_id=_SESSION, behavior_state="speaking"),
        SpeechPlaybackStarted(session_id=_SESSION, text_length=42),
        SpeechPlaybackCompleted(session_id=_SESSION),
        MotionStarted(session_id=_SESSION, motion_id="nod"),
        MotionCompleted(session_id=_SESSION, motion_id="nod"),
        MotionFailed(session_id=_SESSION, motion_id="nod", reason="hardware error"),
        BackendHeartbeatOk(session_id=_SESSION, service="llm", latency_ms=12.5),
        BackendHeartbeatFailed(session_id=_SESSION, service="llm", consecutive_failures=3),
        OfflineRequestQueued(session_id=_SESSION, queue_depth=1),
        OfflineQueueSyncStarted(session_id=_SESSION),
        OfflineQueueSyncCompleted(session_id=_SESSION, synced_count=5),
        ReminderTriggered(session_id=_SESSION, reminder_id=__import__("uuid").uuid4(), message="standup"),
        PresentationCueReceived(session_id=_SESSION, slide_number=3, cue_text="Next slide"),
    ]


@pytest.mark.parametrize("event", _instances())
def test_all_events_have_valid_event_id(event: BaseEvent) -> None:
    """Every event type exposes a valid UUID event_id."""
    assert isinstance(event.event_id, UUID)
    # Round-trip through str to confirm it is a valid UUID
    UUID(str(event.event_id))


@pytest.mark.parametrize("event", _instances())
def test_events_are_frozen(event: BaseEvent) -> None:
    """Frozen models reject mutation."""
    with pytest.raises((ValidationError, TypeError)):
        event.session_id = "mutated"  # pydantic intercepts; object.__setattr__ would bypass frozen


@pytest.mark.parametrize("event", _instances())
def test_broadcaster_json_shape(event: BaseEvent) -> None:
    """model_dump_json() output contains required top-level keys."""
    payload = json.loads(event.model_dump_json())
    assert "event_type" in payload
    assert "timestamp" in payload
    assert "session_id" in payload
    assert "event_id" in payload
