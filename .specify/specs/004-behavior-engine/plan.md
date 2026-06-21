---
spec: "004-behavior-engine"
status: draft
created: 2025-01-01
---

# 004 — Behavior Engine: Implementation Plan

## Summary

Implement `BehaviorEngine` in `robot-runtime`. It subscribes to orchestrator and conversation events, plans synchronized motion+speech timelines, and drives the robot through its 5 behavior states.

## Technical Context

- `BehaviorState` enum: `IDLE`, `LISTENING`, `THINKING`, `SPEAKING`, `RESPONDING`
- `BehaviorEngine` subscribes to: `AudioInputStarted`, `IntentRecognized`, `ResponseDrafted`, `RobotModeChanged`
- `BehaviorEngine` calls `adapter.execute_timeline()` for speech and motion coordination
- Per-persona gesture profiles loaded from `shared-personas`
- Emits: `BehaviorStateChanged`, `BehaviorPlanned`, `SpeechPlaybackStarted`, `MotionStarted`, `MotionCompleted`

## Constitution Check

| Principle | Gate | Status |
|-----------|------|--------|
| Hardware Abstraction | BehaviorEngine only calls `RobotAdapter` methods | ✅ |
| Events Drive State | All state changes emit `BehaviorStateChanged` | ✅ |
| Safety Gates | MAINTENANCE mode blocks all behavior plans | ✅ |
| Simplicity | No LLM calls — motion rules are deterministic | ✅ |

## Project Structure

```
services/robot-runtime/src/robot_runtime/
├── behavior/
│   ├── __init__.py
│   ├── engine.py          # BehaviorEngine
│   ├── states.py          # BehaviorState enum, transition rules
│   ├── idle.py            # Idle motion generators
│   └── timeline_builder.py # create_speaking_timeline(text, persona)
```

## Implementation Steps

### Phase 1: BehaviorState and Transitions

```python
class BehaviorState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    RESPONDING = "responding"
```

Valid transitions:
- `IDLE → LISTENING` on `AudioInputStarted`
- `LISTENING → THINKING` on `UserSpeechDetected`
- `THINKING → SPEAKING` on `ResponseDrafted`
- `SPEAKING → RESPONDING` after speech completes
- `RESPONDING → IDLE` after response actions complete
- Any → `IDLE` on `RobotModeChanged` to OFFLINE or MAINTENANCE

### Phase 2: BehaviorEngine Core

```python
class BehaviorEngine:
    def __init__(self, adapter: RobotAdapter, bus: AsyncEventBus, persona: Persona)
    async def start(self) -> None       # subscribe to bus events
    async def stop(self) -> None        # unsubscribe
    async def plan_behavior(self) -> None
    async def _transition(self, new_state: BehaviorState) -> None
    async def interrupt(self) -> None   # → IDLE immediately
```

### Phase 3: Timeline Builder

`create_speaking_timeline(text, persona) → MotionTimeline`

Rules (deterministic, no LLM):
- One motion cue per ~8 words in text (minimum 1)
- Motion amplitude from `persona.gesture_profile.amplitude`
- Offset 0ms for first cue; subsequent cues at `word_count / 2 * 100ms` intervals
- All cues use `motion_id = "nod"` for work/home; `"gesture"` for demo

### Phase 4: Idle Behavior Generator

- `create_idle_behavior()` — returns a `MotionTimeline` with 2 gentle "rest" cues
- Triggered by `asyncio.create_task` every `IDLE_INTERVAL_SECONDS` while in `IDLE` state
- Cancelled immediately when transitioning out of `IDLE`

### Phase 5: Tests

1. `test_transition_idle_to_listening` — `AudioInputStarted` event triggers state change
2. `test_maintenance_blocks_transitions` — no state change when mode is MAINTENANCE
3. `test_speaking_timeline_has_cues` — short text produces at least 1 cue; long text produces more
4. `test_idle_timer_cancelled_on_transition` — idle task cancelled on `AudioInputStarted`
5. `test_interrupt_returns_to_idle` — `interrupt()` transitions to IDLE from any state

## Complexity Tracking

- Python files: ~6 files, ~300 lines
- No external dependencies beyond shared-schemas and shared-events
