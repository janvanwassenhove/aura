# Implementation Plan: Connector Skeletons (Spec 010)

**Spec**: [spec.md](spec.md)
**Status**: Implemented (plan retroactively documented 2026-05-01)
**Risk**: Medium (MSAL OBO auth complexity; external service dependency for WorkIQ)

---

## Technical Decisions

### TD-001 — M365Connector ABC

Defined in `services/connector-service/src/connector_service/base.py`. Abstract methods:
- `list_calendar_events_today() → list[CalendarEvent]`
- `get_unread_mail() → list[MailItem]`
- `post_teams_message(channel: str, text: str) → None`
- `send_mail(to: str, subject: str, body: str) → None`
- `list_tasks() → list[Task]`
- `create_task(title: str, due_date: str | None) → Task`

All return types are Pydantic v2 models in `packages/shared-schemas/src/shared_schemas/`.

### TD-002 — MockM365Connector

Returns hardcoded realistic fake data. All fakes are `model_validate()`-validated at return time to catch schema drift. Side-effectful methods (`post_teams_message`, `send_mail`) log the action at INFO level with metadata only (no content payload in log).

### TD-003 — WorkIQConnector

Uses `msal.ConfidentialClientApplication` for OBO token acquisition. Token cached in-memory (no disk cache). The acquired bearer token is passed as `Authorization: Bearer <token>` header to the Work IQ MCP HTTP endpoints via `httpx.AsyncClient`. Token refresh is handled by MSAL automatically on expiry. No token value is ever written to logs — only `token_acquired=True` / `token_acquired=False` boolean is logged.

### TD-004 — Connector Factory

`connector_service/factory.py` reads `M365_CONNECTOR` env var:
- `mock` → `MockM365Connector()`
- `workiq` → `WorkIQConnector(client_id, client_secret, tenant_id)`
- unknown → raises `ValueError` with descriptive message listing valid values; service fails to start

### TD-005 — REST Routes

`connector_service/routes.py` exposes HTTP endpoints that the orchestrator calls to execute tool actions. Each endpoint maps 1:1 to an `M365Connector` method.

---

## Pydantic Schemas (in shared-schemas)

```python
# packages/shared-schemas/src/shared_schemas/m365.py
class CalendarEvent(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None

class MailItem(BaseModel):
    id: str
    subject: str
    from_address: str
    received_at: datetime
    is_read: bool

class Task(BaseModel):
    id: str
    title: str
    due_date: str | None = None
    completed: bool = False

class TeamsMessage(BaseModel):
    channel: str
    text: str
    sent_at: datetime
```

---

## File Structure

```
services/connector-service/src/connector_service/
  base.py             ← M365Connector ABC
  mock.py             ← MockM365Connector
  workiq.py           ← WorkIQConnector (MSAL OBO + httpx)
  factory.py          ← Connector selection from M365_CONNECTOR env var
  routes.py           ← FastAPI routes mapping to connector methods
  main.py             ← App init, factory call

packages/shared-schemas/src/shared_schemas/
  m365.py             ← CalendarEvent, MailItem, Task, TeamsMessage
```

---

## Test Strategy

### Unit Tests
- `tests/test_mock_connector.py` — all 6 methods, schema validation on all responses
- `tests/test_workiq_connector.py` — MSAL init with mock credentials, OBO token acquisition (mocked), no token in logs
- `tests/test_routes.py` — HTTP endpoints return correct status codes and response shapes

### Contract Tests
Both `MockM365Connector` and `WorkIQConnector` (with mocked MSAL) run the same parameterised contract test suite (`tests/test_contract.py`) to verify ABC compliance.

### Security Tests
- `test_no_token_in_logs.py` — capture log output with DEBUG level; assert `sk-`, `Bearer`, `secret` strings absent

---

## Complexity Tracking

MSAL OBO requires a `user_assertion` (the user's access token). In development, the orchestrator does not have a real user token. The `WorkIQConnector` in dev mode uses `acquire_token_for_client()` (client credentials grant) as a fallback when no user assertion is available. This deviation from production OBO flow is documented in `workiq.py` with a clear comment.

---

## Files Touched

| File | Action |
|------|--------|
| `services/connector-service/src/connector_service/base.py` | Created |
| `services/connector-service/src/connector_service/mock.py` | Created |
| `services/connector-service/src/connector_service/workiq.py` | Created |
| `services/connector-service/src/connector_service/factory.py` | Created |
| `services/connector-service/src/connector_service/routes.py` | Created |
| `services/connector-service/src/connector_service/main.py` | Created |
| `packages/shared-schemas/src/shared_schemas/m365.py` | Created |
| `services/connector-service/tests/test_mock_connector.py` | Created |
| `services/connector-service/tests/test_workiq_connector.py` | Created |
| `services/connector-service/tests/test_routes.py` | Created |
