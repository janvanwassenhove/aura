---
feature: "023-wandering"
status: "in-progress"
owner: "robot-runtime / aura-brain"
priority: P2
risk: Medium
created: "2026-10-03"
units: [U393, U394, U395, U397]
---

# Feature Specification: Wandering

**Feature Branch**: `023-wandering`

## Background

Asked for as (translated): *"can we add a 'wandering' mode — the robot wanders
around, following people, moving the antennas, moving towards sound or people —
with an option to enable or disable sound"*. Agreed with three conditions:

1. a switch next to follow-me;
2. *"review that this cannot conflict with other settings and modes"*;
3. when someone speaks to him while he wanders, *"he looks at them, but only
   speaks if the sound mode is on"* — with sound as levels rather than on/off:
   silent, emotion sounds only ("hmm", giggling), or talking.

Then extended (translated): *"in present mode, provide this wander mode next to
follow me as options in a scenario"* — U394. And moved (translated): *"if I'm
at a fair and want him in wander mode, how do I best do that? I'd think in work
mode and activate it there? Doing it via Settings seems so strange"* — U397:
wandering is a behaviour of each mode, and a Stand mode wanders by default.

**Reachy Mini does not drive.** Wandering is done where he stands: head, torso
and antennas. The microphone array reports which side a voice comes from but
cannot tell front from back.

## User Scenarios & Testing *(mandatory)*

### Story 1 — he looks around by himself (U393)

1. **Given** wandering is on and nobody is in view, **When** time passes,
   **Then** he glances around every few seconds, now and then turns his whole
   body, and moves his antennas.
2. **Given** wandering is on, **When** someone speaks to one side of him,
   **Then** he turns towards the voice — head first, the torso for wide turns —
   and does not jerk between two voices (a few seconds between turns).
3. **Given** wandering is on, **When** someone is in view, **Then** the face
   tracker keeps him looking at them; he does not glance away or turn to another
   voice, and only his antennas move now and then.
4. **Given** a voice straight ahead or straight behind, **When** it speaks,
   **Then** it is not a reason to turn (the array cannot tell which).

### Story 2 — it cannot conflict (U393)

1. **Given** follow-me is off, **When** wandering is on, **Then** he follows the
   people he sees anyway; **When** wandering stops, **Then** follow-me is off
   again — exactly as the owner left it.
2. **Given** wandering is on, **When** the owner turns follow-me off, **Then**
   wandering carries on, and the setting is remembered for when it stops.
3. **Given** wandering is on, **When** he goes to sleep, **Then** he does not
   wander and does not lift his head (U357); **When** he wakes, **Then** he
   wanders again.
4. **Given** a presentation is running, **Then** he does not wander (U334: on
   stage only the scenario moves and speaks) — until U394 lets a scenario say
   otherwise — and he wanders again when it ends.
5. **Given** a gesture, a beat or speech is playing, **Then** wandering waits.
6. **Given** the robot restarts, **When** it comes back, **Then** the brain tells
   it again — the robot does not remember it.
7. **Given** a robot too old to wander, **When** wandering is switched on,
   **Then** the switch says the robot needs an update rather than failing.

### Story 3 — what he may say while he wanders (U393, U395)

1. **Given** wandering with sound *silent*, **When** someone speaks to him,
   **Then** he turns to them and says nothing; the reply appears in the console.
2. **Given** wandering with sound *talk*, **When** someone speaks to him,
   **Then** he answers as usual.
3. **Given** wandering with sound *emotions*, **When** someone speaks to him,
   **Then** he answers with an emotion that fits the reply — a giggle for a
   joke, an *oops* for an apology, a nod and a *hmm* otherwise — and the words
   appear in the console (U395).
4. **Given** wandering with sound *emotions* or *talk*, **When** someone comes
   into view after a while with nobody there, **Then** now and then he greets
   them with an emotion; **When** he has been alone for a long while, **Then**
   now and then he sighs or yawns. Never two within 45 seconds, and nobody who
   was already there when he started is greeted (U395).
5. **Given** Quiet is on, **Then** he makes no emotion of his own accord — but
   he still answers with one, because answering is not starting (U256).
6. **Given** a talk is on stage, **Then** he makes no emotion at all; only the
   scenario makes sound (U334).
7. **Given** he is asleep, or speaking, **Then** no emotion plays; his voice
   cuts a playing one short.

### Story 4 — a talk decides (U394)

1. **Given** a scenario with `wander: on` for the walk-in and `wander: off`
   from the first slide, **When** the presenter starts, **Then** he looks around
   the room until the first slide and watches the presenter after it.
