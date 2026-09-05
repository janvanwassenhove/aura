# ADR-002: Event Model and Inter-Service Communication

**Status**: Accepted 2026-04-25 — **amended 2026-09-05**  
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

---

## Amendment — 2026-09-05

*Recorded as part of the spec backfill (U309, U310).*

**One bus, in one process.** After the collapse in
[spec 001](../../.specify/specs/001-foundation/spec.md) (U1-U11) all routers run
inside `aura-brain`, so the bus is a single shared in-process `AsyncEventBus`,
verified end to end in U6 — not one bus per service with a broadcaster between
them. Redis Streams remains documented and unimplemented, per constitution VII.

**Two properties that later units kept rediscovering**, written down here so
they stop being rediscoveries:

1. **An event only reaches a subscriber that exists when it is published.**
   `RobotConnected` fires when the robot connects — normally before the console
   window exists — so a console that only listens starts by claiming the robot
   is offline. That shipped, visibly, for months (U152, finished in U297).
   *State that must survive a late subscriber is polled, not awaited.*
2. **The projector overlay is not on this bus at all.** It is a separate
   BrowserWindow with its own Pinia store. Anything two windows must agree on
   crosses through an explicit channel — a `storage` event, or the brain —
   never by assumption (U269, U276, U286, U290).
