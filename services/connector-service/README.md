# connector-service

**Port**: 8004  
**Spec**: [010-connector-skeletons](../../.specify/specs/010-connector-skeletons/spec.md)

## Responsibilities

- Provides the `M365Connector` ABC and all concrete connector implementations
- `MockM365Connector` — returns realistic fake M365 data (no credentials needed)
- `WorkIQConnector` — calls real Work IQ MCP servers via MSAL OBO auth
- Handles MSAL `ConfidentialClientApplication` and OBO token acquisition
- Exposes a connector REST API for the orchestrator to call
- Emits `ToolCallSucceeded` / `ToolCallFailed` events

## Key Interfaces

- `M365Connector` ABC — `list_calendar_events_today()`, `get_unread_mail()`, `post_teams_message()`, `send_mail()`, `list_tasks()`, `create_task()`
- `MockM365Connector` — fake implementation for dev/CI
- `WorkIQConnector` — MSAL + `MCPStreamableHTTPTool` implementation
- REST: `GET /calendar/today`, `GET /mail/unread`, `POST /teams/message`, `POST /mail/send`, `GET /tasks`, `POST /tasks`

## Running Locally

```bash
cd services/connector-service
cp ../../infra/dev/.env.example .env
# M365_CONNECTOR=mock by default — no credentials needed
uv run uvicorn connector_service.main:app --reload --port 8004
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `M365_CONNECTOR` | `mock` | `mock` or `workiq` |
| `A365_CLIENT_ID` | — | Required for `workiq` |
| `A365_CLIENT_SECRET` | — | Required for `workiq` |
| `A365_TENANT_ID` | — | Required for `workiq` |
| `A365_SP_ID` | `ea9ffc3e-8a23-4a7d-836d-234d7c7565c1` | Agent 365 service principal |

## Tests

```bash
M365_CONNECTOR=mock uv run pytest tests/
uv run pytest ../../tests/contract/test_m365_connector_contract.py --connector=mock
```

## CRITICAL: Auth Token Passing

`MCPStreamableHTTPTool` ignores the `headers=` constructor parameter. Auth tokens MUST use `http_client`:

```python
# ✅ CORRECT
tool = MCPStreamableHTTPTool(
    server_url=url,
    http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})
)
```

Auth tokens MUST NOT appear in any log output at any log level. See [ADR-006](../../docs/adr/ADR-006-m365-connector.md).

## Work IQ MCP Servers

| Server | URL |
|--------|-----|
| Teams | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_TeamsServer` |
| Mail | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_MailTools` |
| Calendar | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_CalendarTools` |
| Planner | `https://agent365.svc.cloud.microsoft/agents/servers/mcp_PlannerServer` |