2. **Given** a beat with `follow_me: off` on the demo slide, **When** that
   slide is reached, **Then** he stands still; **When** the presenter jumps back
   into the demo later, **Then** he stands still again.
3. **Given** a scenario that says nothing about wandering, **Then** he does not
   wander during the talk, whatever the mode says.
4. **Given** the talk ends, **Then** the owner's own Wander and Follow me apply
   again.

## Functional Requirements

- **FR-001**: Wandering is a behaviour of each mode (U397): `wander` (`on` /
  `off`) and `wander_sound` in the mode's behaviour row, set in Modes. A Stand
  wanders and talks by default; Home and Work stand still until the owner says
  otherwise; in Present the scenario decides (FR-008). Switching mode in the
  header is what turns it on or off — at a fair, one click. It was a switch
  in Settings (U393) until the owner asked why a fair should need a trip there;
  the environment variables `WANDER_ENABLED` and `WANDER_SOUND` are no longer
  read.
- **FR-002**: The robot decides how to wander (`robot_runtime.wander`, a pure
  planner); the brain decides whether (`aura_brain.wander`) — the active
  mode's behaviour, or the scenario during a talk — and tells the robot on
  every change: a mode switch or a change to a mode's row (U397), Quiet, a
  scenario loading or ending, waking up, and the robot reconnecting.
- **FR-010**: Wander and follow-me compose (U397, asked as *"how does he handle
  it when both are on"*): wandering keeps the face tracker on, so while he
  wanders he follows whoever he sees whatever follow-me says — only the
  antennas move while someone is in view, and he looks around and turns to
  voices when nobody is. Follow-me matters once wandering stops. Standing
  still needs both off.
- **FR-003**: Follow-me and body-follow are the owner's. The robot keeps what
  the owner asked for apart from what is in force; wandering keeps the tracker
  and the torso following people while it runs and gives both back unchanged.
  Never while asleep.
- **FR-004**: The sound direction comes from the daemon's microphone array over
  HTTP (`GET /api/state/doa`), not from the USB device directly. Without it he
  still looks around; the status says the direction is unavailable instead of
  claiming it.
- **FR-005**: Gestures, beats and speech hold the motion lock first; a wander
  step waits for it and does not move while he talks.
- **FR-006**: `wander_sound` is `silent` (default, and what anything
  unrecognised means), `emotions` (FR-009) or `talk`. While wandering silently
  or with emotions, replies are not spoken and no voice engine that speaks for
  itself is opened.
- **FR-008**: During a presentation the scenario decides whether he wanders
  and whether he follows the presenter, slide by slide (spec 011 FR-122); the
  brain composes it with the owner's settings and gives those back at the end.
- **FR-009**: `wander_sound` has a third level, `emotions` (U395): sounds
  instead of words. An emotion is a recording from Pollen's emotions library
  (`pollen-robotics/reachy-mini-emotions-library`) — a movement with its own
  sound — played by the daemon (`POST /api/move/play/recorded-move-dataset/…`)
  through the robot's speaker, whichever speaker he talks on. The robot runtime
  plays it (`POST /robot/emotion {name}`: 409 asleep, 422 not a plain name, 404
  not in the library, 501 an adapter without them) with the motion lock held
  and follow-me paused until the daemon says it has finished, and stops it when
  he starts speaking. The planner chooses spontaneous ones (short ones only:
  greeting someone who arrives, a sigh after five minutes alone, at most one per
  45 s) when the brain allows them: wandering, sound `emotions` or `talk`, not
  Quiet, no talk on stage. The brain tells the robot again when the sound level
  or Quiet changes. In `emotions` mode a reply becomes an emotion picked from
  its mood (`aura_brain.mood`), laughter first.
- **FR-007**: `GET /robot/wander` (brain) says whether he wanders, why not when
  he should (`paused: presentation`), what he may say, and what the robot
  answered — including "the robot needs an update to wander".

## Out of scope

- Driving: Reachy Mini has no wheels.
- Telling a voice in front from one behind.
- Emotions in a scenario: on stage only the scenario's own lines make sound.
- Sound-only emotions, or ones synthesised on the laptop: the library's
  recordings belong to the body — the sound comes from the robot.

## Traceability

| Unit | What it delivered |
|---|---|
| U397 | Wandering is a behaviour of each mode, set in Modes; a Stand mode wanders and talks by default |
| U395 | The *emotions* sound level: spontaneous emotions while he wanders, and a reply answered with one, from Pollen's library |
| U394 | A scenario decides wandering and follow-me during a talk |
| U393 | Wandering: the planner, the robot's half (follow-me untouched, never asleep, motion lock first), the brain's half (whether, and what he may say), the switch and its note in Settings |
