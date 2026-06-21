---
spec: "002-fakerobot-simulation"
status: draft
created: 2025-01-01
---

# 002 — FakeRobot Simulation: Implementation Plan

## Summary

Implement the `RobotAdapter` ABC in `shared-schemas` and the `FakeRobotAdapter` in `robot-runtime`. Provide an operator console panel to display fake robot state.

## Technical Context

- `RobotAdapter` ABC: 9 methods — `connect`, `disconnect`, `get_status`, `speak`, `play_audio`, `capture_audio`, `get_camera_frame`, `execute_motion`, `execute_timeline`, `set_state`
- `FakeRobotAdapter` simulates all actions without hardware
- `BehaviorEngine` is out of scope for this spec (see 004)
- Events: `RobotConnected`, `RobotDisconnected`, `RobotModeChanged` emitted by robot-runtime
- Test: parameterized contract test in `tests/contract/` runs against FakeRobotAdapter

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Hardware Abstraction | ABC defined before any adapter | ✅ |
| FakeRobot-first | FakeRobotAdapter is complete before spec closes | ✅ |
| Events Drive State | State changes emit events | ✅ |
| Test-Driven Contracts | Contract test exists before PR merges | ✅ |

## Project Structure

```
packages/shared-schemas/src/shared_schemas/
├── robot/
│   ├── __init__.py
│   ├── adapter.py        # RobotAdapter ABC
│   └── models.py         # RobotState, RobotMode, MotionCommand, MotionTimeline

services/robot-runtime/src/robot_runtime/
├── adapters/
│   ├── __init__.py
│   ├── fake.py           # FakeRobotAdapter
│   └── factory.py        # get_adapter(env) → RobotAdapter
├── main.py               # FastAPI routes, WebSocket /ws/events

tests/contract/
└── test_robot_adapter_contract.py   # parametrize over adapters
```

## Implementation Steps

### Phase 1: Define ABC and Models (shared-schemas)

1. `RobotMode` — `StrEnum`: `ONLINE`, `DEGRADED`, `OFFLINE`, `MAINTENANCE`
2. `RobotState` — Pydantic model: `mode`, `behavior_state`, `battery_pct`, `connected`
3. `MotionCommand` — Pydantic model: `motion_id`, `speed`, `amplitude`, `direction`
4. `MotionTimeline` — Pydantic model: `cues: list[MotionCue]` where cue has `offset_ms`, `command`
5. `RobotAdapter` — ABC with all 9 abstract methods and signatures

### Phase 2: FakeRobotAdapter (robot-runtime)

1. `connect()` → sets `_state.connected = True`; emits `RobotConnected`
2. `disconnect()` → sets `_state.connected = False`; emits `RobotDisconnected`
3. `get_status()` → returns current `RobotState`
4. `speak(text)` → logs `[FAKE] Speaking: {text[:50]}...`; emits `SpeechPlaybackStarted`
5. `play_audio(chunk)` → no-op; returns immediately
6. `capture_audio()` → returns 1 second of silence (1600 bytes, 16kHz 16-bit)
7. `get_camera_frame()` → returns a static 320×240 grey PNG (30KB)
8. `execute_motion(cmd)` → logs motion; emits `MotionStarted` then `MotionCompleted`
9. `execute_timeline(timeline)` → iterates cues with `asyncio.sleep(offset_ms / 1000)` 
10. `set_state(state)` → updates `_state`; emits `RobotModeChanged` if mode changed

### Phase 3: REST and WebSocket (robot-runtime)

1. `GET /robot/status` → `adapter.get_status()`
2. `POST /robot/speak` → `adapter.speak(body.text)`
3. `POST /robot/motion` → `adapter.execute_motion(body)`
4. `WebSocket /ws/events` → connected to event bus broadcaster

### Phase 4: Contract Tests

1. `test_robot_adapter_contract.py` — `@pytest.fixture(params=["fake"])` for now
2. Tests: connect, get_status, speak, capture_audio returns bytes, execute_motion emits events, set_state with mode change emits RobotModeChanged

## Complexity Tracking

- Python files: ~10 new files, ~250 lines
- No external dependencies added beyond shared-schemas
