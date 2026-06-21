# orchestrator

**Port**: 8003  
**Spec**: [006-orchestrator-foundation](../../.specify/specs/006-orchestrator-foundation/spec.md)

## Responsibilities

- Routes LLM intents to the correct tool via `IntentRouter`
- Enforces the approval gate for sensitive actions via `ApprovalManager`
- Manages persona system prompts and tool lists via `PersonaManager`
- Assembles LLM prompts via `ContextBuilder`
- Manages mode-based access control (work vs. home tool sets)
- Emits `ToolCallRequested`, `ToolCallSucceeded`, `ToolCallFailed`, `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied`

## Key Interfaces

- `IntentRouter` — maps intents to connector tools
- `ApprovalManager` — gates sensitive actions; auto-cancels on timeout (30s)
- `PersonaManager` — 5 personas: work, home, presentation, silent_desk, demo
- `ContextBuilder` — assembles system prompt + tool definitions + session history + memory digest
- REST: `POST /orchestrate`, `POST /approval/{id}/grant`, `POST /approval/{id}/deny`
- WebSocket: `/ws/events` — streams orchestrator events to operator console

## Running Locally

```bash
cd services/orchestrator
cp ../../infra/dev/.env.example .env
uv run uvicorn orchestrator.main:app --reload --port 8003
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for LLM calls |
| `OPENAI_MODEL` | `gpt-4o` | LLM model to use |
| `MAX_CONTEXT_TURNS` | `10` | Session turns in context |
| `APPROVAL_TIMEOUT_SECONDS` | `30` | Auto-cancel timeout |
| `ACTIVE_PERSONA` | `work` | Default persona |

## Tests

```bash
uv run pytest tests/
```

## Architecture Notes

- Orchestrator MUST NOT import Reachy SDK types or call `robot-runtime` directly
- Tool calls are delegated to `connector-service` via REST
- All state changes are communicated via events, never by polling
- Mode-based access control: work-mode tools are blocked in home mode and vice versa
