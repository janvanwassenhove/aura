# AURA — Copilot instructions

> **Adaptive Unified Robotic Assistant** — an embodied AI assistant for a
> Reachy Mini robot, delivered as one desktop application a household installs.
> Spec-driven via [GitHub Spec Kit](https://github.com/github/spec-kit).

## Why this file was replaced

Until U316 this file described a **different repository**: a generic "Cognitive
Hub" scaffold with `.apm/`, `knowledge/`, `providers/` and `specs/` — five
directory trees, none of which exist here. It did not contain the word "AURA".
Copilot has been reading instructions for another project since the repository
was created, which is the Copilot-side twin of `CLAUDE.md` not existing at all
(U299).

Four of the five files in `.github/instructions/` had the same problem: their
`applyTo` globs pointed at `.apm/**`, `.github/apm/**` and `specs/**`, so they
could never fire on anything in this tree. Replaced in the same unit.

## Spec Kit commands

| Command | Purpose |
|---|---|
| `/speckit.constitution` | Create or update the governing principles |
| `/speckit.specify` | Define a new feature (requirements + user stories) |
| `/speckit.plan` | Create a technical implementation plan |
| `/speckit.tasks` | Generate an actionable task list from a plan |
| `/speckit.implement` | Execute tasks and build the feature |
| `/speckit.clarify` | Clarify underspecified areas before planning |
| `/speckit.analyze` | Cross-artifact consistency and coverage analysis |

For planned features, work in that order. For the autobuild stream — one
reported problem fixed end to end — follow "what a unit owes" below.

## Project map

| Path | What it contains |
|---|---|
| `apps/desktop/` | The Electron shell — starts the whole stack in one window |
| `apps/aura-brain/` | The one backend process: voice, knowledge, perception, setup |
| `apps/operator-console/` | Vue 3 + TypeScript console (the only user surface) |
| `services/robot-runtime/` | Runs on the Pi: adapters, behaviour engine, camera, motors |
| `services/orchestrator/` | The agentic loop, skills, approval gate, personas |
| `services/connector-service/` | Microsoft 365, Google, GitHub, Slack, MCP, calendar links |
| `services/identity-service/` | OAuth device-code flows and the token store |
| `services/memory-service/` | Sessions, preferences, todos, reminders |
| `packages/shared-schemas/` | Pydantic events and **every ABC** (see below) |
| `packages/shared-events/` | The async event bus |
| `packages/shared-policies/` | What each mode permits; the approval gate's rules |
| `packages/shared-config/` | Settings models per service |
| `.specify/specs/` | What the product does **today** — 22 feature specs |
| `docs/adr/` | Decisions, with the alternatives that were rejected |
| `docs/implementation-backlog.md` | The unit ledger — how it got here, in Dutch |

**The ABCs live in `packages/shared-schemas`, not beside their implementations.**
That is what lets `robot-runtime`, `orchestrator` and `connector-service` depend
on a contract without depending on each other — see `AGENTS.md` for the table of
where each one is.

---

<!-- BEGIN GENERATED: working-agreement — edit docs/agent-working-agreement.md, then run scripts/sync_agent_docs.py -->
## Spec-first, always

The first principle of this project, from `.specify/memory/constitution.md`
(paths in this block are written as code rather than links on purpose: the same
text is injected at three different depths in the tree, and a relative link
correct in one is broken in the others):

> Every feature begins as a specification in `.specify/specs/NNN-name/spec.md`.
> No code is merged without traceability to a spec acceptance criterion.
> **Specs are living artifacts — update them when reality diverges.**
> Traceability is checked, not trusted.

`.specify/specs/` describes what the product does **today**.
`docs/implementation-backlog.md` is the ledger: one Dutch entry per unit,
recording *how we got here*. **One is not a substitute for the other.** A reader
who needs to know how the product behaves must not have to read 420 kB of
history to find out — and writing a careful ledger entry is what *felt* like
documenting for 292 units while the specs stood still.

## One unit, one commit — and what a unit owes

A unit is one reported problem, fixed end to end, landing as exactly one commit
`auto(UNNN): title`. Before it is finished it owes **all** of these, in that
same commit:

| | What | Where |
|---|---|---|
| 1 | The change, with tests **verified red** against the old code | the source tree |
| 2 | The spec updated to match what the code now does, with the unit id in its `units:` frontmatter | `.specify/specs/NNN-*/spec.md` |
| 3 | The ledger entry — what was reported, what was actually wrong, what changed | `docs/implementation-backlog.md` |
| 4 | The drawing, **if the shape changed** (constitution IX) | `docs/diagrams/*.svg` |
| 5 | An ADR, **if a decision was taken** a future reader would otherwise reverse-engineer | `docs/adr/` |

Then commit, push to `aura-autobuild` **and** to `master` (master builds the
release), and fast-forward local `master`.

### Claiming a unit

Every spec's frontmatter lists the units that shaped it:

```yaml
---
units: [U263, U264, U265]
---
```

`python scripts/spec_drift.py` reports every shipped unit that no spec claims,
and CI fails on any of them. Mentioning a unit in prose does **not** claim it.

## Non-negotiables

- **Hardware abstraction** — nothing above `robot-runtime` imports a Reachy SDK
  type. `RobotAdapter` is the boundary and lives in
  `packages/shared-schemas/src/shared_schemas/robot/adapter.py`. `FakeRobot` is
  the primary target; every flow works without hardware.
- **Events drive state** — typed Pydantic events on the shared in-process bus,
  versioned in `packages/shared-schemas`. The console consumes; it never pushes.
  An event only reaches a subscriber that exists when it is published, so state
  that must survive a late subscriber is **polled**, not awaited.
- **Safety gates are inviolable** — anything touching the outside world goes
  through the approval gate. Offline-queued sensitive actions never auto-run on
  reconnect.
- **Never report what has not been verified** (constitution XI, ADR-009) — a
  missing measurement renders as an absence, a mock says it is a mock,
  constructing is not connecting, and `unknown` is not a status. The console
  composes presentation, never truth.
- **The Pi is older than the app** — every new brain→runtime call goes in its
  own `try`, must not break the sequence around it on a 404, and reports the
  degradation rather than plain success.
- **No sensitive data in logs, and none in git** — tokens, mail bodies,
  calendar detail, identity. The pre-commit privacy scan and CI enforce git.
- **Change the shape, change the drawing** — a diagram that used to be true is
  worse than no diagram, because it is believed.

## Traps specific to this repository

- **There is no `vue-tsc`.** esbuild strips types unchecked, so a type error
  surfaces at runtime in front of the owner. Mount tests are the only defence —
  a store or view change ships with one.
- **`uv sync` prunes extras that are not requested.** This has silently removed
  a dependency four times (U179, U213, U246, U266). A new dependency goes in
  `pyproject.toml`, never only in the working environment.
- **Verify with the keys unset**: `OPENAI_API_KEY= ANTHROPIC_API_KEY= uv run
  --package <pkg> --extra dev pytest`. CI has no keys; a shell that has them
  hid a red build for six hours (U283).
- **Never point a demo or screenshot stack at `./data`.** Set
  `KNOWLEDGE_DB_PATH`, `RECOGNITION_DB_PATH`, `MODE_POLICY_PATH`,
  `DATABASE_URL`, `SKILLS_DIR`, `CONNECTOR_PREFS_PATH` and `MCP_SERVERS_PATH`
  at throwaway paths first.
- **Heredocs mangle `\b` and `\n` on Windows.** Write the patch script to a
  file and run it — this has cost two units on its own.
- **The knowledge passphrase exists only in the Windows credential store.**
  No second copy, no recovery: losing it loses the encrypted profiles and faces.
- **The projector overlay is a separate window with its own store.** Anything
  two windows must agree on crosses an explicit channel — a `storage` event or
  the brain — never by assumption.

## Where things are

| Path | What |
|---|---|
| `.specify/memory/constitution.md` | The governing principles. Read first. |
| `.specify/specs/NNN-*/` | `spec.md` (what and why), `plan.md`, `tasks.md` |
| `.specify/coverage.json` | The spec-coverage baseline |
| `docs/implementation-backlog.md` | The unit ledger — history, in Dutch |
| `docs/adr/` + `docs/adr/README.md` | Decisions, with the rejected alternatives |
| `docs/architecture/overview.md` | How the parts fit together today |
| `docs/diagrams/` | The canonical drawings (part of the contract) |
| `scripts/spec_drift.py` | Which units no spec accounts for |
| `scripts/check_doc_links.py` | Every relative documentation link resolves |
| `scripts/privacy_scan.py` | The gate that keeps personal data out of git |
<!-- END GENERATED -->
