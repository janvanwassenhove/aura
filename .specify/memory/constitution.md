# AURA Constitution
<!-- Adaptive Unified Robotic Assistant — Reachy Chief of Staff -->

## Core Principles

### I. Spec-First, Always
Every feature begins as a specification in `.specify/specs/NNN-name/spec.md`.  
No implementation task is created without a corresponding spec entry.  
No code is merged without traceability to a spec acceptance criterion.  
Specs are living artifacts — update them when reality diverges.  
**Traceability is checked, not trusted.** Every unit names itself in the `units:` frontmatter of the spec whose behaviour it changed; `scripts/spec_drift.py` reports any unit no spec accounts for, and CI fails on it.  
Precedent: this principle was inoperative for 292 units — `.specify/` was touched three times while the product was rebuilt around it, and nothing could notice, because nothing was looking (U299, spec 015).

### II. Hardware Abstraction is Non-Negotiable
The orchestrator, behavior engine, and all higher-level services MUST NOT import or reference Reachy-specific SDK types.  
All robot interaction goes through the `RobotAdapter` ABC.  
`FakeRobot` is the primary development target — every flow must work without physical hardware.  
`ReachyRobotAdapter` is a later addition; it must pass the same contract tests as `FakeRobot`.

### III. Events Drive State (No Direct Coupling)
All state changes are communicated via typed Pydantic events on the shared event bus.  
Services subscribe to events; they do not call each other directly for state updates.  
Every event must be a versioned Pydantic model in `packages/shared-schemas`.  
The operator console is the passive consumer of events — it does not push state.

### IV. Safety Gates are Inviolable
Any tool call touching external systems (send mail, post Teams message, create event, delete task) requires explicit approval from the `ApprovalManager` if flagged in `shared-policies`.  
Offline-queued sensitive actions MUST NOT auto-execute on reconnect without fresh approval.  
Work mode and home mode have separate, non-overlapping permission sets.  
OpenClaw (and any external agent) cannot bypass the orchestrator or approval gate.

### V. Voice Pipeline is Pluggable
The default voice transport is **OpenAI Realtime API** (low latency, WebSocket).  
The fallback is **local Whisper + Kokoro/Piper TTS** (offline-capable, higher latency).  
Both paths implement the same `STTProvider` / `TTSProvider` ABCs.  
Selection is via `STT_PROVIDER` / `TTS_PROVIDER` environment variables — never hardcoded.  
Interruption handling and word-level timing must be supported by both paths.

### VI. No Sensitive Data in Logs
Auth tokens, M365 content (mail bodies, calendar details), personal preferences, and user identity data MUST NOT appear in log output.  
MSAL token caches are memory-only in development and must use per-session isolation in production.  
Audit logs record action metadata (tool name, mode, timestamp, approval status) but never payload content.  
Log levels DEBUG/INFO may log tool names; they must not log tool arguments containing personal data.

### VII. Simplicity Over Cleverness
Start with the simplest implementation that makes the spec tests pass.  
YAGNI: do not implement features not in a current spec.  
SQLite is the dev persistence layer — Postgres-readiness is achieved via `MemoryStore` ABC, not dual implementations.  
The event bus is asyncio in-process for dev — Redis Streams is documented in ADR-002 but not implemented until the spec calls for it.  
Avoid over-engineering: one service per bounded context, one ABC per interface.

### VIII. Test-Driven for Core Contracts
`RobotAdapter` contract tests must pass for any adapter implementation (FakeRobot, ReachyAdapter).  
`Connector` contract tests must pass for any connector implementation (mock, WorkIQ).  
`MemoryStore` contract tests must pass for any store implementation (SQLite, Postgres).  
Unit tests cover: schema serialization, behavior state transitions, approval gate logic.  
Integration tests cover: full text turn → intent → tool → fake motion → transcript.

### IX. The Drawings Are Part of the Contract
`docs/diagrams/` holds the canonical drawings of this system: the trust boundary, one turn, the loops, the knowledge model, envelope encryption, the bounds on a delegated agent, hook ordering, and the build loop.  
A change to the **shape** of the system is not done until the drawing matches it — a unit that moves data across the trust boundary, changes what the approval gate covers, alters a loop's cadence, adds a node or edge type, changes the key hierarchy, or moves a sub-agent's bounds must update the corresponding SVG in the same unit.  
A diagram that used to be true is worse than no diagram, because it is believed.  
`docs/diagrams/README.md` lists which file covers what, and the house style for adding one.

