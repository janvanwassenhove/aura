---
mode: agent
description: Start a greenfield specification package using the hub's spec-kit flow.
---

# Greenfield Kickoff

Help me create a greenfield specification package for a new feature.

Follow the playbook at `.github/apm/knowledge/playbooks/greenfield-playbook.md`:

1. **Constitution** — Read `.github/apm/knowledge/constitution/principles.md` and `.github/apm/knowledge/constitution/greenfield.md`. Draft or refine `specs/constitution.md`.
2. **Feature spec** — Use the `spec-feature` skill. Ask me for: feature name, problem statement, users/actors, desired outcomes, constraints. Write to `specs/features/<feature>/spec.md`.
3. **Clarifications** — Use the `spec-clarify` skill. Identify ambiguities and ask me. Write to `specs/features/<feature>/clarifications.md`.
4. **Plan** — Use the `spec-plan` skill. Produce `specs/features/<feature>/plan.md`.
5. **Tasks** — Use the `spec-tasks` skill. Produce `specs/features/<feature>/tasks.md`.
6. **Quality gate** — Use `spec-quality-gate`. Produce `specs/features/<feature>/quality-gate.md`.

Before starting, ask me for the feature name and a brief description of what we're building.
