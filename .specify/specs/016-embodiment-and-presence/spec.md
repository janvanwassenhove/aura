---
feature: "016-embodiment-and-presence"
status: "implemented"
owner: "robot-runtime"
priority: P1
risk: Medium
created: "2026-09-05"
units: [U16, U36a, U36d, U36g, U37, U51, U99, U100, U101, U102, U111, U116,
        U126, U127, U137, U138, U139, U147, U157, U158, U161, U162, U164,
        U165, U175, U196, U212, U219, U237, U238, U252b, U252d, U253, U268,
        U270, U286]
---

# Feature Specification: Embodiment and Presence

**Feature Branch**: `016-embodiment-and-presence`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: robot-runtime / aura-brain
**Priority**: P1
**Risk**: Medium — every item here is visible in the room, so a regression is
noticed by whoever is standing in front of it before any test catches it.

## Why this spec exists late

This describes behaviour that shipped across 36 units without ever being
specified. It is written from the code as it stands, not from a plan; where a
decision was made under pressure and is still load-bearing, it says so. The
motivation and the full history of each unit remain in
`docs/implementation-backlog.md`.

## Background

A Reachy Mini has a head on a Stewart platform, a rotating torso, two antennae,
a camera, a speaker and a microphone array. It has no arms. Everything this
robot expresses, it expresses with **where it is looking, how it holds itself,
and how its antennae move** — which makes body language a feature rather than a
decoration, and makes a frozen robot read as a broken one.

Two rules shape everything below:

* **[Constitution II] Nothing above `robot-runtime` may import a Reachy SDK
  type.** `RobotAdapter` is the boundary; `FakeRobot` is the primary target and
  every flow works without hardware.
* **[Constitution X] The Pi is older than the app.** The laptop self-updates,
  the robot is flashed by hand, so the brain routinely talks to a runtime that
  predates it. Any new brain→runtime call goes in its own `try`, must not break
  the sequence around it on a 404, and reports the degradation instead of plain
  success.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — He looks at whoever is talking (Priority: P1)

As someone in the room, I want the robot to turn towards me and keep me in
view, so that talking to it feels like talking to something rather than at it.

**Independent Test**: with `ROBOT_ADAPTER=fake`, publish a face at the edge of
frame; the adapter reports a head pose moving towards it, and `tracking` stays
`true` across the motion.

**Acceptance Scenarios**:

1. **Given** follow-me is on and a face is visible, **When** the face moves,
   **Then** the head follows, and beyond a threshold the **torso** turns too so
   the head does not reach its limit and stop (U37).
2. **Given** follow-me is on and no face has been seen for the watchdog
   interval, **When** the timer expires, **Then** the tracker re-acquires with
   a scan that **holds** at each end rather than sweeping past (U158), and the
   console shows *whether he currently sees a face* — separate from whether
   following is on (U165).
3. **Given** the operator aims the head by dragging on the live picture,
   **When** they do so, **Then** follow-me switches to **Manual** rather than
   fighting the drag (U162), and the drag maps to the picture they are looking
   at rather than the SDK's mirrored frame (U164).
4. **Given** a gesture or a mood expression plays, **When** it finishes,
   **Then** tracking resumes by itself — a gesture is not a reason to stop
   watching the room (U116, U137).
5. **Given** the robot is speaking, **When** it speaks, **Then** it keeps
   following (U81) and adds conversational body language rather than freezing
   into a talking statue (U157).

### User Story 2 — He can be asleep, and stay asleep (Priority: P1)

As the owner, I want a real "take no action" state, so that the robot in the
living room is not a thing that reacts all evening.

**Acceptance Scenarios**:

1. **Given** the robot is awake, **When** the owner presses Sleep, **Then** it
   ducks away and sweeps its antennae back (U101), stops tracking, and stays
   there — the idle behaviours do not wake it four seconds later (U237).
2. **Given** the runtime is older than the app and does not implement the sleep
   route, **When** Sleep is pressed, **Then** the console says the robot did
   not accept it, rather than reporting success (U238). *A 404 that reads as
   "done" is the exact failure constitution X exists to prevent.*
3. **Given** the robot wakes, **When** it wakes, **Then** it comes back upright
   before doing anything else (U36d), and follow-me is restored (U116).
4. **Given** the microphone is switched off, **When** anything is said,
   **Then** nothing is heard and the state is visible in the console (U99).

### User Story 3 — Idle is alive, not motionless (Priority: P2)

**Acceptance Scenarios**:

1. **Given** nothing is happening, **When** time passes, **Then** he looks
   around occasionally and fidgets rather than holding one pose (U36d).
2. **Given** he is waiting for an answer, **When** he waits, **Then** he holds
   a listening/thinking pose so the wait is legible (U147).
3. **Given** a reply is emotionally coloured, **When** it is spoken, **Then**
   head and antennae carry that colour (U111) — mapped by keyword and
   punctuation heuristics in `embodiment.py`, deliberately **without** a second
   model call, because a gesture that arrives after the sentence is worse than
   no gesture.
4. **Given** music is playing, **When** he dances, **Then** the torso is part
   of it (U139) and he can synthesise his own groove when there is no track
   (U138).

### User Story 4 — One pick sets how he looks, moves and sounds (Priority: P1)

