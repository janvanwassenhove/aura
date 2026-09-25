# Testing audit — September 2026

**Asked for (translated):** *"do a full review and audit of testing; all specs
should be tested and validated at all times on any release, automated; and
implement all fixes — there is too much regression at the moment, and that
should no longer be the case."*

This is the living tracker, in the same shape as
[`audit-2026-08.md`](audit-2026-08.md): findings numbered `T…`, each with a
status that a unit updates when it lands. Every number below was measured on
the tree at U367b, by script, not estimated.

## The headline

The suites are large and they run: **1,828 tests** across ten Python suites,
the console and `scripts/`, and CI executes all of them. Regression is not
coming from a lack of tests. It comes from three structural gaps, and the
twelve repeat-reports since U300 all fall through one of them:

| Gap | What it looks like from the owner's chair |
|---|---|
| **Two hand-kept gates, already drifted.** CI and Release each carry their own list of what to run. They differ today. Release never runs the repository checks at all. | CI red for seven units while installers kept shipping (U361–U367). |
| **A spec is claimed, not validated.** `spec_drift.py` checks *unit → spec*. Nothing checks *spec → test*. 122 of 394 claimed units are named by no test; the fifteen retro-specified specs have **zero** acceptance scenarios traceable to any test. | "Quiet does nothing" fixed at the turn gate (U332) while the session it needed to cover had no test and kept the mic open (U366). |
| **Whole surfaces no test ever touches.** Five of ten console views, seven stores, the Electron main process, `shared-config`. There is no `vue-tsc`, so an untouched view fails in the owner's window, not in CI. | `App.vue` had never been mounted; a missing import shipped green (U365). The event bridge had no tests at all (U365). |

Twelve of the 71 ledger entries since U300 describe a repeat of something
already fixed: U301, U318, U319, U323, U327, U329, U334, U337, U358, U362,
U366, U367. That is the number this audit exists to move.

## Findings

