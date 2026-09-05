---
feature: "015-spec-coverage"
---

# Implementation Plan: Spec Coverage

**Prerequisites**: `spec.md`

## Technical decisions

### The commit subject is the unit id — no new bookkeeping

Every unit already lands as exactly one commit `auto(UNNN): title`. That
convention has held for 292 units and is what `scripts/release_notes.py`
already builds the release page from. Reusing it means the check needs no
second source of truth and cannot fall out of step with one.

**Rejected**: a `units.yaml` manifest. Anything that must be updated *as well
as* the spec is one more thing to forget, and forgetting is the failure being
fixed.

### The claim lives in the spec, not next to it

A `units:` key in the spec's own frontmatter puts the claim where the person
updating the spec is already typing. Parsing is deliberately narrow: only the
frontmatter block counts, so a spec that mentions a unit in a paragraph has not
thereby claimed it. The alternative — scanning the whole document — would let
prose that merely refers to history register as coverage, which is exactly the
kind of "documented" that produced this situation.

**No YAML dependency**: the parser reads the leading `---` block and extracts
unit tokens from the `units:` key with a regex. `scripts/` runs in CI with
nothing but `pytest` installed, and adding a dependency to a guard makes the
guard fragile.

### A baseline, not an exemption list

292 unclaimed units cannot be fixed in one commit, and a check that fails from
the moment it is installed gets disabled. A single baseline unit in
`.specify/coverage.json` divides admitted debt from new drift.

Two properties make it honest rather than convenient:

* the outstanding count is printed on **every** run, and the check never says
  "complete" while it is non-zero;
* a test compares the baseline against the previous committed value and fails
  if it moved forward. The only way to make the number go down is to write the
  spec.

**Rejected**: an explicit list of 292 forgiven unit ids. Exact, but it invites
appending to it, which is the same failure with more ceremony.

### Warn in the hook, fail in CI

The pre-commit hook cannot see the commit subject — the commit does not exist
yet — so it cannot know which unit is landing. It can see the staged files, and
"code is changing and no spec is" is worth saying while the fix still costs
nothing. Blocking belongs in CI, which reads the log.

## Files

| File | Role |
|---|---|
| `scripts/spec_drift.py` | The check |
| `scripts/test_spec_drift.py` | Its tests, including the one-way baseline |
| `.specify/coverage.json` | Baseline + why it exists |
| `CLAUDE.md` | The working agreement, loaded automatically |
| `.github/workflows/ci.yml` | The `Spec coverage` job |
| `.githooks/pre-commit` | The warning |
