---
mode: agent
description: Run the spec-to-execution workflow — transform a validated spec into plan, risk analysis, tasks, and rollback strategy.
---

Run the **spec-to-execution** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/spec-to-execution.yml` and execute all 6 stations in order:

1. **Plan Generation** — Create implementation plan from spec, clarifications, and architecture review
2. **Risk Analysis** — Identify and mitigate high-severity risks
3. **Rollout / Rollback** — Define rollout strategy and rollback procedures
4. **Task Decomposition** — Break plan into sequenced, traceable tasks
5. **Test Strategy** — Align test levels and coverage expectations with tasks
6. **Execution Readiness** — Verify the full package is ready for implementation

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

This workflow requires an existing spec package (`spec.md`, `clarifications.md`, `architecture-review.md`).
Chain with `implementation-loop` for the coding phase.

Ask the user for:
- Feature name (must match an existing `specs/features/<feature>/` folder with a spec)
