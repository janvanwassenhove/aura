# AURA — Adaptive Unified Robotic Assistant

A modular embodied AI assistant platform for Reachy Mini. AURA combines a pluggable voice pipeline, Microsoft 365 integration, and coordinated robot motion through a spec-driven, event-based architecture.

## Quick Start

```bash
# Copy environment variables (uses FakeRobot + mock M365 connectors by default)
cp infra/dev/.env.example infra/dev/.env

# Start all services
docker compose -f infra/dev/docker-compose.yml up --build

# Send a test text turn
curl -X POST http://localhost:8003/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello AURA, what meetings do I have today?"}'
```

Open the operator console at `http://localhost:5173`.

## Architecture

See [docs/architecture/overview.md](docs/architecture/overview.md) for a full system diagram and data flow walkthrough.

```
services/
├── robot-runtime/       # RobotAdapter, BehaviorEngine, FakeRobot (port 8001)
├── conversation-runtime/ # STT/TTS, session management, LLM turns (port 8002)
├── orchestrator/        # Intent routing, approval gate, persona (port 8003)
├── connector-service/   # Work IQ MCP / Mock M365 connectors (port 8004)
├── memory-service/      # Sessions, todos, reminders (port 8005)
└── identity-service/    # Auth, persona, mode (port 8006)

packages/
├── shared-schemas/      # Pydantic event models and ABCs
├── shared-events/       # AsyncEventBus and WebSocketBroadcaster
├── shared-policies/     # Approval rules and mode access control
├── shared-personas/     # Persona definitions and system prompts
└── shared-prompts/      # LLM prompt templates

apps/
└── operator-console/    # Vue 3 + TypeScript monitoring console

infra/
└── dev/                 # Docker Compose, .env.example

tests/
├── contract/            # RobotAdapter, M365Connector, MemoryStore contracts
├── integration/         # Full-stack text turn and approval gate tests
├── unit/                # Per-service unit tests
└── simulation/          # FakeRobot scenario tests
```

## Development Principles

This project follows a **Spec-First** workflow. See [AGENTS.md](AGENTS.md) for GitHub Copilot integration and the `.specify/` folder for all feature specifications.

The governing principles are in [.specify/memory/constitution.md](.specify/memory/constitution.md). Read it before making any architectural changes.

**Key rules:**
- FakeRobot is the primary development target — everything works without hardware
- No Reachy SDK imports outside `services/robot-runtime/`
- `M365_CONNECTOR=mock` for dev — no M365 license required
- Sensitive actions require approval — the gate is never bypassed
- Auth tokens must never appear in logs

## Prerequisites

- Docker Desktop
- `uv` — `pip install uv` or [install guide](https://docs.astral.sh/uv/getting-started/installation/)
- Node 20+ (for operator console)
- Python 3.11+ (for running services outside Docker)

## Environment Variables

All required variables are documented in [infra/dev/.env.example](infra/dev/.env.example).

For development, defaults work out-of-the-box with no external credentials needed.

## Spec Kit Commands (GitHub Copilot)

| Command | What it does |
|---------|-------------|
| `/speckit.constitution` | Display the governing principles |
| `/speckit.specify <feature>` | Draft a spec for a new feature |
| `/speckit.plan <NNN>` | Create an implementation plan for a spec |
| `/speckit.tasks <NNN>` | Generate a task list from a plan |
| `/speckit.implement <NNN>` | Begin implementation from tasks |

## Contributing

1. Create a feature branch matching the spec folder name (`NNN-feature-name`)
2. Write the spec before any implementation
3. Run contract tests before submitting a PR: `pytest tests/contract/`
4. Ensure `grep -r "reachy" services/orchestrator/` returns no matches
5. Ensure no secrets appear in logs: `grep -r "Bearer" logs/` returns no matches
