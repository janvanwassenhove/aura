---
feature: "003-event-bus-schemas"
status: "in-progress"
owner: "platform"
priority: P1
risk: Low
created: "2026-04-25"
---

# Feature Specification: Event Bus and Shared Schemas

**Feature Branch**: `003-event-bus-schemas`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: platform
**Priority**: P1
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — Pydantic Schemas Exist for All Core Events (Priority: P1)

Any service can import and instantiate any of the 30+ event types from `packages/shared-schemas` and serialize/deserialize them to JSON without error.

**Why this priority**: All other features depend on typed events. No event bus, no observable state.

**Independent Test**: `pytest packages/shared-schemas/tests/test_event_serialization.py` passes 100%.

**Acceptance Scenarios**:

1. **Given** the `shared-schemas` package, **When** any event type is instantiated with valid data, **Then** it serializes to JSON and deserializes back to the identical object.
2. **Given** a `UserSpeechDetected` event, **When** serialized and deserialized, **Then** `event_type`, `session_id`, `transcript`, and `timestamp` fields are preserved.
3. **Given** a `ToolCallRequested` event, **When** serialized, **Then** `tool_name` and `args` are present; no sensitive data is included.
4. **Given** an invalid event payload, **When** Pydantic validation runs, **Then** a `ValidationError` is raised with a clear field-level message.

---

### User Story 2 — Services Can Publish and Subscribe to Events (Priority: P1)

A service can publish an event to the `AsyncEventBus` and a subscribing handler receives it in the same asyncio event loop without polling.

**Why this priority**: Decouples services; enables the behavior engine and operator console to react to state changes without direct calls.

**Independent Test**: Unit test — publish `RobotConnected`, assert subscriber handler is called within 50ms.

**Acceptance Scenarios**:

1. **Given** an `AsyncEventBus`, **When** a handler is subscribed to `RobotConnected` and that event is published, **Then** the handler is called with the event object.
2. **Given** multiple subscribers for the same event type, **When** the event is published, **Then** all subscribers are called.
3. **Given** a subscriber that raises an exception, **When** the event is published, **Then** other subscribers still receive the event and the exception is logged without crashing the bus.
4. **Given** a subscription, **When** `unsubscribe()` is called, **Then** subsequent publishes of that event type do not invoke the handler.

---

### User Story 3 — Events Are Visible in the Operator Console (Priority: P2)

The operator console event log panel shows real-time events from any connected service.

**Why this priority**: Required for the development inner loop — operators and developers need event visibility.

**Independent Test**: Publish 5 test events; verify they appear in the console event log within 500ms.

**Acceptance Scenarios**:

1. **Given** the operator console is connected via WebSocket, **When** any event is published on the bus, **Then** it appears in the event log panel with event type and timestamp.
2. **Given** a high event rate (100 events/second), **When** events are published, **Then** the console does not freeze; events are queued and displayed without dropping.

---

### Edge Cases

- What happens when the event bus has no subscribers for a published event? → The event is discarded silently; no error is raised.
- What happens when a subscriber is slow? → The bus uses asyncio; slow subscribers do not block publishers. Implement with `asyncio.create_task` per handler.
- What happens when an event is published before the bus is started? → Raises `EventBusNotStartedError`.

---

## Requirements

### Functional Requirements

- **FR-001**: Pydantic v2 models MUST exist for all 28 event types listed in the architecture.
- **FR-002**: All event models MUST include `event_id` (UUID), `event_type` (str), `timestamp` (datetime), and `session_id` (str) fields.
- **FR-003**: `AsyncEventBus` MUST support `publish(event)`, `subscribe(event_type, handler)`, `unsubscribe(event_type, handler)`.
- **FR-004**: `AsyncEventBus` MUST dispatch events to all registered handlers asynchronously using `asyncio.create_task`.
- **FR-005**: `WebSocketBroadcaster` MUST accept WebSocket connections and broadcast all published events as JSON.
- **FR-006**: Event schemas MUST be importable from `shared_schemas.events` with a consistent import path.
- **FR-007**: `RobotState`, `RobotMode`, `Persona`, `MotionCommand`, `MotionTimeline` models MUST exist in `shared_schemas`.
- **FR-008**: All models MUST support `model_dump()` and `model_validate()` (Pydantic v2 API).

### Key Entities

**Event Groups**:
- Robot: `RobotConnected`, `RobotDisconnected`, `RobotModeChanged`
- Audio: `AudioInputStarted`, `UserSpeechDetected`, `TranscriptUpdated`
- Conversation: `IntentRecognized`, `ResponseDrafted`
- Orchestrator: `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed`, `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied`
- Behavior: `BehaviorPlanned`, `SpeechPlaybackStarted`, `MotionStarted`, `MotionCompleted`
- System: `BackendHeartbeatOk`, `BackendHeartbeatFailed`, `OfflineRequestQueued`, `OfflineQueueSyncStarted`, `OfflineQueueSyncCompleted`
- Application: `ReminderTriggered`, `PresentationCueReceived`

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: All 28 event types have Pydantic model definitions.
- **SC-002**: `pytest packages/shared-schemas/tests/` passes 100% with 0 warnings.
- **SC-003**: `pytest packages/shared-events/tests/` passes 100%.
- **SC-004**: Event round-trip (Python object → JSON → Python object) produces identical objects for all 28 types.
- **SC-005**: `AsyncEventBus` handles 1000 publish operations per second in a benchmark test without dropped events.

---

## Assumptions

- The event bus is asyncio in-process for the initial implementation.
- WebSocket broadcaster is part of `shared-events` package, used by `robot-runtime` and `orchestrator` services.
- Event schemas are stable across minor versions; breaking changes require a new event type name.
- Redis Streams upgrade path is documented in ADR-002 but not implemented in this feature.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle III (Events Drive State)
- [ADR-002](docs/adr/ADR-002-event-model.md)
