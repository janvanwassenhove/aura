# 002 — FakeRobot Simulation: Task List

Format: `[ID] [P?] [US-N] Description`

User Story refs:
- US-1: FakeRobot implements full RobotAdapter contract
- US-2: Operator console displays robot state
- US-3: CI runs automated adapter tests

## Phase 0: Prereqs (spec 001 tasks must be complete)

- [x] `T001` Verify `packages/shared-schemas` package stub exists with `uv sync`

## Phase 1: RobotAdapter ABC and Models (shared-schemas)

- [x] `T002` [US-1] `packages/shared-schemas/src/shared_schemas/robot/__init__.py`
- [x] `T003` [US-1] `packages/shared-schemas/src/shared_schemas/robot/models.py`
  - `RobotMode(StrEnum)` — ONLINE, DEGRADED, OFFLINE, MAINTENANCE
  - `BehaviorState(StrEnum)` — IDLE, LISTENING, THINKING, SPEAKING, RESPONDING
  - `RobotState(BaseModel)` — mode, behavior_state, battery_pct, connected, adapter_name
  - `MotionCue(BaseModel)` — offset_ms, motion_id, speed, amplitude
  - `MotionCommand(BaseModel)` — motion_id, speed, amplitude, direction
  - `MotionTimeline(BaseModel)` — cues: list[MotionCue]
- [x] `T004` [US-1] `packages/shared-schemas/src/shared_schemas/robot/adapter.py`
  - `RobotAdapter(ABC)` with all 9 abstract methods and type signatures

## Phase 2: Event Models for Robot (shared-schemas)

- [x] `T005` [US-1] `packages/shared-schemas/src/shared_schemas/events/base.py` — `BaseEvent`
- [x] `T006` [US-1] `packages/shared-schemas/src/shared_schemas/events/robot.py`
  - `RobotConnected`, `RobotDisconnected`, `RobotModeChanged`
- [x] `T007` [US-1] `packages/shared-schemas/src/shared_schemas/events/__init__.py` — re-exports

## Phase 3: AsyncEventBus Minimal (shared-events) [P with Phase 2]

- [x] `T008` [P] [US-1] `packages/shared-events/src/shared_events/bus.py` — minimal `AsyncEventBus`
  - `start()`, `stop()`, `publish()`, `subscribe()`, `unsubscribe()`
  - Exception handling in tasks (log; don't crash)

## Phase 4: FakeRobotAdapter (robot-runtime)

- [x] `T009` [US-1] `services/robot-runtime/src/robot_runtime/adapters/__init__.py`
- [x] `T010` [US-1] `services/robot-runtime/src/robot_runtime/adapters/fake.py`
  - `FakeRobotAdapter(RobotAdapter)` — all 9 methods ✓
  - Note: `get_camera_frame()` returns raw RGB bytes (480×640×3), not PNG — deviation accepted (see T015)
- [x] `T011` [US-1] ~~`services/robot-runtime/src/robot_runtime/adapters/factory.py`~~ **DEVIATION ACCEPTED**
  - Adapter selection is inlined in `main.py` — functionally equivalent; dedicated factory.py deferred to future refactor

## Phase 5: REST API (robot-runtime)

- [x] `T012` [US-2] Update `services/robot-runtime/src/robot_runtime/main.py`
  - `GET /health`, `GET /robot/status`, `POST /robot/speak`, `POST /robot/motion` all exist

## Phase 6: WebSocket Broadcaster (shared-events)

- [x] `T013` [US-2] `packages/shared-events/src/shared_events/broadcaster.py`
  - `WebSocketBroadcaster` — `connect(ws)`, `disconnect(ws)`, fan-out on publish ✓

## Phase 7: Contract Tests

- [x] `T014` [US-3] ~~`tests/contract/__init__.py`~~ **DEVIATION ACCEPTED**
  - Root `tests/contract/` not created; equivalent tests in `services/robot-runtime/tests/test_fake_adapter.py`
- [x] `T015` [US-3] ~~`tests/contract/test_robot_adapter_contract.py`~~ **DEVIATION ACCEPTED**
  - Equivalent coverage in `services/robot-runtime/tests/test_fake_adapter.py` ✓
  - **AC update**: `get_camera_frame()` returns raw RGB bytes (480×640×3); PNG encoding deferred to future work

## Phase 8: CI Gate

- [x] `T016` [US-3] CI runs robot-runtime tests (via `services/robot-runtime/tests/`)

## Acceptance Criteria (from spec.md)

- `connect()` → `get_status()` returns `connected=True`
- `speak()` does not raise; logs contain `[FAKE]` prefix
- `capture_audio()` returns bytes (silence)
- `get_camera_frame()` returns raw RGB bytes (480×640×3) — PNG encoding deferred
- `execute_motion()` emits `MotionStarted` + `MotionCompleted`
- `set_state()` with mode change emits `RobotModeChanged`
- All 6 contract tests pass against `FakeRobotAdapter`
