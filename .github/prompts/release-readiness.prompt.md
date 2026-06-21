---
mode: agent
description: Validate release readiness for a feature — check spec, tests, security, observability, deployment.
---

Perform a **release readiness** assessment for the specified feature.

Review the feature's artifacts in `specs/features/<feature>/` and evaluate:

1. **Spec completeness** — Verify spec.md, clarifications.md, plan.md, tasks.md exist and are coherent
2. **Test coverage** — Check that acceptance criteria have corresponding tests
3. **Security posture** — Look for SAST/dependency findings, unresolved vulnerabilities
4. **Observability** — Verify logging, metrics, and alerting are addressed
5. **Deployment readiness** — Check rollback procedure, environment config

Produce a summary assessment in `specs/features/<feature>/release-readiness.md` with a go/no-go recommendation.

This is a quick assessment prompt. For the full 6-station workflow, use `/workflow-release-readiness` instead.

Ask the user for:
- Feature name (must match an existing `specs/features/<feature>/` folder)
