---
feature: "016-embodiment-and-presence"
status: "implemented"
owner: "robot-runtime"
priority: P1
risk: Medium
created: "2026-09-05"
units: [U16, U36a, U36d, U36g, U37, U51, U99, U100, U101, U102, U111, U116, U126, U127, U137, U138, U139, U147, U157, U158, U161, U162, U164, U165, U175, U196, U212, U219, U237, U238, U252b, U252d, U253, U268, U270, U286, U325, U326, U328, U336, U341, U341b, U357, U357b, U359]
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
6. **Given** the daemon's tracker has no face but the camera frame does,
   **When** the recogniser processes that frame, **Then** the brain nudges the
   head toward the person it found — a second, slow tracker that earns its keep
   exactly when the fast one has lost you or has died (U325, U253).
7. **Given** somebody was in view and walks out of it, **When** the tracker
   drops them, **Then** he looks again within seconds rather than waiting out
   the empty-room sweep interval; and **Given** nobody has been seen for a long
   while, **Then** the cadence relaxes again, because a robot sweeping the room
   every few seconds all evening is its own kind of broken (U325).

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
3. **Given** the owner is about to pick him up and travel with him, **When**
   they look for sleep, **Then** it is in "Ask him to…" beside the gestures —
   as two plain instructions ("go to sleep", "wake up") that show which one he
   is in, at every density. They are not motions: a motion would lower the head
   and leave the motors live (U341).
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

### User Story 7 — He is in the conversation, not beside it (Priority: P2)

As someone talking to him, I want him to react while I am speaking and to move
while he is speaking, so that a conversation looks like a conversation.

**Acceptance Scenarios**:

1. **Given** a streaming engine (realtime session or GPT-Live) and somebody
   talking to him, **When** their speech is detected, **Then** he acknowledges
   with a small, paced cue for as long as they keep talking, and stops when
   they stop (U326).
2. **Given** he is answering, **When** his reply comes back as a stream,
   **Then** he moves with what he is saying — the same keyword heuristic the
   typed path uses — about once per reply, never once per transcript delta
   (U326). Before this, the streamed paths commanded **no** motion at all: the
   head sway during speech is the SDK reacting to audio levels and knows
   nothing about the words (U157).
3. **Given** any conversational cue, **When** it plays, **Then** it is one of
   the motions that keep follow-me alive, and it is never awaited on the speech
   path — a gesture that arrives after the sentence is worse than none (U326).
5. **Given** a reaction inside somebody else's sentence, **When** it plays,
   **Then** it is carried by the **antennae** wherever it can be: they cost no
   eye contact, cannot fight the face tracker, and put no motor noise from the
   head platform next to the microphone that is hearing that sentence (U147's
   reason, U328). When head and antennae move together they do so in **one**
   command — two would serialise on the motion lock and read as two events.
6. **Given** the tone of a reply, **When** the body expresses it, **Then** the
   head gesture and the antenna cue read the **same** classification, so the
   two cannot drift into disagreeing about the same sentence (U328).
4. **Given** the pipeline path, **When** somebody speaks, **Then** the
   acknowledgement stays the wake nod (U275) and the thinking pose (U147). It
   records fixed windows and only measures afterwards whether they contained
   speech, so there is no mid-sentence signal to answer — an absence by
   construction, recorded here so it is not mistaken for an oversight (U326).

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
- **FR-013**: The brain follows the robot's address. It is watched, not read
  once: when it stops answering, the brain tries the address it has, then
  `reachy-mini.local`, then every host on its own /24 — the bound U200 set —
  and adopts the first that answers **like a robot** (`/health` with a robot
  body; an open port is not proof). Adoption takes the same three steps as the
  manual button, once per move. `ROBOT_AUTOFIND=false` turns it off. It cannot
  put him on a network he is not on: that stays a one-time job at the robot
  (U336).
- **FR-007**: Every new brain→runtime call tolerates a 404 from an older Pi and
  reports the degradation.
- **FR-008**: Pointing the head comes in two kinds, and they are not
  interchangeable. `aim` is a takeover: it pauses follow-me on purpose, because
  the console joystick may not be fought by the tracker (U161). `gaze` is a
  **nudge**: relative to where he is already looking, it leaves follow-me on,
  and it declines — saying which — when follow-me is off, when the daemon's
  tracker holds a face, or when a motion is running. Two controllers never
  drive the same joint at the same time, and the daemon's tracker wins whenever
  it has a lock (U325).
- **FR-009**: The face position comes from the recognition pass that already
  decoded the frame — never a second detection — as an offset from the centre
  of the picture, in the same operator frame as `aim` (+x right, +y down).
  Nudges below a deadzone are not sent: chasing detection noise reads as a
  twitch, not as attention. The nearest face is the one he turns to, the same
  one recognition treats as the person he is talking to (U288, U325).
- **FR-012**: The antennae are a first-class channel, not decoration:
  `perk`, `flick`, `droop` and `alert` are antenna-only; `acknowledge` moves
  head and antennae in a single command and is deliberately smaller than a
  deliberate `nod`, because it lands inside someone else's sentence. A reply's
  tone is classified once (`embodiment.tone_for`) and both channels read it
  (U328).
