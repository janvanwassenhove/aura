---
mode: agent
description: Run the release-readiness workflow — validate spec, tests, security, observability, and deployment before release.
---

Run the **release-readiness** workflow for the specified feature.

Load the workflow definition from `.github/apm/workflows/release-readiness.yml` and execute all 6 stations in order:

1. **Spec Completeness** — Verify specification package is complete and coherent
2. **Test Completeness** — Confirm all acceptance criteria have tests, coverage meets threshold
3. **Security Validation** — Run SAST and dependency audit, check for critical vulnerabilities
4. **Observability Readiness** — Verify logging, metrics, alerting, and tracing are in place
5. **Deployment Readiness** — Validate rollback procedure, environment config, migration plan
6. **Go / No-Go Decision** — Produce release decision with rationale

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

This workflow requires a completed implementation with spec, plan, tasks, and implementation artifacts.

Ask the user for:
- Feature name (must match an existing `specs/features/<feature>/` folder)
