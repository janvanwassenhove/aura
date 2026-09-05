---
feature: "015-spec-coverage"
status: "implemented"
owner: "build"
priority: P1
risk: Low
created: "2026-09-05"
units: [U299, U300, U301, U302, U303, U304, U305, U306, U307, U308]
---

# Feature Specification: Spec Coverage — traceability that a machine checks

**Feature Branch**: `015-spec-coverage`
**Created**: 2026-09-05
**Status**: Implemented
**Owner**: build / method
**Priority**: P1
**Risk**: Low
**Input**: Owner report — *"waarom zie ik in specify en docs folder geen wijzigingen? alles wat we specifiëren, technisch & functioneel, alle features, beslissingen, documentatie, ... zou steeds moeten gebeurd zijn. ga na wat er is fout gelopen en fix it"*

## Background — what went wrong

The constitution's first principle is **Spec-First, Always**, and it ends:

> Specs are living artifacts — update them when reality diverges.

Reality diverged 292 times. `.specify/` was modified three times in the whole
history of the project: the initial scaffold, U231 and U238. No spec has ever
named a unit; every spec still said `status: in-progress`, including the ones
that shipped in June.

Everything the product actually became was recorded instead in
`docs/implementation-backlog.md` — 420 kB of Dutch prose, one entry per unit,
accurate and detailed. But a ledger is a diary and a spec is a contract. A
reader who wants to know *how the product behaves today* should not have to
read the history of how it got there, and a spec that describes a June plan is
worse than no spec, for the same reason a stale diagram is worse than none: it
is believed.

Three separate causes, each sufficient on its own:

1. **The rule was never in view.** `AGENTS.md` is titled "GitHub Copilot Agent
   Instructions" and the constitution lives under `.specify/`. Claude Code
   loads `CLAUDE.md`, which did not exist. Every unit in the autobuild stream
   was written by an agent that had never read principle I.
2. **Nothing checked.** The privacy scan has a pre-commit hook and a CI job;
   release notes have unit tests. Spec traceability had neither, so it degraded
   to a habit — and habits do not survive 292 units at speed.
3. **The ledger absorbed the pressure.** Writing a careful entry every unit
   *felt* like documenting, which is exactly why the gap went unnoticed for
   three months. Effort was going in; it was going to the wrong artifact.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A shipped change cannot silently leave the spec behind (Priority: P1)

As the owner, I want any unit that changes what the product does to be traceable
to the specification it changed, so that the specs describe the product I
actually have rather than the one that was planned in June.

**Why this priority**: it is the constitution's first principle, and it had been
inoperative for the entire life of the autobuild loop.

**Independent Test**: land a commit `auto(U999): something` and run
`python scripts/spec_drift.py` — it must exit 1 and name U999. Add `U999` to any
spec's `units:` frontmatter and it must exit 0.

**Acceptance Scenarios**:

1. **Given** a unit has landed as `auto(UNNN): …` and no spec names `UNNN` in
   its `units:` frontmatter, **When** the spec-coverage check runs, **Then** it
   exits non-zero and names the unit and the fix.
2. **Given** the same unit is listed in a spec's `units:` frontmatter, **When**
   the check runs, **Then** it exits zero.
3. **Given** a spec merely mentions `UNNN` in its prose, **When** the check
   runs, **Then** that does **not** count as coverage — naming a unit in a
   paragraph is not taking responsibility for it.
4. **Given** the check runs in CI on `master`, **When** an unclaimed unit newer
   than the baseline exists, **Then** the CI job fails.

### User Story 2 — The existing debt stays visible instead of being forgiven (Priority: P1)

As the owner, I want the 292 units of missing documentation to be counted and
reported on every run, so that "we will document it later" cannot quietly become
"never".

**Why this priority**: a guard installed on the day the debt is discovered will
otherwise be tuned to pass, and the debt disappears from view.

**Independent Test**: run `python scripts/spec_drift.py` with the current
baseline — it exits 0 (no *new* drift) but prints the outstanding count, and it
never prints "complete" while the count is non-zero.

**Acceptance Scenarios**:

1. **Given** the baseline in `.specify/coverage.json`, **When** the check runs
   and there is no new drift, **Then** it still reports how many units of debt
   remain and how to pay one off.
2. **Given** somebody edits the baseline **forward** to make the check pass,
   **When** the test suite runs, **Then** it fails — the baseline may only move
   backwards, as specs are written.
3. **Given** `--all`, **When** the check runs, **Then** the historical debt
   fails too, so progress can be measured against the real target.

### User Story 3 — The next agent reads the rule before writing code (Priority: P1)

As the owner, I want the working agreement to be loaded automatically by the
tool that does the work, so the failure cannot recur through the same door.

**Independent Test**: `CLAUDE.md` exists at the repository root, states the
spec-first rule and the per-unit obligations, and points at the constitution.

**Acceptance Scenarios**:

1. **Given** an agent session starts in this repository, **When** it reads its
   automatic context, **Then** it has principle I, the per-unit checklist, and
   the location of the specs.
2. **Given** a commit stages code under `apps/`, `services/` or `packages/`
   and no file under `.specify/specs/`, **When** the pre-commit hook runs,
   **Then** it warns (it does not block: the blocking check is in CI, which can
   read commit subjects).

## Functional Requirements

- **FR-001**: Every unit is identified by its commit subject `auto(UNNN): …`.
  A letter suffix (`U242b`) is a distinct unit. The early history batched
  several into one subject — `auto(U2,U3):`, `auto(U19c+U20):`,
  `auto(U112-U115):` — and every unit named in such a subject counts,
  ranges expanded. A checker that reads only the first would under-report its
  own debt, which is the one failure it cannot afford (U300: doing exactly
  that hid 29 units).
- **FR-002**: A spec claims units through a `units:` key in its leading
  frontmatter, as an inline or block YAML list. Mentions elsewhere do not count.
- **FR-003**: The check reports unclaimed units, the reason (in the
  constitution's own words) and the fix.
- **FR-004**: `.specify/coverage.json` holds a baseline unit. Units up to and
  including it are reported debt; later units fail the check.
- **FR-005**: The baseline may only move backwards. A test enforces this against
  the previous committed value.
- **FR-006**: The check runs in CI alongside the privacy scan and the
  release-notes tests.
- **FR-007**: `CLAUDE.md` states the working agreement and is kept in step with
  `AGENTS.md` and the constitution.

## Out of scope

- Checking that a spec's *text* is accurate — only that a unit is claimed by
  one. Accuracy is a human judgement; the machine can only enforce the link.
- Retro-writing specs for the 292 units of debt. That is the work this check
  makes visible and measurable; it is paid off in later units, each moving the
  baseline back.

## Traceability

| Unit | What it delivered |
|---|---|
| U299 | `scripts/spec_drift.py`, `scripts/test_spec_drift.py`, `.specify/coverage.json`, `CLAUDE.md`, CI job, pre-commit warning |
| U300 | Batched and ranged commit subjects counted as the several units they are — the debt went from 292 to its true 321 |
| U301 | Spec 016 — embodiment and presence (36 units) |
| U302 | Spec 017 — voice and language (60 units) |
| U303 | Spec 018 — knowledge, people and judgment (41 units) |
| U304 | Spec 019 — skills, automation and the agentic loop (32 units) |
| U305 | Specs 020 + 021 — the desktop app, its releases, and getting code onto the robot (51 units) |
| U306 | Spec 022 — security and privacy (9 units, tracked against the August audit) |
| U307 | Spec 011 amended — the presentation copilot as it actually is (14 units) |
| U308 | Specs 008 + 010 amended — the D2 console and the connections (45 units) |