- **FR-011**: Conversational body language is rate-limited, tracking-preserving
  and never awaited. `BACKCHANNEL_MIN_S` bounds how often he acknowledges a
  speaker; `TALK_GESTURE_MIN_S` bounds how often he gestures inside one reply;
  both draw only from the runtime's follow-gesture set, so no cue costs eye
  contact. The reply gesture on the typed path is **started**, not awaited: it
  used to be awaited before synthesis even began, which added its whole
  duration to every answer — a move, a silence, then a voice (U326).
- **FR-010**: The re-acquire sweep follows the room: nothing while a face is in
  view, `IDLE_SCAN_LOST_S` after one was just lost, `IDLE_SCAN_S` once nobody
  has been seen for `IDLE_SCAN_RECENT_S` (U325). The sweep leaves the head
  centred and resets the nudge origin, so the next nudge starts from the pose
  the head is actually in.

## Out of scope

- Arms. This robot has none, and no part of the system pretends otherwise.
- The projector overlay's presentation role — see
  [011-presentation-copilot](../011-presentation-copilot/spec.md).
- Face recognition and who the person is — see
  [018-knowledge-people-and-judgment](../018-knowledge-people-and-judgment/spec.md).

- **FR-041**: Going to sleep never commands the head upright. Turning follow-me
  off recentres the head (U165) so an awake robot does not sit staring at the
  last place it saw a face; the brain's sleep sequence turns follow-me off on
  its way to the sleep pose, so lowering him included an explicit
  `goto_target(head=NEUTRAL, duration=1.0)` issued immediately before
  `goto_sleep()` — and on the real robot the two overlap, so the head-up move
  lands *after* the emote. Reported as *"went down in the shell/torso, but once
  this was finished, the head jumped back up"*. The recentre is now skipped
  while `sleep_state.is_asleep()`, which is U237's rule applied where it was
  missed: sleep means take no action of your own, and lifting the head is such
  an action. Tracking is still paused — this is about the pose, not the tracker
  (U357). The suppression lasts exactly as long as the sleep: boot starts
  following (a fresh runtime is never asleep), the wake sequence gives follow-me
  back, and once awake the U165 recentre returns. All three are pinned, because
  a suppression that outlived its sleep would be a robot that wakes up and never
  looks at anyone again (U357b).

- **FR-042**: A line that fails to play must not cost the robot its voice.
  `BehaviorEngine.speak()` transitions to SPEAKING, plays, and transitions back
  to IDLE — and `SPEAKING → SPEAKING` is not a legal transition, so a playback
  that raised used to leave the engine stuck in SPEAKING and every later line
  answered `500`. The state is restored in a `finally`, and
  `SpeechPlaybackCompleted` is published there too: it means *no longer
  playing*, not *played well*, and a start with no completion is a subtitle
  that never clears. The failure itself still propagates — the caller must hear
  that the line was not said (U269) — it is only the state that may not survive
  it (U359).
- **FR-043**: `POST /robot/speak` answers with a **reason**. An unhandled
  exception became a bare 500, which mid-talk read as *"Server error '500
  Internal Server Error' … For more information check: developer.mozilla.org"*.
  The route answers 503 with the cause attached ("he could not, right now",
  not "that request was wrong"), and the brain's `RobotClient` puts that reason
  into the error it raises instead of httpx's status-and-a-link — keeping the
  `HTTPStatusError` type and its response, because callers branch on
  `status_code == 404` (U359).

## Traceability

| Units | What they delivered |
|---|---|
| U16, U36a | `ReachyRobotAdapter` live-verified on hardware; live video in the console |
| U36d, U147, U157, U111 | Idle look-around, upright after wake, listening pose, conversational body language, mood via head and antennae |
| U37, U36g, U116, U126, U127, U158, U165, U253 | Follow-me: torso yaw, watchdog, re-acquire that holds, face-visible reporting, and a tracker that was dead rather than blind |
| U161, U162, U164 | Drag-to-aim on the live picture; explicit Follow/Manual; the mirrored-axis fix |
| U359 | One failed line left him mute for the rest of the talk — the state now comes back whatever the audio does, and a 500 says what broke |
| U357b | Follow-me checked on both paths that matter — boot and wake — before the fix went to the Pi |
| U357 | Sleep stopped lifting his head on the way down — the recentre that follow-me-off owes an awake robot |
| U99, U100, U101, U102, U237, U238 | Microphone toggle; sleep and wake; the sleep pose; sleep that stays; the 404 that read as success |
| U341 | Sleep and wake asked for like any other action, where you pack him rather than where you configure him |
| U341b | That marker rendered green on green — the app's own `--accent-wash` treatment, seen by looking at it |
| U137, U138, U139 | Quick actions that are not swallowed by a tracking conflict; dance, including the torso and a synthesised groove |
| U51 | Mode behaviour profiles — embodiment follows the active persona |
| U252d, U268, U286 | Per-character move; the one-letter SVG bug that froze all ten faces; the overlay following the character choice |
| U175, U212, U219, U196 | Camera: silent MJPEG stall, single-frame blips, shared frame decode, and a live view against an older robot |
| U270 | Battery, in the three states it can actually be in |
| U336 | The brain follows the robot to a new network instead of reporting offline until somebody scans by hand |
| U328 | Antenna reactions: an antenna-led vocabulary, head-and-antennae in one command, and one tone classification feeding both |
| U326 | Conversational body language both ways: acknowledging while someone speaks, moving with what he says, and a reply gesture that no longer delays the reply |
| U325 | `gaze`: looking at someone without taking follow-me away; the face position the recogniser already had; a sweep whose cadence follows the room |
| U252b | The title bar belongs to the app; the hand on the camera |
