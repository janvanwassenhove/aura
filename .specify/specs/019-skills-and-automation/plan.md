---
feature: "019-skills-and-automation"
---

# Implementation Plan: Skills, Automation and the Agentic Loop

**Prerequisites**: `spec.md`. Retro-written from the code.

## Shape

```
turn ─▶ round 1 (fast model) ─── most turns end here
          │ needs a tool?
          ▼
        round 2..n (stronger model)
          │  each tool call ─▶ mode policy ─▶ approval gate ─▶ run
          │                        │
          │                        └── refused? say so; do not improvise
          ▼
        reply ─▶ skill ledger line (AFTER the turn, with the outcome)
```

`docs/diagrams/one-turn.svg` draws this, and
`docs/diagrams/delegation-bounds.svg` draws what a sub-agent may reach.

## Decisions

### Evidence is written after the fact, and only for real turns

U247, twice over. The ledger line used to be written *before* the turn ran, so
it recorded what was asked and never what happened — and the optimiser was then
asked to "add guardrails for the failure cases implied by the evidence" about
evidence containing no failures. Separately, system-started turns (a greeting,
a presenter beat) ran the same pipeline and were counted as skill *uses*: four
of seven recorded uses of the Spotify skill were the robot saying hello.
`orchestrate(..., from_user=False)` marks those, and they write nothing.

The general rule this repository keeps arriving at: **a learning loop is only as
honest as the record it learns from**, so the record must be written where the
outcome is known.

### Some tools can never be gated off

`shared_policies.rules._ALWAYS` holds `request_capability`, `web_search`,
`read_url` and `look_up_person`. The first is the important one: if asking to
be unblocked can itself be blocked, the owner has to go and read logs to find
out what he wanted. Granting takes effect immediately (the env is set live, not
after a restart) because a setting that needs a restart reads as broken.

### Refusals are real or they are nothing

U253c. A skill had been given a polite sentence for declining, and he used it
for things he could perfectly well do. A refusal must come from the policy, not
from prose — the same rule that
[017](../017-voice-and-language/spec.md) states for stall sentences.

### The cheapest rung first

U58 and U70. Driving the screen is the last resort, not the first: it is slow,
fragile, and needs the display to look the way it looked yesterday. A direct
tool beats PowerShell, which beats the mouse. When the screen is used, it says
so and can be stopped (U75).

### Tool schemas go through `_fn()`

U294. A hand-written schema dict broke two unrelated tests that walk the schema
list, because they rely on a shape `_fn()` guarantees. There is one way to add
a tool.

## Files

| Path | Role |
|---|---|
| `services/orchestrator/src/orchestrator/pipeline.py` | The loop, the rounds, the ledger, the notes |
| `services/orchestrator/src/orchestrator/tool_schemas.py` | Every tool, via `_fn()` |
| `services/orchestrator/src/orchestrator/skills.py` | Storage, triggers, scope |
| `services/orchestrator/src/orchestrator/skill_optimizer.py` | The learning loop |
| `services/orchestrator/src/orchestrator/skill_review.py` | Proposals that wait for a click |
| `services/orchestrator/src/orchestrator/unblocks.py` | `request_capability` |
| `services/orchestrator/src/orchestrator/approval_manager.py` | The gate |
| `services/orchestrator/src/orchestrator/laptop_tools.py` | PowerShell, files, git, launcher |
| `services/orchestrator/src/orchestrator/hooks.py` | Declarative hooks, subagent bounds |
| `packages/shared-policies/src/shared_policies/rules.py` | What each mode permits; `_ALWAYS` |
