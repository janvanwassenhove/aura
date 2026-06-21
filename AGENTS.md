# AURA — Reachy Chief of Staff

> **Adaptive Unified Robotic Assistant** — Embodied AI assistant platform for Reachy Mini, spec-driven from day one.

---

## GitHub Copilot Agent Instructions

This project uses **Spec-Driven Development** via [GitHub Spec Kit](https://github.com/github/spec-kit).  
All feature work begins with a specification. No implementation task exists without a corresponding spec entry.

### Available Spec Kit Commands

| Command | Purpose |
|---|---|
| `/speckit.constitution` | Create or update project governing principles |
| `/speckit.specify` | Define a new feature (requirements + user stories) |
| `/speckit.plan` | Create a technical implementation plan |
| `/speckit.tasks` | Generate actionable task list from a plan |
| `/speckit.implement` | Execute tasks and build the feature |
| `/speckit.clarify` | Clarify underspecified areas before planning |
| `/speckit.analyze` | Cross-artifact consistency and coverage analysis |

### Spec Kit Structure

```
.specify/
  memory/
    constitution.md       ← Project governing principles (read first)
  specs/
    NNN-feature-name/
      spec.md             ← Feature specification (user stories, FR, AC)
      plan.md             ← Technical implementation plan
      tasks.md            ← Actionable task breakdown
  templates/
    spec-template.md
    plan-template.md
    tasks-template.md
```

### Workflow Order

1. Read `.specify/memory/constitution.md` before any implementation
2. Read the relevant `.specify/specs/NNN/spec.md` for the feature being implemented
3. Read `.specify/specs/NNN/plan.md` for technical decisions
4. Execute tasks from `.specify/specs/NNN/tasks.md` in order
5. Never implement without a spec; never skip acceptance criteria

### Copilot Workspace Rules

- **Never couple the orchestrator directly to Reachy hardware APIs** — always use `RobotAdapter`
- **FakeRobot is the primary development target** — all flows must work without physical hardware
- **Sensitive tool calls require approval** — check `packages/shared-policies` before dispatching
- **Events drive state** — all state changes must emit a typed Pydantic event on the event bus
- **No secrets in logs** — auth tokens, personal data, and M365 content must never appear in log output
- **STT/TTS is pluggable** — use `STT_PROVIDER` / `TTS_PROVIDER` env vars; never hardcode a vendor

### Project Map

| Path | What it contains |
|---|---|
| `services/robot-runtime/` | RobotAdapter, FakeRobot, BehaviorEngine, FallbackAgent |
| `services/conversation-runtime/` | Voice/text input loop, STT, TTS, transcript stream |
| `services/orchestrator/` | Intent routing, context building, approval gate, persona |
| `services/connector-service/` | Work IQ MCP + mock M365 connectors |
| `services/memory-service/` | Session, preferences, tasks, reminders (SQLite/Postgres) |
| `services/identity-service/` | User profile, persona assignment |
| `packages/shared-schemas/` | Pydantic v2 event types, RobotState, Persona, MotionCommand |
| `packages/shared-events/` | Async event bus, WebSocket broadcaster |
| `packages/shared-personas/` | Persona and mode configuration |
| `packages/shared-policies/` | Approval gates, permissions per mode |
| `packages/shared-prompts/` | Jinja2 prompt templates |
| `apps/operator-console/` | Vue 3 + TypeScript monitoring console |
| `docs/adr/` | Architecture Decision Records |
| `docs/architecture/` | System diagrams and component specs |
| `infra/dev/` | Docker Compose, dev scripts |
| `tests/` | Unit, integration, contract, simulation tests |

### Key Interfaces (always respect these contracts)

```python
# RobotAdapter ABC — services/robot-runtime/src/robot_runtime/adapters/base.py
# BehaviorEngine — services/robot-runtime/src/robot_runtime/behavior/engine.py
# Orchestrator — services/orchestrator/src/orchestrator/core/
# MemoryStore ABC — services/memory-service/src/memory_service/store/base.py
# Connector ABC — services/connector-service/src/connector_service/base.py
```
