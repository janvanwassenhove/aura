---
spec: "003-event-bus-schemas"
status: draft
created: 2025-01-01
---

# 003 — Event Bus & Schemas: Implementation Plan

## Summary

Define all 30 Pydantic v2 event models in `shared-schemas` and implement the `AsyncEventBus` with WebSocket broadcaster in `shared-events`. Every service imports from these packages; no service defines its own event types.

## Technical Context

- Pydantic v2 `model_config = ConfigDict(frozen=True)` — all events are immutable
- `asyncio.create_task` per subscriber — slow subscribers cannot block the bus
- `WebSocketBroadcaster` serializes events as JSON using `model.model_dump_json()`
- BaseEvent fields: `event_id: UUID`, `event_type: str` (Literal), `timestamp: datetime`, `session_id: str`

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Spec-First | All 28 event types defined in spec.md | ✅ |
| Events Drive State | Every state change maps to an event | ✅ |
| No Sensitive Data in Logs | Event serialization reviewed for token fields | ✅ |
| Simplicity | No external broker in dev; asyncio only | ✅ |

## Project Structure

```
packages/shared-schemas/src/shared_schemas/
├── events/
│   ├── __init__.py        # re-exports all event classes
│   ├── base.py            # BaseEvent
│   ├── robot.py           # RobotConnected, RobotDisconnected, RobotModeChanged
│   ├── audio.py           # AudioInputStarted, UserSpeechDetected, TranscriptUpdated
│   ├── conversation.py    # IntentRecognized, ResponseDrafted
│   ├── orchestrator.py    # ToolCall*, Approval* (6 events)
│   ├── behavior.py        # BehaviorStateChanged, BehaviorPlanned, Speech*, Motion* (6)
│   └── system.py          # Heartbeat*, OfflineQueue*, ReminderTriggered, PresentationCueReceived

packages/shared-events/src/shared_events/
├── __init__.py
├── bus.py                 # AsyncEventBus
└── broadcaster.py         # WebSocketBroadcaster

tests/
└── test_event_bus.py
```

## Implementation Steps

### Phase 1: BaseEvent (shared-schemas)

```python
class BaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str
```

### Phase 2: Event Models (shared-schemas)

Create one file per group. Each event:
- Inherits `BaseEvent`
- Has `event_type: Literal["<EventTypeName>"] = "<EventTypeName>"`
- Has only fields defined in the spec

Key field notes:
- `ApprovalRequested` must include `approval_id: UUID` and `tool_name: str`; MUST NOT include tool arguments containing sensitive data
- `ToolCallSucceeded` result field is `Optional[str]`; truncate at 500 chars at the model level (validator)
- `ReminderTriggered` includes `reminder_id: UUID`, `message: str`

### Phase 3: AsyncEventBus (shared-events)

```python
class AsyncEventBus:
    async def start(self) -> None
    async def stop(self) -> None
    async def publish(self, event: BaseEvent) -> None
    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None
    def unsubscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None
```

- `publish` dispatches to all handlers via `asyncio.create_task`
- Exceptions in handlers are caught and logged; bus is not stopped
- `EventBusNotStartedError` raised if `publish` is called before `start()`

### Phase 4: WebSocketBroadcaster (shared-events)

```python
class WebSocketBroadcaster:
    def __init__(self, bus: AsyncEventBus)
    async def connect(self, ws: WebSocket) -> None
    def disconnect(self, ws: WebSocket) -> None
```

- Subscribes to ALL event types on `connect`
- Serializes with `event.model_dump_json()`
- Disconnects silently on `WebSocketDisconnect`

### Phase 5: Tests

1. `test_publish_subscribe` — handler receives event
2. `test_slow_handler_doesnt_block` — slow handler doesn't delay second event
3. `test_unsubscribe` — handler not called after unsubscribe
4. `test_not_started_raises` — publish before start raises
5. `test_broadcaster_json` — event serializes to expected JSON shape

## Complexity Tracking

- Python files: ~15 files, ~350 lines
- Zero external broker dependencies in dev