| # | Sev | Finding | Status |
|---|---|---|---|
| T1 | **critical** | **Release does not depend on CI, and keeps its own copy of the test list.** `release.yml` re-lists the Python suites, the console and the desktop checks by hand. That copy already lacks `identity-service` and `test-brain-launch.cjs`, and it runs none of the repository checks (privacy, spec drift, doc links, agent-docs sync, `scripts/`). So a red CI ships. U337 removed one hand-kept list; U367 removed a second; this is the third and the only one that decides whether a build reaches the owner. | **done (U368)** — `checks.yml` is the one list; `ci.yml` and `release.yml` both `uses:` it and `build`/`release` depend on that job. `scripts/test_release_gate.py` refuses a second list in either caller and walks the tree for suites the gate does not run. Found a third omission on its first run: see T11. |
| T2 | **critical** | **No link from a spec to a test.** The constitution says "no code merged without traceability to a spec acceptance criterion", and the only check goes the other way. Per spec, the units no test names: 020 desktop 40/61, 015 spec-coverage 13/19, 008 console 19/40, 017 voice 19/68. Of 394 claimed units, **122** are named by no test. Recent ones include U333, U343, U344, U354, U355. | **done (U369)** — `scripts/spec_tests.py` runs in the gate. 122 units of debt sit behind `tests_baseline: U367b` in `.specify/coverage.json`, reported on every run; every unit after it must be named by a test or the gate fails. `--list` prints the debt. Paying it down is T2's remainder and is tracked by that number. |
| T3 | **high** | **Fifteen specs have acceptance scenarios that trace to nothing.** 001–015 were retro-specified (U299) with scenarios and FRs carrying no unit ids, so T2 cannot even see them. 182 scenarios, 0 traceable. | **open**: paying this is writing, not code. Tracked here so the number stays visible; not started in this pass. |
| T4 | **high** | **Half the console is never mounted by a test.** Views never imported by any test: `TalkView` (the main screen), `ModesView`, `GraphView`, `ActivityView`, `AboutView`. Stores: `modeStore` (the Quiet switch), `capabilitiesStore`, `mcpStore`, `navStore`, `presenterStore`, `settingsStore`, `setupStore`. Components: `SetupWizard`, `ApprovalPanel`, `MindCanvas`, `ActivityLog`, `ConfirmDialog`, `NavRail`, `WikiText`, `KnowledgeGraph`, `CapabilityRow`. Composables: `useEventBusWs`, `useModal`. With no `vue-tsc`, a mount test is the only compile step this app has. | **done (U370)** — three sweeps that read their list from the code, not from a list of their own: every view in `navStore`'s `View` union mounts inside the shell; every `.vue` under `src/components` mounts with its required props; every `use*Store` under `src/stores` constructs, plus the Quiet switch's write-through and snap-back. All ten views mounted clean on the first run — the value is that an eleventh cannot arrive unmounted. |
| T5 | **high** | **Nothing runs the gate locally.** No `Makefile`, no root script, no single command that does what CI does. So "verified locally" means "ran the suite I remembered" — U367b was verified in a primed venv and was wrong. | **done (U372)** — `python scripts/gate.py` reads `checks.yml` and runs its steps through bash, in the runner's order, with each step's `working-directory` and `env`; `--job`, `--list`, `--keep-going`. It is the file, not a copy: a step added to the gate runs here next time. The working agreement now names it as what "verified locally" means. |
| T6 | **medium** | **The robot being behind the laptop is invisible in the app.** `deploy_robot.py --check` compares commits and the Pi's `/health` reports its `build`, but nothing in the brain or console shows it. The Pi drifting 74 commits behind was the original U240 report; today it is one commit behind and nobody would know. Every "the fix did not work" that is really "the fix is not on the Pi" lands here. | **done (U371)** — `/robot/status` carries `build: {robot, laptop, behind}`; the Connection card says *behind this laptop — run deploy_robot.py*, *same build*, or *cannot compare*. A packaged app learns its commit from a `BUILD_COMMIT` stamp the release writes; a checkout asks git; neither → an absence, never a guess. The robot was off while this landed, so the live line was not seen — the unit tests and U240's `/health.build` are what stand behind it until the next deploy. |
| T7 | **medium** | **The Electron main process has no unit tests**, only lint and five ad-hoc `test-*.cjs` scripts (which do run). 968 lines including the bootstrap, env pinning (U327) and the updater. The U327 class of bug — a setting silently reset by an update — lives here and is tested only by the owner noticing. | **done (U375)** — `apps/desktop/test-brain-env.cjs` pins all eleven owner-state paths under the owner's data directory, that an explicit `.env` value wins over each default, that voice providers are forced off, and that the U371 build stamp reaches the brain. Source-level, like its siblings (main.cjs requires `electron` at load); proven red against the exact U327 regression — one path defaulting to `./data` — and in the gate. |
| T8 | **medium** | **`shared-config` (233 lines, identity + connector config) has no tests.** Every connector reads it. | **done (U374)** — twelve tests: the enabled-connector list is parsed and trimmed and never contains an empty entry; the keyring backend is chosen by the environment and an unknown one is refused; the keyring passphrase and the Azure client secret never appear in `repr`, `str` or `model_dump`; a developer's `.env.local` cannot leak into the suite; unknown env keys are ignored. In the gate. |
| T9 | **low** | **A flaky assertion shipped and failed in CI's absence.** `test_brain_bundle` asserted a three-letter name was absent from base64 (U342); it failed on the first unlucky nonce (U365). The suite is not run under `pytest-randomly` or repeated, so order- and seed-dependence is found by the owner. | fixed for that test (U365); **open**: no general flake detection. Not started. |
| T11 | **low** | **`packages/shared-prompts/tests/` has existed since April and contains only `__init__.py`.** A scaffolded suite nobody ever wrote a test for; pytest on it exits 5, so it cannot even be added to the gate as-is. Found by the T1 tree walk. | **done (U373)** — six tests on rendered text (persona, guardrail lines, no HTML-escaping into a prompt, the approval wording, the context count), and the suite is in the gate. |
| T12 | **medium** | **A commit that edits `release.yml` does not publish its own release.** Observed twice, with zero counterexamples: U368 and U371 — the only two commits in this pass that changed `release.yml` — reached *Publish release* with the normal token (`Contents: write` printed at job start) and were refused with HTTP 403 *Resource not accessible by integration*; U369, U369b and U372, which did not touch the file, published v2.0.177–179 through the identical workflow. Tag numbers were fresh each time. Not explained; recorded as a rule of thumb: the *next* commit ships. | **open**: reproduce deliberately with a comment-only edit to `release.yml`, then decide — accept, or move publishing to a `workflow_run` on CI success so the file that publishes is never the file that changed. |
| T10 | **low** | Three tests skip by environment (`test_reachy_live.py` needs hardware, `test_laptop_tools.py` is Windows-only, `test_person_prefs.py` needs the console tree). Acceptable and honest; listed so they are known. | accepted |

