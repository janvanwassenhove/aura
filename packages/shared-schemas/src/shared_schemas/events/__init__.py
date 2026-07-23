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
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    AuthRequiredEvent,
    ComputerControlEnded,
    ComputerControlStarted,
    ToolCallFailed,
    ToolCallRequested,
    ToolCallSucceeded,
)
from shared_schemas.events.perception import GestureDetected, PersonRecognized
from shared_schemas.events.robot import RobotConnected, RobotDisconnected, RobotModeChanged
from shared_schemas.events.system import (
    BackendHeartbeatFailed,
    BackendHeartbeatOk,
    MaintenanceReport,
    OfflineQueueSyncCompleted,
    OfflineQueueSyncStarted,
    OfflineRequestQueued,
    PresentationBeatFired,
    PresentationCueReceived,
    ReminderTriggered,
    TurnLatencyMeasured,
)

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
    "PresentationBeatFired",
    "PresentationCueReceived",
]
