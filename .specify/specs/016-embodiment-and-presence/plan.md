---
feature: "016-embodiment-and-presence"
---

# Implementation Plan: Embodiment and Presence

**Prerequisites**: `spec.md`. Retro-written from the code (see
[015-spec-coverage](../015-spec-coverage/spec.md)); the decisions below are the
ones still load-bearing today.

## Where the boundary sits

```
aura-brain                     robot-runtime (on the Pi)
  embodiment.py     ── name ──▶  BehaviorEngine ──▶ RobotAdapter
  (text → gesture)                                    ├── FakeRobot
                                                      └── ReachyRobotAdapter
```

The brain asks for `"wave"`, never for a joint angle. That is constitution II,
and it is what let the whole product be developed and screenshotted without
hardware — the release pipeline still boots `ROBOT_ADAPTER=fake`.

## Decisions

### Gestures are chosen by keyword, not by a model

`embodiment.py` maps reply text to a gesture with keyword and punctuation
heuristics. A second model call would be more nuanced and would arrive after
the sentence had finished, which is worse than a slightly wrong nod. The
persona's `GestureProfile` then scales how embodied the result is: `silent_desk`
stays still and mute, `work` keeps a restrained nod, presentation gestures
freely (U51).

### Follow-me is a state on the robot, not in a component

U162: two surfaces drove it — the Robot panel's toggle and the camera's
Follow/Manual switch — each with its own ref. They drifted, and the robot
fought the operator: one said "following" while the other had just aimed by
hand. The robot is now the single source of truth and both surfaces read it.

### `tracking` and `face_visible` are separate facts

U165: "follow is on" and "it has someone to follow" look identical from across
the room — a still head either way. That ambiguity is what made "follow-me
doesn't work" so hard to pin down, so both are reported and both are shown.

### Sleep goes through the SDK's own `goto_sleep()`

U102: a hand-built pose was close but not reliable. The SDK call is, and it
means the robot's own idea of "asleep" and ours agree.

### Nothing invents a measurement

U270 is the general rule this codebase keeps relearning: where a value is not
measured, the answer is "not measured", never a plausible default. The same
principle produced the three-state battery, the honest connector statuses
(U254), and the refusal to report a green badge for an unverified connection.

## Files

| Path | Role |
|---|---|
| `packages/shared-schemas/src/shared_schemas/robot/adapter.py` | The contract |
| `services/robot-runtime/src/robot_runtime/adapters/reachy.py` | Hardware, motions, dances, sleep |
| `services/robot-runtime/src/robot_runtime/adapters/fake.py` | The primary development target |
| `services/robot-runtime/src/robot_runtime/behavior/` | States, timeline builder |
| `apps/aura-brain/src/aura_brain/embodiment.py` | Reply text → gesture |
| `apps/aura-brain/src/aura_brain/characters.py` | The archetypes, brain side |
| `apps/operator-console/src/lib/characters.ts` | Faces, idle animation, opening move |
| `apps/operator-console/src/stores/robotStore.ts` | What the console believes about the body |
