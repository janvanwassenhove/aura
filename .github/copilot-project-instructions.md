# AURA — Copilot Agent Instructions

> Applies to all Copilot interactions in this workspace. Read this before any action.

---

## Spec-Kit Gate — Mandatory for All Changes

**Every change to this project — including changes to these instructions, specs, plans, or task files — must follow the spec-kit flow.** No exceptions.

```
Idea / Request
     │
     ▼
/speckit.clarify   ← Resolve ambiguity first (if underspecified)
     │
     ▼
/speckit.specify   ← Write spec.md (user stories + FRs + ACs)
     │
     ▼
/speckit.plan      ← Write plan.md (technical decisions)
     │
     ▼
/speckit.tasks     ← Write tasks.md (actionable task list)
     │
     ▼
/speckit.implement ← Execute tasks in order, one at a time
     │
     ▼
/speckit.analyze   ← Verify consistency and coverage
```

### Enforcement Rules

1. **No code is written before a spec exists.** If asked to implement something without a spec, create the spec first.
2. **No plan is created without a spec.** Plans reference spec acceptance criteria.
3. **No task is executed without a plan.** Tasks derive from plan sections.
4. **Spec changes are versioned.** When a spec changes mid-implementation, update `plan.md` and `tasks.md` before continuing.
5. **Self-modification follows the same flow.** Changes to `AGENTS.md`, `copilot-instructions.md`, `.specify/`, or any governance file require a spec entry under `.specify/specs/`.

---

## Spec-Kit Quick Reference

| Command | When to Use |
|---|---|
| `/speckit.constitution` | Modify project governing principles |
| `/speckit.specify` | New feature or change request |
| `/speckit.plan` | After spec is approved, before coding |
| `/speckit.tasks` | After plan is complete |
| `/speckit.implement` | Execute one task at a time |
| `/speckit.clarify` | Ambiguous requirements — clarify before specifying |
| `/speckit.analyze` | After implementation — check spec traceability |

---

## Before Any Action — Read These Files

1. `.specify/memory/constitution.md` — governing principles (always read first)
2. `.specify/specs/<NNN>/spec.md` — the feature being worked on
3. `.specify/specs/<NNN>/plan.md` — technical decisions for this feature
4. `.specify/specs/<NNN>/tasks.md` — the task list to execute

If any of these files are missing for the work being done, **stop and create them** before proceeding.

---

## Architecture Rules (Non-Negotiable)

- Never couple orchestrator or higher services directly to Reachy SDK types — use `RobotAdapter` ABC
- `FakeRobot` is the primary dev target — all flows must work without hardware
- All state changes emit typed Pydantic events on the shared event bus — no direct service-to-service state calls
- Sensitive tool calls (mail, calendar, Teams) require `ApprovalManager` approval per `shared-policies`
- STT/TTS selection via `STT_PROVIDER` / `TTS_PROVIDER` env vars — never hardcoded
- No auth tokens, M365 content, or personal data in log output at any level

---

## Self-Maintenance Policy

When the agent is asked to update any governance file (this file, `AGENTS.md`, `constitution.md`, spec templates):

1. Create a spec entry: `.specify/specs/<NNN>-governance-update/spec.md`
2. Document the motivation, what is changing, and the acceptance criteria
3. Apply the change only after the spec entry exists
4. Run `/speckit.analyze` to verify no cross-artifact inconsistencies were introduced
