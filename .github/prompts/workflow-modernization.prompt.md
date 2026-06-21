---
mode: agent
description: Run the modernization workflow — guided migration from assessment through implementation, parity validation, and quality assurance.
---

Run the **modernization** workflow for the specified initiative.

Load the workflow definition from `.github/apm/workflows/modernization.yml` and execute all 10 stations in order:

1. **Baseline Assessment** — Comprehensive codebase assessment with health scores and reverse brief
2. **Architecture Decisions** — Capture ADRs for every significant decision
3. **Target State** — Define the modernization target with compatibility expectations
4. **Architecture Review** — Validate migration approach against governance principles
5. **Migration Plan** — Create phased plan with rollback, coexistence, and dependency graph
6. **Risk Clarification** — Resolve all blocker-level risks and identify spikes
7. **Task Breakdown** — Break down into sequenced tasks with verification checklists
8. **Implementation** — Execute migration tasks with migration record tracking
9. **Parity Validation** — Verify old vs. new functional and visual parity (optional)
10. **Quality Validation** — Run nested quality-validation workflow

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

Ask the user for:
- Initiative name (used as the folder name under `specs/features/`)
- What system or component is being modernized
- What the target state looks like
