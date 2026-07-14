"""Re-export all 30 AURA event types."""

from shared_schemas.events.audio import (
    AudioInputStarted,
    TranscriptUpdated,
    UserSpeechDetected,
)
from shared_schemas.events.base import BaseEvent
from shared_schemas.events.behavior import (
    BehaviorPlanned,
    BehaviorStateChanged,
    MotionCompleted,
    MotionFailed,
    MotionStarted,
    SpeechPlaybackCompleted,
    SpeechPlaybackStarted,
)
from shared_schemas.events.conversation import IntentRecognized, ResponseDrafted
from shared_schemas.events.orchestrator import (
    AgentRoundCompleted,
    AgentRoundStarted,
    ComputerControlEnded,
    ComputerControlStarted,
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    AuthRequiredEvent,
    ToolCallFailed,
    ToolCallRequested,
    ToolCallSucceeded,
)
from shared_schemas.events.robot import RobotConnected, RobotDisconnected, RobotModeChanged
from shared_schemas.events.system import (
    MaintenanceReport,
    BackendHeartbeatFailed,
    BackendHeartbeatOk,
    OfflineQueueSyncCompleted,
    OfflineQueueSyncStarted,
    OfflineRequestQueued,
    PresentationCueReceived,
    ReminderTriggered,
    TurnLatencyMeasured,
)
from shared_schemas.events.perception import GestureDetected, PersonRecognized

__all__ = [
    "BaseEvent",
    # robot
    "RobotConnected",
    "RobotDisconnected",
    "RobotModeChanged",
    # audio
    "AudioInputStarted",
    "UserSpeechDetected",
    "TranscriptUpdated",
    # conversation
    "IntentRecognized",
    "ResponseDrafted",
    # orchestrator
    "AgentRoundCompleted",
    "AgentRoundStarted",
    "ComputerControlEnded",
    "ComputerControlStarted",
    "ToolCallRequested",
    "ToolCallSucceeded",
    "ToolCallFailed",
    "ApprovalRequested",
    "ApprovalGranted",
    "ApprovalDenied",
    "AuthRequiredEvent",
    # behavior
    "BehaviorStateChanged",
    "BehaviorPlanned",
    "SpeechPlaybackStarted",
    "SpeechPlaybackCompleted",
    "MotionStarted",
    "MotionCompleted",
    "MotionFailed",
    # system
    "BackendHeartbeatOk",
    "MaintenanceReport", "TurnLatencyMeasured",
    "GestureDetected", "PersonRecognized",
    "BackendHeartbeatFailed",
    "OfflineRequestQueued",
    "OfflineQueueSyncStarted",
    "OfflineQueueSyncCompleted",
    "ReminderTriggered",
    "PresentationCueReceived",
]
