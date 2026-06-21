# identity-service

**Port**: 8006  
**Spec**: (Pending — identity feature not yet specified)

## Responsibilities (Planned)

- User identity and authentication for the operator console
- Persona persistence (active persona, mode overrides)
- Mode switching (work → home → presentation → silent_desk → demo)
- API key management for the OpenClaw gateway
- Session-scoped permission context

## Current Status

**Skeleton only.** This service exposes a `/health` endpoint and returns stubbed responses for all other routes. Full implementation is deferred until the identity feature spec is written.

The orchestrator uses `ACTIVE_PERSONA` env var directly until this service is implemented.

## Running Locally

```bash
cd services/identity-service
cp ../../infra/dev/.env.example .env
uv run uvicorn identity_service.main:app --reload --port 8006
```

## Temporary REST Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /health` | `{"status": "ok"}` |
| `GET /identity/persona` | `{"persona": os.getenv("ACTIVE_PERSONA", "work")}` |
| `POST /identity/mode` | `{"status": "accepted"}` (no-op) |

## Tests

```bash
uv run pytest tests/
```
