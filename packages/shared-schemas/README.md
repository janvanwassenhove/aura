# shared-schemas

## Purpose

The single source of truth for all data contracts in AURA:

- **All 30 Pydantic v2 event models** — used by every service to publish and subscribe to events
- **ABCs** — `RobotAdapter`, `STTProvider`, `TTSProvider`, `M365Connector`, `MemoryStore`
- **Shared domain models** — `RobotState`, `RobotMode`, `MotionCommand`, `MotionTimeline`, `Persona`, `CalendarEvent`, `MailItem`, `Task`

## Installation

```bash
# From any service or package
uv add shared-schemas --path ../../packages/shared-schemas
```

## Event Import Paths

```python
from shared_schemas.events.robot import RobotConnected, RobotModeChanged
from shared_schemas.events.audio import UserSpeechDetected
from shared_schemas.events.orchestrator import ToolCallRequested, ApprovalRequested
from shared_schemas.events.behavior import BehaviorStateChanged, MotionStarted
from shared_schemas.events.system import BackendHeartbeatOk, ReminderTriggered

from shared_schemas.robot.adapter import RobotAdapter
from shared_schemas.robot.models import RobotState, RobotMode, MotionCommand, MotionTimeline
from shared_schemas.voice.providers import STTProvider, TTSProvider
from shared_schemas.m365.connector import M365Connector
from shared_schemas.memory.store import MemoryStore
```

## All Event Types

| Group | Events |
|-------|--------|
| Robot | `RobotConnected`, `RobotDisconnected`, `RobotModeChanged` |
| Audio | `AudioInputStarted`, `UserSpeechDetected`, `TranscriptUpdated` |
| Conversation | `IntentRecognized`, `ResponseDrafted` |
| Orchestrator | `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed`, `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied` |
| Behavior | `BehaviorStateChanged`, `BehaviorPlanned`, `SpeechPlaybackStarted`, `MotionStarted`, `MotionCompleted`, `MotionFailed` |
| System | `BackendHeartbeatOk`, `BackendHeartbeatFailed`, `OfflineRequestQueued`, `OfflineQueueSyncStarted`, `OfflineQueueSyncCompleted`, `ReminderTriggered`, `PresentationCueReceived` |

## Base Event Fields

Every event includes: `event_id` (UUID), `event_type` (str), `timestamp` (datetime), `session_id` (str).

## Tests

```bash
uv run pytest tests/
```
