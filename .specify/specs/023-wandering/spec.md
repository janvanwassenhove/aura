---
feature: "023-wandering"
status: "in-progress"
owner: "robot-runtime / aura-brain"
priority: P2
risk: Medium
created: "2026-10-03"
units: [U393]
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
follow me as options in a scenario"* — U394.

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
3. *Emotions* — emotion sounds from Pollen's library instead of words — is U395.

## Functional Requirements

- **FR-001**: Wandering is a capability, `wander` (`WANDER_ENABLED`, off by
  default), listed directly after *Turn body too*.
- **FR-002**: The robot decides how to wander (`robot_runtime.wander`, a pure
  planner); the brain decides whether (`aura_brain.wander`) — the owner's
  switch, paused while a presentation runs — and tells the robot on every
  change: the switch, a scenario loading or ending, waking up, and the robot
  reconnecting.
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
- **FR-006**: `WANDER_SOUND` is `silent` (default, and what anything
  unrecognised means) or `talk`. While wandering silently, replies are not
  spoken and no voice engine that speaks for itself is opened.
- **FR-007**: `GET /robot/wander` (brain) says whether he wanders, why not when
  he should (`paused: presentation`), what he may say, and what the robot
  answered — including "the robot needs an update to wander".

## Out of scope

- Driving: Reachy Mini has no wheels.
- Telling a voice in front from one behind.
- Emotion sounds (U395) and scenario control (U394), specified when they land.

## Traceability

| Unit | What it delivered |
|---|---|
| U393 | Wandering: the planner, the robot's half (follow-me untouched, never asleep, motion lock first), the brain's half (whether, and what he may say), the switch and its note in Settings |
