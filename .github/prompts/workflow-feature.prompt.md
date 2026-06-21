---
mode: agent
description: Run the feature implementation workflow — full delivery from constitution through quality validation.
---

Run the **feature-implementation** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/feature-implementation.yml` and execute all 9 stations in order:

1. **Constitution** — Create or verify project constitution
2. **Specification** — Write the feature spec with scope and acceptance criteria
3. **Clarification** — Resolve ambiguities and open questions
4. **Architecture Review** — Validate against architecture principles
5. **Plan** — Create implementation plan with risks, rollout, rollback
6. **Tasks** — Break down into sequenced, testable tasks
7. **Implementation** — Execute tasks, generate/modify code
8. **Quality Validation** — Run nested quality-validation workflow (lint, SAST, deps, coverage)
9. **Final Quality Gate** — Verify package completeness

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

Ask the user for:
- Feature name (used as the folder name under `specs/features/`)
- Whether this is greenfield or brownfield
- A brief description of what the feature should do
