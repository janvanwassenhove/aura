---
mode: agent
description: Draft a modernization specification package with comprehensive assessment, ADR-driven decisions, and migration plan with rollback clarity.
---

# Modernization

Help me draft a modernization specification package.

Follow the playbook at `.github/apm/knowledge/playbooks/modernization-playbook.md`:

1. **Assess baseline** — Comprehensive codebase assessment with health scores.
2. **Capture decisions** — Create ADRs for every architecturally significant choice.
3. **Define target state** — What the system should look like after modernization.
4. **Coexistence** — Describe how old and new will run together during migration.
5. **Risks and rollback** — Clarify what can go wrong and how to reverse.
6. **Staged plan** — Phased migration plan with dependency graph and rollback paths.
7. **Tasks** — Sequenced tasks with verification checklists and regression coverage.

Apply `.github/apm/knowledge/governance/architecture-principles.md` and `.github/apm/knowledge/constitution/enterprise-defaults.md`.

Use the specialised refactor sub-agents when detailed work is needed:
- `refactor-assessor` for comprehensive assessment
- `refactor-planner` for phased migration planning

Write output under `specs/features/<feature>/`.

Before starting, ask me: What system are we modernizing? What's the target state? What are the constraints?
