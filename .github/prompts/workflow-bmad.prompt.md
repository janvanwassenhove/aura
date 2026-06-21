---
mode: agent
description: Run the BMAD workflow — Build→Measure→Analyze→Decide feedback loop with iterative improvement.
---

Run the **BMAD** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/bmad.yml` and execute all 4 stations in a loop:

1. **Build (Deliver)** — Nest a delivery workflow (feature-implementation or spec-kit)
2. **Measure (Validate)** — Nest quality-validation workflow
3. **Analyze (Evaluate)** — Score iteration outcomes, detect drift and regressions
4. **Decide (Adapt)** — Make evidence-based decision: accept, retry, update-spec, escalate

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

The loop retries up to 3 times. On `accept`, the workflow completes. On `escalate`, halt and request human input.

Ask the user for:
- Feature name (used as the folder name under `specs/features/`)
- Whether to use feature-implementation or spec-kit as the Build workflow
- Acceptance criteria for scoring
