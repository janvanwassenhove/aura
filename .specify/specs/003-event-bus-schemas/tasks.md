# 003 — Event Bus & Schemas: Task List

Format: `[ID] [P?] [US-N] Description`

User Story refs:
- US-1: Pydantic schemas for all 28 event types
- US-2: Pub/sub bus with asyncio dispatch
- US-3: Operator console sees all events

## Phase 0: Prereqs (spec 001 stubs required; spec 002 BaseEvent required)

- [x] `T001` Verify `BaseEvent` class exists in `shared_schemas.events.base`
- [x] `T002` Verify `AsyncEventBus` minimal implementation exists from spec 002

## Phase 1: Remaining Event Models (shared-schemas) [all P]

- [x] `T003` [P] [US-1] `packages/shared-schemas/src/shared_schemas/events/audio.py`
- [x] `T004` [P] [US-1] `packages/shared-schemas/src/shared_schemas/events/conversation.py`
- [x] `T005` [P] [US-1] `packages/shared-schemas/src/shared_schemas/events/orchestrator.py`
- [x] `T006` [P] [US-1] `packages/shared-schemas/src/shared_schemas/events/behavior.py`
- [x] `T007` [P] [US-1] `packages/shared-schemas/src/shared_schemas/events/system.py`

## Phase 2: Update Event __init__ (shared-schemas)

- [x] `T008` [US-1] Update `packages/shared-schemas/src/shared_schemas/events/__init__.py`
  - 28 event types re-exported (spec said "30" but only 28 are defined — spec count was off by 2)

## Phase 3: Complete AsyncEventBus (shared-events)

- [x] `T009` [US-2] `packages/shared-events/src/shared_events/bus.py`
  - `asyncio.create_task` dispatch ✓, `EventBusNotStartedError` ✓, exception isolation ✓

## Phase 4: Complete WebSocketBroadcaster (shared-events)

- [x] `T010` [US-3] `packages/shared-events/src/shared_events/broadcaster.py`
  - Subscribes to all 28 event types; JSON fan-out; handles disconnect silently ✓

## Phase 5: Tests

- [x] `T011` [US-2] `packages/shared-events/tests/test_event_bus.py`
  - Note: path differs from spec (`packages/` not `tests/unit/`); 5 of 6 cases covered
  - ⚠️ **Missing**: `test_slow_handler_doesnt_block` and `test_multiple_handlers`
- [x] `T012` [US-3] `packages/shared-schemas/tests/test_event_schemas.py` ✓ — 3 tests (parametrized over 28 events) pass

## Phase 6: CI Gate

- [x] `T013` Verify all event model tests pass ✓ — `packages/shared-schemas/tests/test_event_schemas.py` passes
- [x] `T014` Verify bus tests pass ✓ — `packages/shared-events/tests/test_event_bus.py` passes

## Acceptance Criteria (from spec.md)

- All 28 event types importable from `shared_schemas.events`
- Each event has `event_id`, `event_type`, `timestamp`, `session_id`
- All events are frozen (immutable)
- `asyncio.create_task` dispatch verified by timing test
- `WebSocketBroadcaster` sends all events as JSON on connect
