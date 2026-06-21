---
mode: agent
description: Review architecture decisions against principles, NFRs, and governance guardrails.
---

Run an **architecture review** for the specified feature or decision.

Load the architecture governance agent from `.github/agents/architecture-governance.md` and use the following skills:
- `architecture-guardrails` — Apply architecture guardrails for the chosen style
- `nfr-review` — Review non-functional requirement completeness

## Review scope

1. **Principles alignment** — Verify against `.github/apm/knowledge/governance/architecture-principles.md`
2. **NFR completeness** — Check performance, security, availability, observability requirements
3. **Security posture** — Validate against `.github/apm/knowledge/governance/secure-by-default.md`
4. **Observability** — Check against `.github/apm/knowledge/governance/observability-by-default.md`
5. **Testing policy** — Verify against `.github/apm/knowledge/governance/testing-policy.md`

Write the review output to `specs/features/<feature>/architecture-review.md`.

Ask the user for:
- Feature name (must match a `specs/features/<feature>/` folder with a spec)
- Specific concerns to focus on (optional)
