---
feature: "002-fakerobot-simulation"
status: "in-progress"
owner: "robot-runtime"
priority: P1
risk: Low
created: "2026-04-25"
---

# Feature Specification: FakeRobot Simulation

**Feature Branch**: `002-fakerobot-simulation`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: robot-runtime
**Priority**: P1
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — FakeRobot Implements Full RobotAdapter Contract (Priority: P1)

A developer can run all assistant flows — speech, motion, camera, audio — using the FakeRobot adapter without any physical hardware present.

**Why this priority**: All other services (conversation, orchestrator, behavior engine) depend on a working robot adapter. FakeRobot unblocks the entire development stack.

**Independent Test**: `pytest tests/contract/test_robot_adapter_contract.py --adapter=fake` passes with 100% success.

**Acceptance Scenarios**:

1. **Given** FakeRobot is instantiated, **When** `connect()` is called, **Then** the adapter transitions to CONNECTED state and emits `RobotConnected` event.
2. **Given** a connected FakeRobot, **When** `speak("Hello world")` is called, **Then** the text is logged to stdout, a `SpeechPlaybackStarted` event is emitted, and the method completes without error.
3. **Given** a connected FakeRobot, **When** `execute_motion(MotionCommand(name="nod"))` is called, **Then** a `MotionStarted` event is emitted, the command is logged, and a `MotionCompleted` event is emitted after completion.
4. **Given** a connected FakeRobot, **When** `get_camera_frame()` is called, **Then** a non-empty bytes object (static PNG) is returned without error.
5. **Given** a connected FakeRobot, **When** `capture_audio()` is called, **Then** a bytes object representing silence is returned.
6. **Given** a connected FakeRobot, **When** `disconnect()` is called, **Then** the adapter transitions to DISCONNECTED state and emits `RobotDisconnected`.
7. **Given** a connected FakeRobot, **When** `get_status()` is called, **Then** a `RobotState` object with all fields populated is returned.

---

### User Story 2 — Operator Console Displays FakeRobot State (Priority: P1)

The operator console shows FakeRobot's current state, recent speech output, and motion log entries in real time.

**Why this priority**: Required for the developer inner loop — need visual feedback that FakeRobot is responding correctly.

**Independent Test**: Start FakeRobot + operator console; call `speak("test")` via REST; console shows the text in the transcript panel within 500ms.

**Acceptance Scenarios**:

1. **Given** the operator console is open and FakeRobot is running, **When** `speak()` is called, **Then** the text appears in the transcript panel.
2. **Given** the operator console is open, **When** a motion command executes, **Then** the motion log panel shows the command name, timestamp, and status.
3. **Given** FakeRobot state is DEGRADED, **When** the console updates, **Then** the robot state panel shows the DEGRADED badge.

---

### User Story 3 — Automated Tests Cover FakeRobot Behavior (Priority: P1)

A CI pipeline can run all FakeRobot tests without hardware and without network access.

**Why this priority**: Ensures regressions are caught immediately when adapter interface changes.

**Independent Test**: `cd services/robot-runtime && uv run pytest tests/unit/test_fake_robot.py tests/contract/` returns 0 exit code.

**Acceptance Scenarios**:

1. **Given** the test suite, **When** run in a clean environment with no hardware, **Then** all tests pass.
2. **Given** FakeRobot tests, **When** `execute_timeline()` is called with a multi-step timeline, **Then** events are emitted in order with correct timing.
3. **Given** FakeRobot tests, **When** `set_state(RobotMode.OFFLINE)` is called, **Then** subsequent capability calls raise `RobotUnavailableError`.

---

### Edge Cases

- What happens when `speak()` is called while already speaking? → Speech is queued; `SpeechPlaybackStarted` is emitted for each chunk.
- What happens when `execute_motion()` is called with an unknown motion name? → Logs a warning; emits `MotionCompleted` with `status=unknown`; does not raise.
- What happens when `get_camera_frame()` is called and no static image is configured? → Returns a 1x1 white PNG bytes object.

---

## Requirements

### Functional Requirements

- **FR-001**: `FakeRobotAdapter` MUST implement all methods of `RobotAdapter` ABC.
- **FR-002**: `speak(text)` MUST log the text to stdout and emit `SpeechPlaybackStarted` event.
- **FR-003**: `execute_motion(cmd)` MUST log the command and emit `MotionStarted` + `MotionCompleted` events.
- **FR-004**: `get_camera_frame()` MUST return valid PNG bytes (static test image or 1×1 white pixel).
- **FR-005**: `capture_audio()` MUST return valid PCM silence bytes of configurable duration.
- **FR-006**: `play_audio(chunk)` MUST log audio chunk metadata (size, format) without playing sound.
- **FR-007**: `connect()` / `disconnect()` MUST update internal state and emit corresponding events.
- **FR-008**: `execute_timeline(timeline)` MUST execute steps sequentially, emitting events per step.
- **FR-009**: `set_state(mode)` MUST update robot mode and emit `RobotModeChanged` event.
- **FR-010**: FakeRobot MUST expose a REST endpoint and WebSocket for remote control from the operator console.

### Key Entities

- **RobotAdapter**: ABC defining the 9-method contract.
- **FakeRobotAdapter**: Concrete in-memory simulation implementation.
- **RobotState**: Pydantic model — mode, connected, speak_active, motion_active, last_motion, uptime.
- **MotionCommand**: Pydantic model — name, params, duration_hint.
- **MotionTimeline**: List of `MotionCommand` with timing offsets.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: `pytest tests/contract/test_robot_adapter_contract.py --adapter=fake` passes 100%.
- **SC-002**: `pytest tests/unit/test_fake_robot.py` passes 100% in under 5 seconds.
- **SC-003**: All 9 `RobotAdapter` methods have at least one passing test.
- **SC-004**: FakeRobot can handle 100 sequential `speak()` calls without memory growth > 10MB.
- **SC-005**: Motion timeline with 10 steps executes and emits all 20 events (10× start + 10× complete).

---

## Assumptions

- No audio hardware is required — `capture_audio()` returns synthetic silence.
- No display is required — `get_camera_frame()` returns a static bytes object.
- FakeRobot runs in the same process as the `robot-runtime` FastAPI app.
- Physical Reachy hardware integration is explicitly out of scope for this feature.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle II (Hardware Abstraction)
- [ADR-003](docs/adr/ADR-003-robot-adapter-abstraction.md)
- [RobotAdapter ABC](services/robot-runtime/src/robot_runtime/adapters/base.py)
