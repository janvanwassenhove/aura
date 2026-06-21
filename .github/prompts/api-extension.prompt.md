---
mode: agent
description: Draft an API extension specification package with contract and compatibility focus.
---

# API Extension

Help me draft an API extension specification package.

Follow the playbook at `.github/apm/knowledge/playbooks/api-extension-playbook.md`:

1. **Consumer and contract** — Identify who consumes this API and what the contract intent is.
2. **Compatibility** — Define backward compatibility expectations, versioning strategy.
3. **Auth, validation, errors** — Clarify authentication, input validation, and error handling.
4. **Plan** — Implementation, rollout, and support plan.
5. **Tasks** — Concrete tasks with contract verification steps.

Apply governance guardrails from `.github/apm/knowledge/governance/secure-by-default.md`.

Write output under `specs/features/<feature>/`.

Before starting, ask me: What API are we extending? What's the consumer? What's the change?
