# ADR-009: Honest State — never report what has not been verified

**Status**: **Accepted** — retro-recorded 2026-09-05
**Date**: 2026-09-05 (the practice is older; it accumulated from U52 onward)
**Owner**: cross-cutting
**Related**: constitution IV and X; ADR-006; specs
[010](../../.specify/specs/010-connector-skeletons/spec.md),
[016](../../.specify/specs/016-embodiment-and-presence/spec.md),
[018](../../.specify/specs/018-knowledge-people-and-judgment/spec.md)

---

## Context

This decision is recorded late because it was never *taken* — it accumulated,
one incident at a time, until it turned out to be the single most repeated
lesson in three hundred units. Writing it down now stops it being relearned.

The pattern, in the order it happened:

| Unit | What was reported | What was true |
|---|---|---|
| U52 | A green "connected" badge | A mock returning canned data |
| U180 | `BENIGN` | A tier the owner could not interpret |
| U238 | "Sleep: done" | A 404 from an older runtime |
| U253 | "Following" | The tracker thread was dead |
| U254b | "Connected — real calls are going out" | No token had ever been stored |
| U270 | "Battery 100%" | The SDK exposes no battery reading |
| U276, U278 | Nothing saved | It had been saved |
| U290 | "Nothing is being remembered" | He knew exactly who was talking |
| U283 | "CI is green" | CI had been red for six hours |
| U297 | "Robot offline" | The robot was answering — visibly, in our own release screenshots |

Ten incidents, one shape. Each was a component reporting a **plausible default**
or an **unverified assumption** instead of what it actually knew. None of them
was a crash; every one of them was believed.

The cost is asymmetric. A component that says "I don't know" costs a moment of
mild disappointment. A component that says "fine" when it is not costs the
owner's trust in everything else the system says — and, in the case of the
battery, would have let a robot run flat while reassuring them.

## Decision

**A value is reported only if it has been verified. Where it has not, the
absence is reported as an absence, in the owner's language, with the next step
attached.**

Four rules follow:

1. **Never substitute a plausible default for a missing measurement.** A value
   that is not known is `null` and renders as *"not reported by this
   firmware"*, *"mains powered"*, *"nobody has measured this"* — never as a
   number. (U270, and every status line since.)

2. **A mock says it is a mock.** Anything answering with synthetic data reports
   a distinct state and never `ok`. (U52, ADR-006.)

3. **Constructing is not connecting.** A component whose credential is read at
   call time builds happily with nothing configured, so *it built* proves
   nothing. Green is earned by a probe that exercises the real path — and the
   probe must be a call that component actually implements. (U254b.)

4. **`unknown` is not a status.** It is the only answer that tells the owner
   nothing they can act on. Every state must map to a distinct next step, and
   carry it. (U254.)

And one consequence for the console specifically:

5. **The console composes presentation, never truth.** Every status,
   capability and knowledge state it shows is supplied by the brain. When it
   derived state itself, it was wrong six times (U252c, U252e, U276, U278,
   U290, U297).

## Consequences

**Good.** A status line becomes actionable rather than decorative. "Six states,
each a different job" (ADR-006) is a direct product of this decision, and it is
why the Connections panel can be understood by somebody who has never read the
code. It also gives a cheap review question for any new surface: *what does this
say when it does not know?*

**Bad.** It is more work per feature, and it produces screens with more words on
them. Several units were spent adding a third state where two would have "worked"
— `has_battery: null` versus `false` is a distinction nobody asks for until the
day it matters.

**Ugly.** It cannot be tested for in general. There is no lint for optimism.
The defence is that every unit fixing an instance of this states the pattern in
a comment at the site, and that the tests written for it assert the *honest*
answer rather than merely a non-crash — a test that accepts "100%" would have
passed U270 unchanged.

## Alternatives considered

**Report optimistically and let the owner discover the truth.** This is the
default behaviour of most software and is what produced the ten rows above.
Rejected: the owner discovers it at the worst moment, and every previous
reassurance retroactively loses value.

**Report nothing until fully verified.** Cleanest, and unusable: a robot that
shows no state until every subsystem has been probed shows nothing for the first
several seconds of every session, on a device whose whole point is presence.

**A single "health" number.** Rejected for the same reason as `unknown`: it
aggregates away exactly the distinction that tells the owner what to do.
