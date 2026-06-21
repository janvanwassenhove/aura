# ADR-002: Event Model and Inter-Service Communication

**Status**: Accepted  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA has 6 backend services that need to share state and react to each other without tight coupling:
- `robot-runtime` emits motion and audio events
- `conversation-runtime` emits transcript and intent events
- `orchestrator` emits tool call and approval events
- `operator-console` needs to receive all events for display

We needed to choose: event format, transport, and pub/sub mechanism.

---

## Decision

**Event Format**: Typed Pydantic v2 models in `packages/shared-schemas`  
**Event Bus (dev)**: asyncio in-process pub/sub (`AsyncEventBus` in `packages/shared-events`)  
**External Fan-out**: WebSocket broadcaster (FastAPI WebSocket connections to operator console)  
**Future Production Path**: Redis Streams (documented here but not implemented until a production spec exists)  
**Event Base Fields**: `event_id` (UUID), `event_type` (str), `timestamp` (datetime), `session_id` (str)

---

## Rationale

### Pydantic v2 Event Models
- Compile-time schema documentation prevents mismatches
- JSON serialization is required for WebSocket delivery and future Redis Streams
- 30 event types across 6 groups cover all known state transitions
- Pydantic `model_validate()` enforces schema at subscribe time

### asyncio In-Process Bus for Dev
- Zero infrastructure: no Redis, RabbitMQ, or Kafka needed in development
- `asyncio.create_task` per handler prevents slow subscribers from blocking publishers
- Tests can subscribe, publish, and assert in a single event loop without mocking
- Services co-located in Docker Compose can share the same bus via the `shared-events` package

### WebSocket Fan-out to Operator Console
- Browser cannot connect to asyncio event bus directly
- WebSocket is the lowest-latency option for browser real-time updates
- Each service exposes a `/ws/events` endpoint; the console connects to robot-runtime and orchestrator
- Events are serialized to JSON for browser consumption

### Redis Streams as Future Path
- When services scale to separate machines, asyncio bus is insufficient
- Redis Streams provide persistence (replay), consumer groups, and acknowledgment
- The `AsyncEventBus` interface can be swapped for a Redis implementation without changing service code
- This migration requires a new spec and ADR amendment

---

## Event Groups and Types

| Group | Events |
|-------|--------|
| Robot | `RobotConnected`, `RobotDisconnected`, `RobotModeChanged` |
| Audio | `AudioInputStarted`, `UserSpeechDetected`, `TranscriptUpdated` |
| Conversation | `IntentRecognized`, `ResponseDrafted` |
| Orchestrator | `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed`, `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied` |
| Behavior | `BehaviorStateChanged`, `BehaviorPlanned`, `SpeechPlaybackStarted`, `MotionStarted`, `MotionCompleted`, `MotionFailed` |
| System | `BackendHeartbeatOk`, `BackendHeartbeatFailed`, `OfflineRequestQueued`, `OfflineQueueSyncStarted`, `OfflineQueueSyncCompleted` |
| Application | `ReminderTriggered`, `PresentationCueReceived` |

---

## Consequences

### Positive
- No infrastructure setup for local development
- Event types are documented and versioned as code
- asyncio bus is easily testable without mocking external systems
- WebSocket fan-out works with the Vue 3 reactive store model

### Negative
- In-process bus does not survive service restarts (events are lost if a service crashes)
- Scaling to multiple service instances requires the Redis Streams migration
- WebSocket reconnection must be handled by the client

### Neutral
- The 30 event types represent the full known state space; new events require a schema change and PR

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| REST polling for state | Too high latency for audio/motion sync; tight coupling |
| gRPC streaming | Adds code generation complexity; not natural for browser clients |
| RabbitMQ from day one | Requires infrastructure even for local dev; YAGNI |
| Plain dict events | No type safety; schema drift between services |
| Server-Sent Events (SSE) | One-way only; cannot support approval grant/deny from console |
