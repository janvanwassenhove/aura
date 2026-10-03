---
feature: "023-wandering"
---

# Implementation Plan: Wandering

**Prerequisites**: `spec.md`, [ADR-015](../../../docs/adr/ADR-015-wandering-is-a-layer-not-a-setting.md).

## Decisions

- **The robot decides how, the brain decides whether.** The planner runs on the
  robot, next to the face tracker and the motion lock, at a half-second tick a
  Wi-Fi round trip should not carry. The brain owns the reasons it may not run
  — a presentation, the owner's switch — because only the brain knows them.
- **Wishes are kept apart from what is in force.** `set_tracking` records the
  owner's follow-me; what is applied is *follow-me, or wandering, never
  asleep*. A wander that turned follow-me on would have had to remember to
  turn it off again, and would have forgotten a change made meanwhile.
- **The planner is pure.** No hardware, no clock, no randomness of its own: the
  adapter passes `now`, the camera and the array, and a seeded `Random`.
- **The array through the daemon.** `GET /api/state/doa` on the robot answers
  `{"angle", "speech_detected"}`; opening the ReSpeaker USB device from the
  runtime as well would compete with the daemon for it.
- **Silent means text.** A silent wander does not discard the conversation; it
  keeps it off the speaker.
