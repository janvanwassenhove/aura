---
mode: agent
description: Run the quality validation workflow — lint, static analysis, SAST, dependency audit, coverage, DAST.
---

Run the **quality-validation** workflow for the specified feature or project.

Load the workflow definition from `.github/apm/workflows/quality-validation.yml` and execute all 7 stations:

1. **Lint Analysis** — Run language-specific linter (ESLint, Pylint, Clippy)
2. **Static Analysis** — Run SonarQube/SonarCloud analysis
3. **Security SAST** — Run Checkmarx SAST scan
4. **Dependency Audit** — Scan for known CVEs (Snyk, OWASP Dependency-Check, Trivy)
5. **Coverage** — Measure test coverage (JaCoCo, Istanbul, Coverage.py)
6. **Security DAST** — Run OWASP ZAP scan (optional, requires running app)
7. **Quality Report** — Aggregate all results

Write all reports to `specs/features/<feature>/`.
Evaluate quality gates between stations. Halt on blocker failures.

If a tool is not installed, the station is reported as skipped (not failed).

Ask the user for:
- Feature or project name
- Path to the project to scan (if not the current workspace)
