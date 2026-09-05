# AURA — working agreement

> Read this before changing anything. **[`AGENTS.md`](AGENTS.md)** and
> **[`.specify/memory/constitution.md`](.specify/memory/constitution.md)** are
> the governing documents; this file exists so that an agent working here is
> actually holding them.

## Why this file exists

It was missing, and that cost 292 units.

`AGENTS.md` is titled "GitHub Copilot Agent Instructions" and the constitution
lives under `.specify/`. Neither is loaded automatically by Claude Code, which
reads `CLAUDE.md`. So the first principle of this project —

> **Spec-First, Always.** Every feature begins as a specification in
> `.specify/specs/NNN-name/spec.md`. No code is merged without traceability to
> a spec acceptance criterion. **Specs are living artifacts — update them when
> reality diverges.**

— was never in view during the entire autobuild stream. `.specify/` was touched
three times in 292 units. Everything the product actually became went into
`docs/implementation-backlog.md` instead: a 420 kB Dutch diary, honest and
detailed and completely disconnected from the contract it was supposed to keep
current. Asked as *"waarom zie ik in specify en docs folder geen wijzigingen?"*
— and the answer was that nothing, anywhere, connected the two.

`scripts/spec_drift.py` now connects them, and CI runs it. This file makes sure
the rule is read before the code is written rather than after.

## One unit, one commit — and what a unit owes

A unit is one reported problem, fixed end to end. Before it is finished it owes
**all** of these, in the same commit:

| | What | Where |
|---|---|---|
| 1 | The change, with tests that were **verified red** against the old code | the source tree |
| 2 | The specification updated to match what the code now does, with the unit id in its `units:` frontmatter | `.specify/specs/NNN-*/spec.md` |
| 3 | The ledger entry, in Dutch — what was reported, what was actually wrong, what changed | `docs/implementation-backlog.md` |
| 4 | The drawing, **if the shape changed** (constitution IX) | `docs/diagrams/*.svg` |
| 5 | An ADR, **if a decision was taken** that a future reader would otherwise have to reverse-engineer | `docs/adr/` |

Then: commit, push to `aura-autobuild` **and** to `master` (master builds the
release), and fast-forward local `master`.

The ledger is not a substitute for the spec. It records *how we got here*; the
spec records *what is true now*. A reader who needs to know how the product
behaves must not have to read 420 kB of history to find out.

### Claiming a unit

Every spec's frontmatter lists the units that shaped it:

```yaml
---
units: [U263, U264, U265]
---
```

`python scripts/spec_drift.py` reports every shipped unit no spec claims. CI
fails on any unclaimed unit newer than the baseline in
`.specify/coverage.json`. That baseline is the honest boundary between the debt
that already existed and the discipline that starts now, and it may **only move
backwards**.

## Non-negotiables (constitution, short form)

- **Hardware abstraction** — nothing above `robot-runtime` imports a Reachy SDK
  type. `FakeRobot` is the primary target; every flow works without hardware.
- **Events drive state** — typed Pydantic events on the bus, versioned in
  `packages/shared-schemas`. The console consumes; it never pushes.
- **Safety gates are inviolable** — anything touching the outside world goes
  through the approval gate. Offline-queued sensitive actions never auto-run on
  reconnect.
- **No sensitive data in logs, and none in git** — tokens, mail bodies,
  calendar detail, identity. The pre-commit privacy scan and CI enforce the
  second half; the first half is on you.
- **The Pi is older than you think** — any new brain→runtime call goes in its
  own `try`, must not break the sequence around it on a 404, and reports the
  degradation rather than plain success.
- **Change the shape, change the drawing** — a diagram that used to be true is
  worse than no diagram, because it is believed.

## Practical notes for this repository

- **No `vue-tsc`.** esbuild strips types unchecked, so a type error surfaces at
  runtime, in front of the owner. Mount tests are the only defence — write one.
- **`uv sync` prunes extras that are not requested.** This has cost four units
  (U179, U213, U246, U266). A new dependency goes in `pyproject.toml`, not in
  the working environment.
- **Verify with the keys unset**: `OPENAI_API_KEY= ANTHROPIC_API_KEY= uv run
  --package <pkg> --extra dev pytest`. CI has no keys; a shell that does hid a
  red build for six hours (U283).
- **Never point a demo or screenshot stack at `./data`.** Set
  `KNOWLEDGE_DB_PATH`, `RECOGNITION_DB_PATH`, `MODE_POLICY_PATH`,
  `DATABASE_URL`, `SKILLS_DIR`, `CONNECTOR_PREFS_PATH` and `MCP_SERVERS_PATH`
  at throwaway paths first.
- **Heredocs mangle `\n` and `\b` on Windows.** Write the patch script to a
  file and run it.
- **The knowledge passphrase exists only in the Windows credential store.**
  There is no second copy; losing it loses the encrypted profiles and faces.

## Where things are

| Path | What |
|---|---|
| `.specify/memory/constitution.md` | The governing principles. Read first. |
| `.specify/specs/NNN-*/` | `spec.md` (what and why), `plan.md`, `tasks.md` |
| `.specify/coverage.json` | The spec-coverage baseline and the debt it admits |
| `docs/implementation-backlog.md` | The unit ledger — history, in Dutch |
| `docs/adr/` | Decisions, with the alternatives that were rejected |
| `docs/architecture/overview.md` | How the parts fit together today |
| `docs/diagrams/` | The canonical drawings (part of the contract) |
| `scripts/spec_drift.py` | Which units no spec accounts for |
| `scripts/privacy_scan.py` | The gate that keeps personal data out of git |
| `AGENTS.md` | The project map, key interfaces, workspace rules |
