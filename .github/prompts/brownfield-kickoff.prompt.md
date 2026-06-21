---
mode: agent
description: Start a brownfield specification package with reverse brief.
---

# Brownfield Kickoff

Help me create a brownfield specification package for a change in an existing system.

Follow the playbook at `.github/apm/knowledge/playbooks/brownfield-playbook.md`:

1. **Reverse brief** — Use the `brownfield-context` skill. Extract current state, constraints, integration points, and known risks. Write to `specs/features/<feature>/reverse-brief.md`.
2. **Constitution** — Read `.github/apm/knowledge/constitution/brownfield.md` and `.github/apm/knowledge/constitution/enterprise-defaults.md`. Refine `specs/constitution.md` with compatibility rules.
3. **Feature spec** — Use `spec-feature`. Write to `specs/features/<feature>/spec.md`.
4. **Clarifications** — Use `spec-clarify`. Focus on impact, edge cases, and backward compatibility. Write to `specs/features/<feature>/clarifications.md`.
5. **Plan** — Use `spec-plan`. Include existing boundaries and regression coverage. Write to `specs/features/<feature>/plan.md`.
6. **Tasks** — Use `spec-tasks`. Include regression test tasks. Write to `specs/features/<feature>/tasks.md`.
7. **Quality gate** — Use `spec-quality-gate`. Write to `specs/features/<feature>/quality-gate.md`.

Before starting, ask me for the feature name and a description of the existing system and the change needed.