### X. The Two Hosts Update Separately
The laptop updates itself (in-app updater, several releases a day); the Pi is flashed by hand and stays on whatever it was last given.  
**A brain newer than the runtime it talks to is the NORMAL state of this system**, not an edge case — so every brain→runtime call added after the fact must be OPTIONAL: a 404 from an older robot is deployment skew, not a fault.  
Concretely: call a new endpoint in its own `try`, never in the same block as the behaviour it accompanies, and never as the first step of a sequence that must still happen without it.  
When the optional half is missing, SAY so in the response instead of reporting plain success — the owner should hear about a degradation from the app, not discover it by watching the robot.  
Precedent: U195 (new camera route, probed once, falls back to the legacy stream) got this right. U237 did not: one 404 made the sleep button do nothing at all while the app reported success (fixed in U238).

### XI. Never Report What Has Not Been Verified
A value is reported only if it has been measured or proven. Where it has not, the ABSENCE is reported — in the owner's language, with the next step attached.  
Concretely: never substitute a plausible default for a missing measurement; a mock says it is a mock; constructing is not connecting (green is earned by a probe that exercises the real path); and `unknown` is not a status, because it is the only answer nobody can act on.  
The console composes presentation, never truth: every status, capability and knowledge state it shows comes from the brain.  
**The cost is asymmetric.** "I don't know" costs a moment. "It's fine" when it is not costs the owner's trust in everything else the system says.  
Precedent: ten instances of one shape — a green badge over canned data (U52), "sleep: done" on a 404 (U238), "following" with a dead tracker (U253), "battery 100%" from an SDK that measures none (U270), "nothing is being remembered" while it was (U290), "CI is green" for six hours while it was red (U283). None was a crash; every one was believed. Rationale in [ADR-009](../../docs/adr/ADR-009-honest-state.md).

---

## Architecture Constraints

- **Python 3.11+** for all backend services; **TypeScript** for the operator console
- **FastAPI + asyncio** for all service APIs; **Pydantic v2** for all data models
- **Vue 3 + Vite + TypeScript + Pinia + TailwindCSS** for the operator console
- **uv** as the Python package manager for all services and packages
- **Docker Compose** for local development orchestration
- Speech, movement, and behavior are coordinated through the **timeline scheduler** in `robot-runtime`
- Tool calls must not block the audio/motion event loop
- Services communicate via the shared **WebSocket event bus** for real-time events; REST for commands

---

## M365 / Work IQ Constraints

- **Work IQ MCP** (`agent365.svc.cloud.microsoft`) is the preferred Microsoft 365 connector
- All 4 Work IQ MCP servers (Teams, Mail, Calendar, Planner) are accessed via MSAL OBO flow
- Dev/FakeRobot mode uses mock connectors (`M365_CONNECTOR=mock`) — no M365 license required
- Production mode uses real Work IQ MCP (`M365_CONNECTOR=workiq`) — requires M365 Copilot license
- Copilot Studio and Agent 365 SDK are explicitly NOT required (direct MCP over HTTPS)

---

## Development Workflow

1. Feature branch named `NNN-feature-name` matching spec folder
2. Spec (`spec.md`) written and reviewed before `plan.md` is created
3. Plan (`plan.md`) reviewed before `tasks.md` is generated
4. Tasks executed in order; `[P]` tasks may run in parallel
5. Acceptance criteria verified before merging
6. Spec status updated to `implemented` after merge

For the autobuild stream — one reported problem, fixed end to end, landing as
exactly one commit `auto(UNNN): title` — a unit is not finished until **all** of
these are in that same commit:

| | What | Where |
|---|---|---|
| 1 | The change, with tests verified **red** against the old code | the source tree |
| 2 | The spec updated to match what the code now does, with the unit in its `units:` frontmatter | `.specify/specs/NNN-*/spec.md` |
| 3 | The ledger entry — what was reported, what was actually wrong, what changed | `docs/implementation-backlog.md` |
| 4 | The drawing, if the shape changed (principle IX) | `docs/diagrams/*.svg` |
| 5 | An ADR, if a decision was taken a future reader would otherwise have to reverse-engineer | `docs/adr/` |

The ledger records *how we got here*; the spec records *what is true now*. One
is not a substitute for the other, and treating it as one is exactly what
principle I now checks for.

---

## Governance

This constitution supersedes all other practices and README instructions.  
Amendments require: documented rationale, update to affected ADR(s), migration plan for existing code.  
All PRs must verify compliance with the Hardware Abstraction and Safety Gates principles.  
Complexity violations must be justified in `.specify/specs/NNN/plan.md` under the **Complexity Tracking** section.

**Version**: 1.3.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-09-05 (added principle XI; principle I now names its enforcement; the workflow states what a unit owes)
