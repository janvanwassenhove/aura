---
feature: "010-connector-skeletons"
status: "implemented"
owner: "connector-service"
priority: P2
risk: Medium
created: "2026-04-25"
amended: "2026-09-05"
units: [U39, U48, U52, U69, U254, U254b, U255, U295, U298]
---

# Feature Specification: Connector Skeletons (Work IQ MCP + Mock)

**Feature Branch**: `010-connector-skeletons`
**Created**: 2026-04-25
**Status**: Implemented — **see the 2026-09 amendment at the end**.
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

---

# Amendment — 2026-09-05: connections a household can make

*Retro-specified; see [015-spec-coverage](../015-spec-coverage/spec.md). The
April text is the record of the original plan and is left intact.*

## What changed in shape

The plan was a **skeleton**: a `Connector` ABC, a Work IQ MCP client, and a
mock. What was missing was everything between "the code can talk to Microsoft"
and "a family sees their calendar".

| April plan | What it is now | Why |
|---|---|---|
| Connectors built from `ENABLED_CONNECTORS` | Owner-switchable in Settings, persisted, applied without a restart | Editing an env file the desktop app generates is not a setting (U254) |
| Status: connected / not | Six states, each a **different job**: `not_enabled`, `no_credentials`, `unauthenticated`, `mock`, `ok`, `unavailable` | `unknown` is the only status that tells the owner nothing they can act on (U254) |
| A mock for development | A mock that **says** it is canned data | A green badge over invented data is the worst outcome available here (U52) |
| Microsoft only | Microsoft 365, Google, GitHub, Slack, generic MCP servers, and a calendar connected by **pasting a link** | (U255, U298) |

## Additional user stories

### User Story 4 — Every connector answers for itself (Priority: P1)

1. **Given** any connector the code can build, **When** the panel is shown,
   **Then** it appears — enabled or not — with a plain sentence for what is
   true and a plain sentence for the next step (`connector_state.describe`,
   U254).
2. **Given** a connector is switched on, **When** it is, **Then** the brain
   republishes what he may do in the same request, so his capabilities change
   without a restart (U254).
3. **Given** a live connector, **When** the tool layer builds the turn,
   **Then** `live_domains` decides which tools exist — so a connector that is
   off does not leave him promising mail he cannot read (U254).
4. **Given** the Test button, **When** it is pressed, **Then** it makes the
   cheapest **real** call that connector implements. U254b: it asked every
   connector for today's calendar, so GitHub and Slack — which do repos and
   channels — could never pass their own test.
5. **Given** a connector whose credential is only read at call time, **When**
   it constructs, **Then** that is **not** reported as connected: green has to
   be earned by a successful probe (U254b).

### User Story 5 — Connecting does not require being a developer (Priority: P1)

Reported as *"don't we have more user friendly ways to connect? this is really
dev like"*, then *"app-ids is enige manier? er niks gebruiksvriendelijker?"*.

1. **Given** any row, **When** its copy is shown, **Then** it contains no
   environment-variable names. The names still travel in `missing`, because a
   diagnostic that drops them helps nobody — it is the visible sentence that
   had to change (U295).
2. **Given** a connector needs a one-time app ID, **When** the row is shown,
   **Then** there is a field to paste it into and a clickable link to the page
   it comes from. U295: the text said "paste its id here" next to no field.
3. **Given** a calendar, **When** the owner wants one connected, **Then** they
   can paste a published `.ics` link: no app registration, no consent screen,
   no sign-in, read-only by construction (U298).
4. **Given** GitHub, **When** it is connected, **Then** a personal access token
   is enough — no OAuth app to register (U298).
5. **Given** a connector cannot do something, **When** it is asked, **Then** it
   says so plainly rather than failing deep inside a turn ("A shared calendar
   link can only read the calendar").

### User Story 6 — Tools the owner adds themselves (Priority: P2)

1. **Given** any MCP server with an HTTP endpoint, **When** it is added,
   **Then** its tools are **discovered first** and switched on afterwards —
   adding is not enabling (U255).

### User Story 7 — Music, honestly (Priority: P3)

1. **Given** Spotify or Sonos, **When** asked, **Then** playback is controlled
   for real (U39), the mock says it is a mock (U48), and "always allow" is
   remembered per action (U48).
2. **Given** lyrics, **When** they are heard, **Then** they cannot become
   conversation (U69).

## Amended functional requirements

- **FR-101**: `connector_state.describe()` answers for **every** known
  connector, enabled or not, without touching the network, with a next step
  always attached.
- **FR-102**: Visible copy contains no environment-variable names; `missing`
  carries them for diagnosis.
- **FR-103**: A mock never reports itself as connected.
- **FR-104**: A connector verified only at call time must earn `ok` with a real
  probe.
- **FR-105**: The probe is a call that connector actually implements.
- **FR-106**: `live_domains` gates which tools are offered to the model.
- **FR-107**: A calendar can be connected read-only from a published `.ics`
  link, parsed in-repo (no new dependency beyond `tzdata`, because `uv sync`
  prunes unrequested extras — four units have been lost to that).

## Traceability

| Units | What they delivered |
|---|---|
| U39, U48, U69 | Spotify and Sonos control; an honest mock and remembered approvals; the lyrics guard |
| U52 | Honest connector statuses; Chrome browser control |
| U254 | Connections that exist, can be switched on, and change what he can do |
| U254b | A Test button that asks each connector something it can answer |
| U255 | MCP servers the owner adds, discovered before being switched on |
| U295 | The Connections page stopped speaking developer — and got the field its own text promised |
| U298 | A calendar connected by a link; GitHub by a personal token |
