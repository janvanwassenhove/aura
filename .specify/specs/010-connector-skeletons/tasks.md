# Tasks: Connector Skeletons (Spec 010)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: All tasks completed (retroactively documented 2026-05-01)

---

## Task List

### Phase 1 — Pydantic Schemas

- [x] **T-001** Add `m365.py` to `packages/shared-schemas/` with `CalendarEvent`, `MailItem`, `Task`, `TeamsMessage` models
- [x] **T-002** Export new models from `shared_schemas/__init__.py`

### Phase 2 — M365Connector ABC

- [x] **T-003** Create `base.py` with `M365Connector` ABC and all 6 abstract methods with full type signatures
- [x] **T-004** Add docstrings for each method specifying expected return schema

### Phase 3 — MockM365Connector

- [x] **T-005** Implement `MockM365Connector.list_calendar_events_today()` — return 2 fake `CalendarEvent` objects
- [x] **T-006** Implement `MockM365Connector.get_unread_mail()` — return 3 fake `MailItem` objects
- [x] **T-007** Implement `MockM365Connector.post_teams_message()` — log metadata only, return None
- [x] **T-008** Implement `MockM365Connector.send_mail()` — log metadata only, return None
- [x] **T-009** Implement `MockM365Connector.list_tasks()` — return 3 fake `Task` objects
- [x] **T-010** Implement `MockM365Connector.create_task()` — return new fake `Task`, log title only (not full content)
- [x] **T-011** Validate all mock responses with `model_validate()` at return time

### Phase 4 — WorkIQConnector

- [x] **T-012** Implement `WorkIQConnector.__init__()` — `msal.ConfidentialClientApplication` creation; log `client_id` only (not secret)
- [x] **T-013** Implement `_get_token()` — OBO acquisition; log `token_acquired=True/False`; never log token value
- [x] **T-014** Implement all 6 connector methods using acquired token in `httpx.AsyncClient` headers
- [x] **T-015** Map MSAL exceptions to `ConnectorAuthError` / `ConnectorPermissionError`; no token in exception message
- [x] **T-016** Implement token refresh: call `_get_token()` fresh on each request (MSAL handles caching)

### Phase 5 — Factory & Routes

- [x] **T-017** Implement `factory.py` — read `M365_CONNECTOR` env var; raise `ValueError` for unknown values
- [x] **T-018** Implement `routes.py` — FastAPI routes for each connector method; `GET /connector/health`, tool endpoints
- [x] **T-019** Wire factory in `main.py` lifespan; inject connector into router via dependency

### Phase 6 — Unit Tests

- [x] **T-020** `test_mock_connector.py` — all 6 methods return valid schemas; no personal data in logs
- [x] **T-021** `test_workiq_connector.py` — MSAL init (mocked), token acquisition (mocked), no token in log output
- [x] **T-022** `test_routes.py` — 200 responses for all endpoints with mock connector injected
- [x] **T-023** Contract test: run same test suite against both Mock and WorkIQ (mocked MSAL)

### Phase 7 — Acceptance Criteria Verification

- [x] **T-024** SC-001: Contract tests pass for both implementations — verified
- [x] **T-025** SC-002: `pytest services/connector-service/tests/` passes 100% with `M365_CONNECTOR=mock`
- [x] **T-026** SC-003: No bearer token in logs — verified with captured log output test
- [x] **T-027** SC-004: All mock responses match Pydantic schemas — validated by `model_validate()` at return
- [x] **T-028** SC-005: Factory correctly selects implementation from env var — unit test confirmed

---

## Notes

- `WorkIQConnector` dev mode uses `acquire_token_for_client()` (client credentials) instead of true OBO when no user assertion is available. This is documented in `workiq.py`. Full OBO will require a real user token from the identity-service in a future spec.
- The full Work IQ MCP tool surface (70+ tools) is out of scope; only the 6 MVP tools are implemented.
- MSAL token cache is in-memory per-process; no `SerializableTokenCache` is wired up.
