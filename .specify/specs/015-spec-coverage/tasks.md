---
feature: "015-spec-coverage"
---

# Tasks: Spec Coverage

**Prerequisites**: `spec.md` (done), `plan.md` (done)

## Phase 1: The check

- [x] T001 [US1] `scripts/spec_drift.py` — read units from the git log, claims from spec frontmatter, report the difference
- [x] T002 [US1] `scripts/test_spec_drift.py` — unit parsing, claim parsing, prose does not count, report names the fix
- [x] T003 [US2] `.specify/coverage.json` — baseline + the reason it exists, in the file itself
- [x] T004 [US2] Baseline split, the outstanding count on every run, and `--all` to fail on the debt too
- [x] T005 [US2] Test: the baseline may only move backwards, compared against the committed value

## Phase 2: Where it runs

- [x] T006 [US1] CI job `Spec coverage` next to the privacy scan and release-notes tests
- [x] T007 [US3] `.githooks/pre-commit` — warn when code is staged and no spec is

## Phase 3: The rule in view

- [x] T008 [US3] `CLAUDE.md` — spec-first, what a unit owes, the repository's practical traps
- [x] T009 [US3] This spec, claiming U299, as the first worked example of the mechanism

## Phase 4: Paying off the debt *(later units)*

- [ ] T010 Specs for the presentation copilot as it now exists (U263–U269, U282)
- [ ] T011 Specs for knowledge, people and the judgment layer (U243–U245, U271–U281, U290, U293, U294)
- [ ] T012 Specs for voice and language (U256–U258, U260, U275, U287–U292)
- [ ] T013 Specs for the desktop app, self-update and robot deployment (U239–U242b)
- [ ] T014 Specs for connections and capabilities (U254–U255, U295, U298)
- [ ] T015 Amend ADRs where a decision has since been reversed or extended
- [ ] T016 Move the baseline back with each of the above
