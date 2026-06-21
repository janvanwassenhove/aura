---
mode: agent
description: Run the incident-resolution workflow — structured diagnosis from incident analysis through fix, regression testing, and knowledge capture.
---

Run the **incident-resolution** workflow for the specified incident.

Load the workflow definition from `.github/apm/workflows/incident-resolution.yml` and execute all 7 stations in order:

1. **Incident Analysis** — Reconstruct timeline, collect logs/traces, assess impact
2. **Root Cause Hypothesis** — Form hypothesis with evidence, rule out alternatives
3. **Reproduction Scenario** — Document steps to reproduce with environment details
4. **Fix Proposal** — Plan minimal, targeted fix with blast radius assessment
5. **Regression Test** — Create tests that reproduce the incident scenario
6. **Patch Validation** — Run lint, tests, security scan — verify no side effects
7. **Knowledge Update** — Create ADR or playbook entry, document preventive measures

Write all outputs to `specs/features/<feature>/`.
Evaluate quality gates between each station. Halt on blocker gate failures.

Ask the user for:
- Incident name or ID (used as the folder name under `specs/features/`)
- Description of the incident or link to the alert/ticket
- Affected service or component (if known)
