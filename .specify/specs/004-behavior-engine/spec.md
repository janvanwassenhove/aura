---
feature: "004-behavior-engine"
status: "in-progress"
owner: "robot-runtime"
priority: P1
risk: Medium
created: "2026-04-25"
---

# Feature Specification: Behavior Engine

**Feature Branch**: `004-behavior-engine`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: robot-runtime
**Priority**: P1
**Risk**: Medium

## User Scenarios & Testing

### User Story 1 — Idle Behavior Runs Continuously When Not Speaking (Priority: P1)

When AURA is not speaking or processing a request, it exhibits subtle idle motions (head micropan, breathing LED pattern) to appear attentive and alive.

**Why this priority**: A robot that freezes when not speaking is unsettling. Idle behavior is core to the embodied presence value proposition.

**Independent Test**: Start `robot-runtime` with FakeRobot; verify `MotionStarted` events for idle_micropan fire every 3-5 seconds.

**Acceptance Scenarios**:

1. **Given** FakeRobot is CONNECTED and no speech or motion is active, **When** 3 seconds pass, **Then** an `idle_micropan` motion event is emitted.
2. **Given** FakeRobot is in IDLE state, **When** `speak()` is called, **Then** idle motion stops immediately, speech starts, and idle resumes after speech completes.
3. **Given** FakeRobot mode is OFFLINE, **When** idle should fire, **Then** no motion events are emitted.

---

### User Story 2 — Speech and Motion Are Synchronized via Timelines (Priority: P1)

AURA speaks and moves simultaneously using a coordinated timeline. Speech audio and motion keyframes are synchronized so gestures accompany speech naturally.

**Why this priority**: Synchronization is what separates an embodied assistant from a speaker. Without it the product premise fails.

**Independent Test**: Call `create_speaking_timeline("Hello, I am AURA")` and assert the returned `MotionTimeline` has a `nod_start` step at t=0ms and a `gaze_forward` step at the end.

**Acceptance Scenarios**:

1. **Given** a speech text, **When** `create_speaking_timeline(text)` is called, **Then** a `MotionTimeline` is returned with gesture steps correlated to sentence structure.
2. **Given** a `MotionTimeline`, **When** `execute_timeline()` is called on FakeRobot, **Then** `SpeechPlaybackStarted` and `MotionStarted` events are emitted within 50ms of each other.
3. **Given** speech is interrupted, **When** `interrupt()` is called on the behavior engine, **Then** the ongoing timeline is cancelled and AURA returns to listening state.
4. **Given** two consecutive speak calls, **When** the first is still in flight, **Then** the second is queued and begins immediately after the first completes.

---

### User Story 3 — Behavior States Transition Correctly (Priority: P1)

The behavior engine transitions cleanly between IDLE, LISTENING, THINKING, SPEAKING, and RESPONDING states, emitting events at each transition.

**Why this priority**: Correct state transitions prevent motion/speech conflicts and are visible to the operator console.

**Independent Test**: Drive the engine through IDLE → LISTENING → THINKING → SPEAKING → IDLE and assert all 4 `BehaviorStateChanged` events are emitted in order.

**Acceptance Scenarios**:

1. **Given** AURA is in IDLE state, **When** `AudioInputStarted` event is received, **Then** behavior engine transitions to LISTENING and emits `BehaviorStateChanged`.
2. **Given** AURA is in LISTENING state, **When** `IntentRecognized` event is received, **Then** behavior engine transitions to THINKING.
3. **Given** AURA is in THINKING state, **When** `ResponseDrafted` event is received, **Then** behavior engine transitions to SPEAKING and invokes `create_speaking_timeline()`.
4. **Given** AURA is in SPEAKING state, **When** speech completes, **Then** behavior engine returns to IDLE.
5. **Given** any non-OFFLINE state, **When** `RobotModeChanged(mode=OFFLINE)` is received, **Then** behavior engine transitions to IDLE and stops all motion.

---

