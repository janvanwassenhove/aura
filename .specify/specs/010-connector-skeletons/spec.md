---
feature: "010-connector-skeletons"
status: "in-progress"
owner: "connector-service"
priority: P2
risk: Medium
created: "2026-04-25"
---

# Feature Specification: Connector Skeletons (Work IQ MCP + Mock)

**Feature Branch**: `010-connector-skeletons`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: connector-service
**Priority**: P2
**Risk**: Medium

## User Scenarios & Testing

### User Story 1 — Mock Connectors Work Without M365 Credentials (Priority: P2)

When `M365_CONNECTOR=mock`, all M365 tool calls return realistic fake data, enabling full development and testing without an M365 license.

**Why this priority**: Unblocks all orchestrator and conversation testing without real credentials. Without this, no M365-related feature can be tested in CI.

**Independent Test**: Set `M365_CONNECTOR=mock`; call `GET /calendar/events/today`; assert a list of fake calendar events is returned with correct schema.

**Acceptance Scenarios**:

1. **Given** `M365_CONNECTOR=mock`, **When** `list_calendar_events_today()` is called, **Then** a list of 2-3 fake events is returned with correct `CalendarEvent` schema.
2. **Given** `M365_CONNECTOR=mock`, **When** `get_unread_mail()` is called, **Then** a list of fake mail items is returned.
3. **Given** `M365_CONNECTOR=mock`, **When** `post_teams_message(channel, text)` is called, **Then** the call succeeds and the message is logged (not actually sent).
4. **Given** `M365_CONNECTOR=mock`, **When** `list_tasks()` is called, **Then** a list of fake Planner tasks is returned.
5. **Given** `M365_CONNECTOR=mock`, **When** `send_mail(to, subject, body)` is called, **Then** the call succeeds and the mail is logged (not actually sent).

---

### User Story 2 — Work IQ MCP Connector Authenticates via MSAL OBO (Priority: P2)

When `M365_CONNECTOR=workiq`, the connector authenticates using MSAL OBO flow and calls the real Work IQ MCP servers.

**Why this priority**: Required for production use. Medium risk due to MSAL OBO complexity and external service dependency.

**Independent Test**: With valid Entra credentials, call `list_calendar_events_today()` via Work IQ MCP; assert a `CalendarEvent` list is returned.

**Acceptance Scenarios**:

1. **Given** valid `A365_CLIENT_ID`, `A365_CLIENT_SECRET`, `A365_TENANT_ID` env vars, **When** the connector initializes, **Then** MSAL `ConfidentialClientApplication` is created successfully.
2. **Given** an authenticated connector, **When** `list_calendar_events_today()` is called, **Then** the request uses the OBO token and the response matches the `CalendarEvent` schema.
3. **Given** a token expiry, **When** the next tool call is made, **Then** MSAL automatically refreshes the token without user intervention.
4. **Given** auth failure (wrong credentials), **When** any tool call is made, **Then** a clear `ConnectorAuthError` is raised (no token logged).

---

### User Story 3 — Connector ABC Defines the Tool Interface (Priority: P2)

`WorkIQConnector` and `MockM365Connector` both implement `M365Connector` ABC, so the orchestrator can switch between them via env var.

**Independent Test**: Run `M365Connector` contract tests against both `MockM365Connector` and `WorkIQConnector` (mocked MSAL); both pass.

**Acceptance Scenarios**:

1. **Given** `M365Connector` contract tests, **When** run against `MockM365Connector`, **Then** all tests pass.
2. **Given** `M365Connector` contract tests, **When** run against `WorkIQConnector` with mocked MSAL, **Then** all tests pass.
3. **Given** `M365_CONNECTOR=workiq`, **When** the connector factory is called, **Then** `WorkIQConnector` is returned.
4. **Given** `M365_CONNECTOR=mock`, **When** the connector factory is called, **Then** `MockM365Connector` is returned.

---

### User Story 4 — Auth Tokens are Never Logged (Priority: P2)

No auth token, client secret, or personal M365 content appears in any log output.

**Why this priority**: Hard security requirement from the constitution. Must be verified explicitly.

**Independent Test**: Enable DEBUG logging; make a successful tool call; assert no bearer token or secret appears in log output.

**Acceptance Scenarios**:

1. **Given** DEBUG logging is enabled, **When** any connector method is called, **Then** log output contains method name and status but NOT the bearer token.
2. **Given** a mail is retrieved, **When** the result is logged, **Then** only metadata (subject length, count) is logged; no mail body content appears.
3. **Given** MSAL cache, **When** the service is running, **Then** the token cache is memory-only (not written to disk).

---

### Edge Cases

- What if the Work IQ MCP server is unavailable? → `ConnectorUnavailableError` is raised; `ToolCallFailed` event is emitted; offline queue handles retry if applicable.
- What if the OBO token does not have the required scope? → Clear `ConnectorPermissionError` is raised with the missing scope name.
- What if `M365_CONNECTOR` env var is unrecognized? → Service fails to start with a descriptive error listing valid values.

---

## Requirements

### Functional Requirements

- **FR-001**: `M365Connector` ABC MUST define: `list_calendar_events_today()`, `get_unread_mail()`, `post_teams_message()`, `send_mail()`, `list_tasks()`, `create_task()`.
- **FR-002**: `MockM365Connector` MUST implement all `M365Connector` methods with realistic fake responses.
- **FR-003**: `WorkIQConnector` MUST authenticate via MSAL `ConfidentialClientApplication.acquire_token_on_behalf_of()`.
- **FR-004**: `WorkIQConnector` MUST use `http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})` — NOT the `headers=` constructor param on `MCPStreamableHTTPTool`.
- **FR-005**: Connector selection MUST be via `M365_CONNECTOR` env var (`mock` | `workiq`).
- **FR-006**: MSAL token cache MUST be in-memory only in the current implementation.
- **FR-007**: Auth tokens MUST NOT appear in any log output at any log level.
- **FR-008**: All connector methods MUST return Pydantic response models defined in `shared-schemas`.

### Key Entities

- **M365Connector**: ABC defining the tool interface.
- **MockM365Connector**: Fake implementation for dev/CI.
- **WorkIQConnector**: Real MSAL + MCPStreamableHTTPTool implementation.
- **CalendarEvent**, **MailItem**, **Task**, **TeamsMessage**: Response Pydantic models in `shared-schemas`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: `M365Connector` contract tests pass for both implementations.
- **SC-002**: `pytest services/connector-service/tests/` passes 100% with `M365_CONNECTOR=mock`.
- **SC-003**: No bearer token or secret appears in logs at any log level (verified by test).
- **SC-004**: All mock responses match the Pydantic schemas (validated at serialization time).
- **SC-005**: Connector factory correctly selects the implementation based on `M365_CONNECTOR` env var.

---

## Assumptions

- Work IQ MCP auth uses OBO flow only (not client credentials flow).
- The `agent-framework` package providing `MCPStreamableHTTPTool` is available via pip.
- M365 Copilot license is NOT required for development when `M365_CONNECTOR=mock`.
- Initial connector surface area is limited to 6 methods; full 70-tool surface is a future spec.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle IV (Safety Gates), Principle VI (No Sensitive Data in Logs)
- [ADR-006](docs/adr/ADR-006-m365-connector.md)
- [Spec 006 — Orchestrator Foundation](../006-orchestrator-foundation/spec.md)
