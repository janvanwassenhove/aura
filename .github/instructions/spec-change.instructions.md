---
applyTo: ".specify/**"
---

# You are editing a specification

`.specify/specs/` describes what the product does **today**. It is a contract,
not a diary — `docs/implementation-backlog.md` is the diary.

- **Amend, do not rewrite.** Where reality has moved past the original text,
  append an `## Amendment — <date>` section. The original is the record of what
  was believed at the time, and deleting it deletes the reason.
- **`units:` frontmatter is a claim of responsibility.** List every unit that
  shaped this spec. Mentioning a unit in prose claims nothing —
  `scripts/spec_drift.py` only reads the frontmatter, on purpose.
- **Status must be true.** `implemented`, `blocked` (with what is missing and
  who can supply it), or `in-progress` only while somebody is actually working
  on it. `in-progress` on a spec nobody is touching is the same plausible
  default as "battery 100%" (constitution XI).
- **Every relative link is checked** by `scripts/check_doc_links.py` in CI.
- Changing the constitution requires a documented rationale, an update to the
  affected ADRs, and a version bump in its Governance section.
