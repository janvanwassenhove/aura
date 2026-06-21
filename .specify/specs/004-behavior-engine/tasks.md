# 004 — Behavior Engine: Task List

Format: `[ID] [P?] [US-N] Description`

User Story refs:
- US-1: Idle behavior plays automatically
- US-2: Speech + motion synchronized in timelines
- US-3: State transitions logged and visible
- US-4: Per-persona gesture maps

## Phase 0: Prereqs (specs 001, 002, 003 required)

- [x] `T001` Verify `RobotAdapter` ABC exists with all 9 methods
- [x] `T002` Verify all behavior event models exist (`BehaviorStateChanged`, `BehaviorPlanned`, etc.)
- [x] `T003` Verify `AsyncEventBus` is complete with `create_task` dispatch

## Phase 1: BehaviorState and Transitions (shared-schemas)

- [x] `T004` [US-3] Confirm `BehaviorState(StrEnum)` exists in `shared_schemas.robot.models`
- [x] `T005` [US-3] `services/robot-runtime/src/robot_runtime/behavior/states.py` ✓
  - `VALID_TRANSITIONS`, `is_valid_transition()`, `TransitionBlockedError` created

## Phase 2: GestureProfile (shared-personas)

- [x] `T006` [US-4] `packages/shared-personas/src/shared_personas/models.py` — `GestureProfile`, `Persona`, `PersonaConfig` ✓
- [x] `T007` [US-4] `packages/shared-personas/src/shared_personas/configs.py` — 5 persona configs ✓
- [x] `T008` [US-4] `packages/shared-personas/src/shared_personas/__init__.py` — `get_persona_config()` ✓

## Phase 3: Timeline Builder

- [x] `T009` [US-2] `services/robot-runtime/src/robot_runtime/behavior/timeline_builder.py` ✓
  - `create_speaking_timeline()` extracted; 250ms/word; `create_idle_timeline()` extracted

## Phase 4: Idle Behavior Generator

- [x] `T010` [US-1] `create_idle_timeline()` in `behavior/timeline_builder.py` ✓
  - Idle timeline logic extracted (spec named `idle.py`; implemented in `timeline_builder.py` per plan)

## Phase 5: BehaviorEngine Core

- [x] `T011` [US-1] [US-2] [US-3] `services/robot-runtime/src/robot_runtime/engine/behavior.py`
  - Note: path is `engine/behavior.py` not `behavior/engine.py` as specified
  - `BehaviorEngine` class with `start()`, `stop()`, `transition()`, `speak()` ✓
  - Idle fidget loop runs as background task ✓
  - Emits `BehaviorStateChanged`, `BehaviorPlanned`, `SpeechPlaybackStarted/Completed`, motion events ✓
  - Bus event subscriptions added in `start()`: `AudioInputStarted`, `UserSpeechDetected`, `ResponseDrafted`, `RobotModeChanged` ✓

## Phase 6: Wire BehaviorEngine into robot-runtime main

- [x] `T012` [US-1] `BehaviorEngine` and `AsyncEventBus` wired in `main.py` lifespan ✓

## Phase 7: Tests

- [x] `T013` [US-3] `services/robot-runtime/tests/test_behavior_engine.py` ✓ — 6 tests pass
- [x] `T014` [US-2] `services/robot-runtime/tests/test_timeline_builder.py` ✓ — 7 tests pass
- [x] `T015` [US-4] `services/robot-runtime/tests/test_persona_configs.py` ✓ — 6 tests pass

## Phase 8: CI Gate

- [x] `T016` Run full robot-runtime test suite: `pytest services/robot-runtime/tests/ -v` — 26 passed ✓

## Acceptance Criteria (from spec.md)

- BehaviorState transitions following stimulus events verified by tests
- MAINTENANCE mode blocks all transitions
- Timeline cue count scales with word count
- `silent_desk` persona produces empty timeline
- All 5 persona configs defined and accessible
