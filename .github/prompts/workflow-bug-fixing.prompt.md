---
mode: agent
description: Run the bug-fixing workflow — structured bug resolution from triage through regression testing.
---

Run the **bug-fixing** workflow for the specified bug.

Load the workflow definition from `.github/apm/workflows/bug-fixing.yml` and execute all 7 stations in order:

1. **Bug Triage** — Classify severity, priority, and affected component
2. **Reproduction** — Document reproduction steps and environment
3. **Root Cause Analysis** — Identify root cause with evidence
4. **Fix Plan** — Plan minimal fix with regression scope and rollback
5. **Fix Implementation** — Execute the fix
6. **Regression Testing** — Verify bug is resolved, no side effects
7. **Quality Validation** — Run nested quality-validation workflow

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

Station 7 invokes quality-validation as a nested sub-workflow.

Ask the user for:
- Bug identifier or feature name (used as the folder name under `specs/features/`)
- Bug description or link to the issue
- Affected component (if known)
