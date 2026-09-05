---
applyTo: "apps/**,services/**,packages/**"
---

# You are changing what the product does

This file fires because you are editing the source tree. That means a
**specification is now out of date** unless you update it in the same change.

From the constitution, principle I:

> Specs are living artifacts — update them when reality diverges.
> Traceability is checked, not trusted.

## Before you finish

1. Find the spec that owns this behaviour in `.specify/specs/`. If none does,
   the feature needs one.
2. Update its text so it describes what the code now does — not what it was
   planned to do. Where the two disagree, append an amendment rather than
   rewriting: the original is the record of what was believed at the time.
3. Add the unit id to that spec's `units:` frontmatter.
4. Add the ledger entry to `docs/implementation-backlog.md`: what was reported,
   what was actually wrong, what changed.
5. If the **shape** of the system changed — data crossing the trust boundary,
   what the approval gate covers, a loop's cadence, a node or edge type, the key
   hierarchy — update the matching SVG in `docs/diagrams/` (constitution IX).
6. If a **decision** was taken that a future reader would otherwise have to
   reverse-engineer, write an ADR in `docs/adr/`.

`python scripts/spec_drift.py` reports any unit no spec claims, and CI fails on
it. This is not paperwork: the specs stood still for 292 units while the product
was rebuilt around them, and nothing could notice, because nothing was looking.

## While you are in here

- **There is no `vue-tsc`** — esbuild strips types unchecked, so a type error
  surfaces at runtime in front of the owner. Write a mount test.
- **A new Python dependency goes in `pyproject.toml`**, never only in the
  working environment: `uv sync` prunes anything unrequested, and has silently
  removed one four times.
- **Verify with the keys unset**: `OPENAI_API_KEY= ANTHROPIC_API_KEY= uv run
  --package <pkg> --extra dev pytest`. CI has no keys.
- **Never report what has not been verified** (constitution XI) — a missing
  measurement renders as an absence, not as a plausible default.
- **A new brain→runtime call** goes in its own `try` and tolerates a 404 from an
  older robot (constitution X).
