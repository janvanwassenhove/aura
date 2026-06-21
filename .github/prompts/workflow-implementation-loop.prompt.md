---
mode: agent
description: Run the implementation-loop workflow — agent-assisted dev loop with self-review, testing, and commit readiness.
---

Run the **implementation-loop** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/implementation-loop.yml` and execute all 6 stations in order:

1. **Task Selection** — Pick the next task from `tasks.md` with prerequisites met
2. **Code Generation** — Implement the task, produce or modify source code
3. **Self-Review** — Agent reviews its own code for smells, style, and security
4. **Test Generation** — Create tests covering the task's acceptance criteria
5. **Local Validation** — Run lint, build, tests, and check coverage
6. **Commit Readiness** — Verify all gates pass, produce commit summary

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

This workflow requires existing `tasks.md` and `plan.md` from a prior `spec-to-execution` run.
Iterate this workflow for each task in the task list.

Ask the user for:
- Feature name (must match an existing `specs/features/<feature>/` folder with tasks)
