---
feature: "016-embodiment-and-presence"
---

# Tasks: Embodiment and Presence

Retro-specified. Every task below is **done**; the list exists so the spec's
requirements can be traced to the units that satisfied them.

## Phase 1: The boundary

- [x] T001 `RobotAdapter` ABC + `FakeRobot` (spec 002) — the primary target
- [x] T002 [U16] `ReachyRobotAdapter`, live-verified on the physical robot
- [x] T003 [U196] Tolerate a runtime older than the app on every new call

## Phase 2: Looking at people

- [x] T004 [U36g] Head tracking from the perception loop
- [x] T005 [U37] Body-yaw follow — the torso turns before the head runs out
- [x] T006 [U126, U127] Watchdog + per-person recognition snapshots
- [x] T007 [U158] Re-acquire scan that holds at each end; sway yaw
- [x] T008 [U162] Explicit Follow/Manual; the robot owns the state
- [x] T009 [U161, U164] Drag-to-aim on the live picture, in the operator's frame
- [x] T010 [U165] Report `face_visible` separately from `tracking`
- [x] T011 [U116, U137, U253] Tracking survives gestures; a dead tracker is not reported as healthy

## Phase 3: Awake, asleep, alive

- [x] T012 [U99, U100] Microphone toggle; sleep/wake as a real "take no action"
- [x] T013 [U101, U102] Sleep pose, then the SDK's own `goto_sleep()`
- [x] T014 [U237] Idle behaviour no longer wakes a sleeping robot
- [x] T015 [U238] A 404 from an older runtime is reported, not reported as success
- [x] T016 [U36d, U147, U157, U111] Idle look-around, upright after wake, listening pose, body language, mood
- [x] T017 [U51] Gesture profile per persona/mode
- [x] T018 [U137, U138, U139] Quick actions, dance, torso, synthesised groove

## Phase 4: Character

- [x] T019 [U252d] "Try a move" plays that character's move
- [x] T020 [U268] Idle animation for all ten archetypes (the `ry`/`r` SVG bug)
- [x] T021 [U286] The projector overlay follows the character choice across windows

## Phase 5: The picture

- [x] T022 [U36a] Live robot video in the console
- [x] T023 [U175] Auto-remount a silently stalled MJPEG stream
- [x] T024 [U212] Survive a single dropped frame
- [x] T025 [U219] Stop transcoding to PNG per consumer; share the decode
- [x] T026 [U270] Battery in three honest states
- [x] T027 [U252b] App-owned title bar; the hand on the camera
