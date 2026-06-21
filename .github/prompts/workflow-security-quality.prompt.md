---
mode: agent
description: Run the security and quality assessment workflow — threat modelling, hardening review, SAST, dependency CVE audit, static analysis, lint, coverage, WCAG accessibility, DAST, and aggregated risk report.
---

Run the **security-quality-assessment** workflow for the specified target.

Load the workflow definition from `.github/apm/workflows/security-quality-assessment.yml` and execute all 11 stations:

1. **Scope & Context** — Confirm target, depth, stack, and compliance requirements with the user
2. **Threat Modelling** — STRIDE analysis, trust boundary map, threat register
3. **Hardening Review** — HTTP security headers, CORS, secrets scanning (Gitleaks/TruffleHog), rate limiting, input/output controls
4. **Security SAST** — Static vulnerability analysis (Checkmarx, Semgrep)
5. **Dependency CVE Audit** — Scan for known CVEs (Snyk, OWASP Dependency-Check, Trivy)
6. **Static Code Analysis** — Code quality and bug detection (SonarQube/SonarCloud)
7. **Lint Analysis** — Language-specific linting (ESLint, Pylint, Clippy)
8. **Coverage Assessment** — Test coverage measurement (JaCoCo, Istanbul, Coverage.py)
9. **Accessibility Audit** *(optional — front-end only)* — WCAG 2.1/2.2 AA compliance (axe, Pa11y)
10. **Security DAST** *(optional — requires running app and explicit confirmation)* — Dynamic scan (OWASP ZAP)
11. **Security & Quality Report** — Aggregate all findings into a risk-scored report with remediation plan

Write all reports to `specs/features/<target>/`.
Evaluate quality gates between stations. Halt on blocker failures.
Pause and ask the user on every Critical or High finding before proceeding.

Ask the user for:
- Target name (repository, service, or component)
- Assessment depth: quick / focused / full
- Stack (language, framework, cloud provider)
- Compliance requirements (PCI-DSS, SOC 2, HIPAA, ISO 27001, or none)
- Any known concerns or prior incidents to prioritise
- Live app URL (only if DAST is in scope — will ask for explicit confirmation before scanning)
