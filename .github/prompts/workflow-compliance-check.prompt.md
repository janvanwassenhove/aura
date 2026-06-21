---
mode: agent
description: Run the compliance-check workflow — validate PII, prompt injection, policies, risk scoring, and compliance reporting.
---

Run the **compliance-check** workflow for the specified feature or system.

Load the workflow definition from `.github/apm/workflows/compliance-check.yml` and execute all 6 stations in order:

1. **PII Scan** — Scan source code, config, and test data for unprotected PII
2. **Prompt Injection Detection** — Scan prompt templates and AI inputs for injection vectors
3. **Policy Validation** — Check applicable policies (GDPR, AI Act, organizational rules)
4. **Risk Scoring** — Compute overall compliance risk score from all findings
5. **Human Approval** — Record reviewer sign-off (optional, based on risk level)
6. **Compliance Report** — Produce consolidated report with pass/conditional/fail status

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

Relevant for EU AI Act compliance, GDPR, and organizational governance.

Ask the user for:
- Feature or system name (used as the folder name under `specs/features/`)
- Whether this is a periodic audit or pre-release check
- Any specific regulatory frameworks to prioritize
