---
mode: agent
description: Run the spec-kit workflow — specification-only pipeline without implementation.
---

Run the **spec-kit** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/spec-kit.yml` and execute all 8 stations in order:

1. **Constitution** — Create or verify project constitution
2. **Specification** — Write the feature spec with scope and acceptance criteria
3. **Clarification** — Resolve ambiguities and open questions
4. **Architecture Review** — Validate against architecture principles
5. **Plan** — Create implementation plan with risks, rollout, rollback
6. **Tasks** — Break down into sequenced, testable tasks
7. **Test Strategy** — Define test levels and coverage expectations
8. **Quality Gate** — Verify package completeness and coherence

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

This is a specification-only pipeline — no implementation or quality-validation stations.

Ask the user for:
- Feature name (used as the folder name under `specs/features/`)
- Whether this is greenfield or brownfield
- A brief description of what the feature should do