### User Story 4 — Gesture Map is Configurable per Persona (Priority: P2)

Each persona (work, home, demo) has a different gesture intensity and style. Work mode uses minimal gestures; demo mode uses expressive gestures.

**Why this priority**: Persona-based behavior differentiation is a product differentiator. Medium priority because the gesture map can start with defaults.

**Independent Test**: Instantiate engine with work persona; call `create_speaking_timeline("Hello")` and assert head_tilt amplitude is < 10 degrees.

**Acceptance Scenarios**:

1. **Given** persona=work, **When** `create_speaking_timeline()` is called, **Then** gesture amplitudes are ≤ 50% of demo persona amplitudes.
2. **Given** persona=demo, **When** `create_speaking_timeline()` is called, **Then** at least 2 distinct gesture types appear in the timeline.
3. **Given** persona changes from work to home, **When** the next speech begins, **Then** the new persona's gesture profile is used.

---

### Edge Cases

- What happens if a gesture motion fails mid-timeline? → Log warning, continue remaining timeline steps; emit `MotionFailed` event.
- What happens if the behavior engine receives two state change events simultaneously? → Serialize via asyncio queue; process in order.
- What happens if `create_speaking_timeline()` is called with empty text? → Return an empty timeline with only a `gaze_forward` step.

---

## Requirements

### Functional Requirements

- **FR-001**: `BehaviorEngine` MUST expose: `plan_behavior()`, `create_idle_behavior()`, `create_listening_behavior()`, `create_thinking_behavior()`, `create_speaking_timeline(text)`.
- **FR-002**: `BehaviorEngine` MUST subscribe to: `AudioInputStarted`, `UserSpeechDetected`, `IntentRecognized`, `ResponseDrafted`, `RobotModeChanged`.
- **FR-003**: `BehaviorEngine` MUST emit `BehaviorStateChanged` at every state transition.
- **FR-004**: Idle behavior MUST fire at a configurable interval (default: 4 seconds) when no other behavior is active.
- **FR-005**: `create_speaking_timeline(text)` MUST return a `MotionTimeline` with at least one gesture step per sentence.
- **FR-006**: Timeline execution MUST be cancellable via `interrupt()` without leaving the robot in mid-motion.
- **FR-007**: Gesture map MUST be configurable per persona via a YAML or Pydantic config.
- **FR-008**: `BehaviorEngine` MUST NOT import Reachy SDK types directly.

### Key Entities

- **BehaviorEngine**: Stateful asyncio service subscribing to events and issuing timeline commands.
- **BehaviorState**: Enum — IDLE, LISTENING, THINKING, SPEAKING, RESPONDING.
- **GestureMap**: Per-persona mapping of speech patterns → motion keyframes.
- **MotionTimeline**: Ordered list of MotionCommand with timing offsets (from `shared_schemas`).

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: All 5 behavior state transitions are covered by tests.
- **SC-002**: `create_speaking_timeline()` returns a timeline within 20ms for texts up to 500 characters.
- **SC-003**: Idle motion fires every 3-5 seconds ±500ms in a 30-second test run.
- **SC-004**: Speech + motion timeline synchronization delta ≤ 100ms (measured by event timestamp).
- **SC-005**: All gesture maps for 3 personas (work, home, demo) are defined and tested.

---

## Assumptions

- Gesture keyframes for FakeRobot are simulated and do not require physical motion data.
- Speech duration estimation is based on word count (≈150ms per word) until real TTS duration is available.
- The gesture map YAML is bundled with `robot-runtime` service, not an external dependency.
- Timeline cancellation is cooperative — motion steps check for cancellation before starting.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle II (Hardware Abstraction), Principle III (Events Drive State)
- [ADR-003](docs/adr/ADR-003-robot-adapter-abstraction.md)
- [Spec 002 — FakeRobot](../002-fakerobot-simulation/spec.md)
- [Spec 003 — Event Bus](../003-event-bus-schemas/spec.md)