## What "validated on every release" means now (T1, T2, T5 landed)

1. **One gate.** `checks.yml` is the only list of what must pass. CI runs it on
   every push; Release runs the same jobs and builds nothing until they are
   green. Adding a suite means adding it in one place, and a test refuses a
   second list.
2. **Every claimed unit is named by a test.** A unit is a fix; a fix nothing
   names is a fix the next refactor deletes. `spec_tests.py` fails the gate on
   any new unit without one. The 122 of historical debt are reported on every
   run and may only go down.
3. **The gate runs on the laptop with one command**, reading the same file CI
   reads. "Verified locally" then means the same thing as "CI is green".

What it does **not** mean: that the specs' prose is exhaustively covered.
T3 is the honest remainder — 182 retro-written scenarios with nothing behind
them — and it is writing, to be paid down spec by spec.

## State after the first pass (U368–U375)

| Landed | Still open |
|---|---|
| T1 one gate — `checks.yml`, CI and Release both call it; a second list is refused by test | T3 — 182 retro-specified scenarios trace to nothing (writing) |
| T2 spec → test — `spec_tests.py` in the gate; 117 units of debt behind a baseline that only shrinks | T9 — no general flake detection |
| T4 every view, component and store is mounted or constructed, from the code's own lists | T12 — a commit that edits `release.yml` does not publish its own release (observed twice) |
| T5 `gate.py` runs the gate here from the file CI reads | |
| T6 the robot being behind the laptop is a line in the Connection card | |
| T7 every owner-state path the shell hands the brain is pinned, red on the U327 class | |
| T8 `shared-config` has its first tests, secrets proven not to print | |
| T11 `shared-prompts` has its first tests, and the gate runs them | |

Suites in the gate went from ten to twelve; tests from 1,828 to 1,931. The
number to watch is the one `spec_tests.py` prints on every push: **122** on
the day of the audit, **117** at the end of the pass — not because five tests
were written, but because the check had ignored the desktop's `test-*.cjs`
suite, which guards U224, U229, U234, U239 and U344 (U375b). It goes down when
a test is written and names its unit; it cannot go up without the gate going
red.

## Method

- CI/Release lists: `diff` of the `--package` and `test-*.cjs` mentions in the
  two workflows.
- Unit → test: every `U\d+[a-z]?` token in any `test_*.py` / `*.test.ts`
  against every unit in a spec's `units:` frontmatter. A mention in a
  docstring counts, because that is this repository's convention for saying
  which fix a test guards; a unit mentioned nowhere in `tests/` is a unit no
  test knows about.
- Console reachability: which `src/` files any `tests/**/*.test.ts` imports.
- Repeat reports: ledger entries since U300 whose text says the problem was
  reported again, still present, or a regression.
