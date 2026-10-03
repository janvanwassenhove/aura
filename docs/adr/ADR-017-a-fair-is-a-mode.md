# ADR-017: A fair is a mode — where he is decides what he may reach and whether he wanders

**Status**: **Accepted — implemented in U397** (2026-10-03).
**Date**: 2026-10-03
**Owner**: orchestrator / mode_policy, aura-brain / wander, operator-console
**Related**: [spec 019](../../.specify/specs/019-skills-and-automation/spec.md)
(FR-MODE-STAND), [spec 023](../../.specify/specs/023-wandering/spec.md),
[ADR-015](ADR-015-wandering-is-a-layer-not-a-setting.md), U294, U334, U335,
U393, U397

---

## Context

The owner asked (translated): *"if I'm at a fair, say, and I want to put the
robot in wander mode there, how do I best do that? I'd think in work mode and
activate it there? Doing it via Settings seems so strange."*

Wandering (U393) was a switch in Settings, which is a place for how the
installation is set up, not for where the robot is today. And the mode the
owner reached for, Work, carries the owner's working life: calendar, mail,
files, the screen, PowerShell; memory writing on; the household roster and
the day's agenda in every prompt; and the conversation so far. At a fair,
everyone who walks up is talking to that.

## Decision

1. **Wandering is a behaviour of each mode**, beside persona, voice, speaks
   first and memory writing, set in Modes. The Settings switch and the
   `WANDER_ENABLED` / `WANDER_SOUND` variables are gone. Switching mode in the
   header is what turns it on or off.
2. **A fair is its own mode, Stand**, between Work and Present. It allows
   talking and looking things up; every group of the owner's is blocked, and
   so is the person lookup every other mode carries. It wanders and talks,
   never speaks first, and remembers nobody.
3. **At a stand nothing personal is in a prompt**: no agenda, mail or tasks
   snapshot, no household roster, no profile for a face he knows. He is told
   where he is instead. The conversation of the stand and the conversation of
   the other modes are kept apart in both directions.

## Why not the alternatives

- **Work mode with wandering switched on**, as first suggested. It answers the
  question asked and leaves the owner's mail and agenda one sentence away from
  any visitor; the approval gate stops *sending* mail, not reading the day's
  calendar aloud. Making Work safe for a fair would make it useless at work.
- **Wandering per mode, without a new mode.** Smaller, and it still leaves the
  owner to remember, at a fair, to restrict a mode built for something else
  — and to restore it afterwards.
- **A wandering scenario in Present.** A scenario can set `wander: on` (U394),
  but on stage only the scenario speaks (U334): he would not answer a single
  visitor.
- **Keep the Settings switch as a global default under the modes.** Two places
  that decide the same thing is the conflict the owner made wandering
  conditional on avoiding (U393, translated: *"review that this cannot
  conflict with other settings and modes"*).

## Consequences

- One click in the header changes what he may reach, what he is told, what he
  remembers and whether he wanders — and one click gives all of it back.
- A face he knows is a visitor at a stand. If the owner's colleague walks up,
  he will not greet them by name; that is the price of not reciting a profile
  to whoever stands beside them.
- The owner can still open up a Stand in Modes, group by group, like any mode.
  The defaults are the safe ones.
- At a stand his name and the question come in one breath, and nothing he
  says opens a window for the next voice (U398). The first evening in Stand
  showed why: the transcriber made "AURA" out of noise and out of his own
  giggle, and the window that followed took the crowd's next sentence as the
  question. A visitor who says only "AURA" and waits gets nothing — the
  price of not answering the hall.
- Anything added later that reads personal context must ask
  `mode_policy.in_public()` — the pipeline, the household note and the person
  note do, and they are what both speech paths ask.
