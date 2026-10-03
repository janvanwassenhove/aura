# ADR-015: Wandering is a layer over follow-me, not a change to it

**Status**: **Accepted — implemented in U393** (2026-10-03).
**Date**: 2026-10-03
**Owner**: robot-runtime / adapters, aura-brain / wander
**Related**: [spec 023](../../.specify/specs/023-wandering/spec.md), [ADR-016](ADR-016-his-emotions-are-the-robots-recordings.md), U37, U157,
U165, U357, U393

---

## Context

Wandering needs the face tracker on (to follow people) and the torso following
(to turn towards them). Both already exist as the owner's settings: *Follow me*
(`HEAD_TRACKING`) and *Turn body too* (`BODY_FOLLOW`). The owner agreed to
wandering on one condition: *"review that this cannot conflict with other
settings and modes"* (translated).

The obvious implementation is to switch follow-me and body-follow on when
wandering starts and off when it stops.

## Decision

**The robot keeps what the owner asked for apart from what is in force.**
`set_tracking` and `set_body_follow` record the owner's wish; what the adapter
applies is computed: *the owner's follow-me, or wandering — and never while
asleep*. Wandering never writes either setting.

## Why not switch them on and off

- **It forgets.** Turning follow-me off at the end of a wander is wrong if the
  owner had it on, and right if they had it off — so the wander has to
  remember the state it found. Then the owner changes follow-me in the middle
  of a wander, and the remembered state is stale.
- **It fights sleep.** U357 established that the sleep sequence turns tracking
  off on its way down and that nothing may lift the head while asleep. A wander
  that re-enabled tracking would undo it; *never while asleep* in the computed
  state cannot.
- **It interrupts.** Turning follow-me off recentres the head (U165). Applied
  while wandering keeps the tracker on, that recentre would jerk the head for a
  setting not in force — the computed state skips it.

## Consequences

- `set_tracking(False)` while wandering changes nothing visible; it is
  remembered and applied when the wander ends.
- Every place that turns tracking on or off goes through the same computation,
  so a later feature that also needs the tracker (U394 lets a scenario turn
  wandering on) adds a term to it rather than another switch.
