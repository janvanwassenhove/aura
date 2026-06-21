# AURA Constitution
<!-- Adaptive Unified Robotic Assistant — Reachy Chief of Staff -->

## Core Principles

### I. Spec-First, Always
Every feature begins as a specification in `.specify/specs/NNN-name/spec.md`.  
No implementation task is created without a corresponding spec entry.  
No code is merged without traceability to a spec acceptance criterion.  
Specs are living artifacts — update them when reality diverges.

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

---

## Governance

This constitution supersedes all other practices and README instructions.  
Amendments require: documented rationale, update to affected ADR(s), migration plan for existing code.  
All PRs must verify compliance with the Hardware Abstraction and Safety Gates principles.  
Complexity violations must be justified in `.specify/specs/NNN/plan.md` under the **Complexity Tracking** section.

**Version**: 1.0.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-04-25
