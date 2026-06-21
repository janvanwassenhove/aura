# docs/method — archived delivery-method material

This directory holds the generic "agentic delivery method" framework (APM /
spec-kit knowledge base: constitution, governance, playbooks, templates) that
shipped with the original scaffold. It is **not product documentation** for AURA
and is **not load-bearing** — no service imports or depends on it.

It was moved here from the repo root (`knowledge/`) per
[ADR-007](../adr/ADR-007-topology-and-capability-reshape.md) decision #6 ("demote
the delivery-method ceremony") to keep the product tree focused on the robot.

The actual AURA governing document is the
[constitution](../../.specify/memory/constitution.md); feature specs live in
[`.specify/specs/`](../../.specify/specs/). Architecture decisions are in
[`docs/adr/`](../adr/) and the migration plan in
[`docs/reshape-plan.md`](../reshape-plan.md).

The local-only `.github/apm/` tree (gitignored) is the same framework's tooling
and is similarly non-load-bearing.
