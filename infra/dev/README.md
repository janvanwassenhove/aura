# infra/dev

Local development infrastructure for AURA.

## Contents

- `docker-compose.yml` — 7-container stack (6 Python services + Vue dev server)
- `.env.example` — all environment variable documentation

## Quick Start

```bash
# Copy example env file
cp .env.example .env

# Build and start all containers
docker compose up --build

# Start with live reload (recommended for development)
docker compose up
```

## Container Map

| Container | Port | Service |
|-----------|------|---------|
| `robot-runtime` | 8001 | RobotAdapter, BehaviorEngine, FakeRobot |
| `conversation-runtime` | 8002 | STT/TTS, LLM turns, session management |
| `orchestrator` | 8003 | Intent routing, approval, persona |
| `connector-service` | 8004 | Mock/Work IQ M365 connector |
| `memory-service` | 8005 | SQLite sessions, todos, reminders |
| `identity-service` | 8006 | Persona, mode, auth (skeleton) |
| `operator-console` | 5173 | Vue 3 dev server |

## Health Checks

```bash
for port in 8001 8002 8003 8004 8005 8006; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | python -m json.tool
done
```

## Resetting Local Data

```bash
docker compose down -v   # removes SQLite volume
```

## Running Individual Services

```bash
docker compose up robot-runtime orchestrator
```