As the owner, I want to choose a character and have everything follow from it,
rather than configuring a face, a voice and a motion style separately.

**Acceptance Scenarios**:

1. **Given** ten shipped archetypes, **When** one is selected, **Then** it sets
   the on-screen face, the idle animation, the voice, and the move he opens
   with (`apps/operator-console/src/lib/characters.ts`).
2. **Given** the owner presses "Try a move", **When** they do, **Then** the
   move is **that character's** move, not the same nod for all ten (U252d).
3. **Given** the character is changed while the projector overlay is open,
   **When** it changes, **Then** the overlay follows (U286). *The overlay is a
   separate BrowserWindow with its own Pinia store — the recurring root cause
   of "the other window did not hear about it" (U269, U276, U286, U290); it
   follows through a `storage` event.*
4. **Given** any character, **When** it renders on the projector, **Then** it
   is animated — blinking and gaze drift. U268: all ten were frozen because the
   blink used `ry` on a `<circle>`, which has no such attribute. One wrong
   letter of SVG, ten dead faces, and nothing failed.

### User Story 5 — The picture is live, or it says it is not (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the camera stream drops a single frame, **When** it does, **Then**
   the picture does not blip (U212).
2. **Given** the MJPEG stream loses its server (a brain restart or an update),
   **When** it stalls, **Then** the console remounts it automatically — an
   `<img>` that loses its source stalls **silently**, with no error and no
   retry, which made the camera look dead until a full page reload (U175).
3. **Given** perception is running, **When** frames are processed, **Then**
   they are not transcoded to PNG per consumer; one decode is shared (U219).
4. **Given** the robot connected before the console opened, **When** the
   console opens, **Then** it asks `/robot/status` rather than waiting for a
   `RobotConnected` event that has already been and gone (U152, completed in
   U297 — see [020-desktop-app-and-releases](../020-desktop-app-and-releases/spec.md)).

### User Story 6 — The state it reports is the state it is in (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a robot with no battery (the mains-powered version), **When**
   status is shown, **Then** it says *mains powered*, not 100%. U270: the
   adapter hard-coded `100.0` with the comment "SDK exposes no battery reading
   yet", so the wizard printed a full battery that nothing had measured. A full
   battery is the most reassuring thing a status line can say, which makes it
   the worst thing to invent. Three states: a number, "no battery", "not
   reported by this firmware".
2. **Given** follow-me is on but the tracker thread has died, **When** status
   is read, **Then** it does not report healthy tracking (U253).
3. **Given** the app is newer than the runtime, **When** a new call 404s,
   **Then** the surrounding sequence still completes and the degradation is
   reported (U196, U238).

## Functional Requirements

- **FR-001**: All robot interaction goes through `RobotAdapter`
  (`packages/shared-schemas/src/shared_schemas/robot/adapter.py`). `FakeRobot`
  and `ReachyRobotAdapter` pass the same contract tests.
- **FR-002**: Head tracking, torso yaw, gestures, dances, poses and the sleep
  pose are adapter concerns; the brain asks for a named motion and never for
  joint angles.
- **FR-003**: `tracking` and `face_visible` are distinct, both reported in
  `/robot/status`, and the robot — not the console — is the source of truth for
  both (U162, U165).
- **FR-004**: `battery_pct` is `null` when unmeasured; `has_battery` is `null`
  when unknown. Neither is ever substituted with a plausible number.
- **FR-005**: A character selects face, idle animation, voice and opening move
  as one choice, and every window showing the robot honours the same selection.
- **FR-006**: Gesture selection from reply text is heuristic and synchronous —
  no model call on the speech path.
- **FR-007**: Every new brain→runtime call tolerates a 404 from an older Pi and
  reports the degradation.

## Out of scope

- Arms. This robot has none, and no part of the system pretends otherwise.
- The projector overlay's presentation role — see
  [011-presentation-copilot](../011-presentation-copilot/spec.md).
- Face recognition and who the person is — see
  [018-knowledge-people-and-judgment](../018-knowledge-people-and-judgment/spec.md).

## Traceability

| Units | What they delivered |
|---|---|
| U16, U36a | `ReachyRobotAdapter` live-verified on hardware; live video in the console |
| U36d, U147, U157, U111 | Idle look-around, upright after wake, listening pose, conversational body language, mood via head and antennae |
| U37, U36g, U116, U126, U127, U158, U165, U253 | Follow-me: torso yaw, watchdog, re-acquire that holds, face-visible reporting, and a tracker that was dead rather than blind |
| U161, U162, U164 | Drag-to-aim on the live picture; explicit Follow/Manual; the mirrored-axis fix |
| U99, U100, U101, U102, U237, U238 | Microphone toggle; sleep and wake; the sleep pose; sleep that stays; the 404 that read as success |
| U137, U138, U139 | Quick actions that are not swallowed by a tracking conflict; dance, including the torso and a synthesised groove |
| U51 | Mode behaviour profiles — embodiment follows the active persona |
| U252d, U268, U286 | Per-character move; the one-letter SVG bug that froze all ten faces; the overlay following the character choice |
| U175, U212, U219, U196 | Camera: silent MJPEG stall, single-frame blips, shared frame decode, and a live view against an older robot |
| U270 | Battery, in the three states it can actually be in |
| U252b | The title bar belongs to the app; the hand on the camera |
