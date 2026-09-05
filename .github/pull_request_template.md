## What was reported

<!-- The problem in the reporter's words, if there was one. -->

## What was actually wrong

<!-- The cause, not the symptom. If the symptom had several causes, say so. -->

## What changed

---

### The unit checklist

Constitution I and the working agreement in `CLAUDE.md` / `AGENTS.md` /
`.github/copilot-instructions.md`. CI enforces the starred ones.

- [ ] Tests, **verified red** against the old code
- [ ] ★ The spec updated, with the unit id in its `units:` frontmatter (`python scripts/spec_drift.py`)
- [ ] The ledger entry in `docs/implementation-backlog.md`
- [ ] The drawing in `docs/diagrams/`, **if the shape changed** (constitution IX)
- [ ] An ADR in `docs/adr/`, **if a decision was taken**
- [ ] ★ No personal data (`python scripts/privacy_scan.py --all`)
- [ ] ★ Documentation links resolve (`python scripts/check_doc_links.py`)
- [ ] Verified with the API keys **unset** — CI has none
