---
feature: "023-wandering"
---

# Tasks: Wandering

## Phase 1: Wandering itself (U393)

- [x] T001 [U393] `robot_runtime.wander`: a pure planner — glances, body turns, antennas, turn to a voice
- [x] T002 [U393] Reachy adapter: `set_wander`, owner's wishes kept apart from what is in force
- [x] T003 [U393] Never asleep; gestures, beats and speech first; the idle scan steps aside
- [x] T004 [U393] Sound direction from the daemon's array, reported honestly when missing
- [x] T005 [U393] Brain: `aura_brain.wander` — whether, paused for a presentation, re-asserted on reconnect
- [x] T006 [U393] Silent wander keeps replies off the speaker; talk answers as usual
- [x] T007 [U393] The `wander` capability next to follow-me, its sound and an honest note in Settings

## Phase 2: Scenarios (U394)

- [x] T008 [U394] `wander` and `follow_me` in a scenario, per talk and per beat
- [x] T009 [U394] Example scenarios: a keynote and a conference talk, walked step by step in the tests
- [x] T011 [U394] The builder offers both and carries `once` through a save

## Phase 3: Emotions (U395)

- [x] T010 [U395] The *emotions* sound level, from Pollen's library — verified on the robot: the move, the sound file opened by the daemon, follow-me back afterwards, refusals asleep and for unknown names
