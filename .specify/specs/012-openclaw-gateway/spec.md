---
feature: "012-openclaw-gateway"
status: "in-progress"
owner: "orchestrator"
priority: P3
risk: Medium
created: "2026-04-25"
---

# Feature Specification: OpenClaw External Agent Gateway

**Feature Branch**: `012-openclaw-gateway`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: orchestrator
**Priority**: P3
**Risk**: Medium

## User Scenarios & Testing

### User Story 1 — External Agent Can Send Instructions to AURA (Priority: P3)

An external AI agent (OpenClaw or similar) can send structured commands to AURA via a gateway endpoint. Commands pass through the approval gate before execution.

**Why this priority**: Enables AURA to participate in multi-agent workflows. P3 because it requires the full orchestrator and approval gate to be in place first.

**Independent Test**: POST a `speak` command to `POST /gateway/command` with a valid API key; assert AURA speaks the text and `ToolCallSucceeded` event is emitted.

**Acceptance Scenarios**:

1. **Given** a valid gateway API key, **When** `POST /gateway/command` is called with `{action: "speak", text: "Hello"}`, **Then** AURA speaks the text.
2. **Given** a command for a sensitive action (e.g., `send_mail`), **When** received via the gateway, **Then** `ApprovalRequested` is emitted before execution.
3. **Given** an invalid API key, **When** a gateway command is received, **Then** 401 is returned and no action is taken.
4. **Given** an unsupported action type, **When** a gateway command is received, **Then** 422 is returned with a clear error.
5. **Given** a command with malformed payload, **When** Pydantic validation runs, **Then** 422 is returned with field-level details.

---

### User Story 2 — Rate Limiting Protects AURA from Command Floods (Priority: P3)

The gateway enforces rate limiting to prevent external agents from overwhelming AURA with commands.

**Independent Test**: Send 20 commands in 1 second; assert the 11th command receives a 429 response.

**Acceptance Scenarios**:

1. **Given** a rate limit of 10 commands/second, **When** 11 commands arrive in 1 second, **Then** the 11th returns 429 with `Retry-After` header.
2. **Given** a rate limit is hit, **When** 1 second passes, **Then** new commands are accepted again.
3. **Given** a burst of 3 high-priority commands, **When** burst quota allows it, **Then** all 3 are accepted.

---

### User Story 3 — Gateway Commands Are Audited (Priority: P3)

Every gateway command is logged to the audit trail with the action type, API key identifier (not the key itself), timestamp, and approval status.

**Independent Test**: Send 5 commands; query `GET /gateway/audit`; assert 5 entries with correct metadata.

**Acceptance Scenarios**:

1. **Given** a gateway command is received, **When** logged to audit, **Then** the log entry contains: action_type, key_id (not key value), timestamp, status (approved/denied/executed/failed).
2. **Given** the audit log, **When** `GET /gateway/audit?limit=20` is called, **Then** the last 20 entries are returned.
3. **Given** an audit entry for a sensitive action, **When** viewed, **Then** no payload content (mail body, message text) is stored; only action metadata.

---

### User Story 4 — AURA Can Query Back via Gateway (Priority: P3)

AURA can push status events to registered external agents via webhook callbacks.

**Independent Test**: Register a webhook; trigger a `RobotModeChanged` event; assert the webhook URL receives a POST with the event payload within 1 second.

**Acceptance Scenarios**:

1. **Given** a registered webhook URL, **When** `RobotModeChanged` event is emitted, **Then** the webhook URL receives a POST with the event JSON.
2. **Given** a webhook URL that returns 500, **When** the POST fails, **Then** the system retries 3 times with exponential backoff.
3. **Given** a webhook that fails all 3 retries, **When** all retries fail, **Then** the webhook is marked inactive and an admin alert is logged.

---

### Edge Cases

- What happens if an external agent sends a contradictory command (e.g., `speak` while AURA is already speaking)? → The command is queued; a `CommandQueued` response is returned.
- What happens if the gateway receives a command while AURA is in OFFLINE mode? → 503 is returned with `{"mode": "OFFLINE", "retry_after": 30}`.
- What happens if the API key is revoked? → 401 on next request; existing commands in flight are not affected.

---

## Requirements

### Functional Requirements

- **FR-001**: Gateway MUST expose `POST /gateway/command` accepting `{action, payload, priority?}` with API key auth.
- **FR-002**: Gateway MUST expose `GET /gateway/audit` with pagination.
- **FR-003**: Gateway MUST expose `POST /gateway/webhooks` to register a callback URL for AURA events.
- **FR-004**: All gateway commands MUST pass through `ApprovalManager` for sensitive actions.
- **FR-005**: API key validation MUST use constant-time comparison (no timing attacks).
- **FR-006**: Rate limiting MUST be 10 commands/second per API key (configurable).
- **FR-007**: Audit log MUST NOT store payload content for sensitive actions; only metadata.
- **FR-008**: Webhook delivery MUST retry up to 3 times with exponential backoff.
- **FR-009**: Gateway endpoint MUST return 503 when AURA is in OFFLINE/MAINTENANCE mode.

### Key Entities

- **GatewayCommand**: `action`, `payload`, `priority`, `api_key_id`, `received_at`.
- **AuditEntry**: `action_type`, `key_id`, `timestamp`, `status`, `mode_at_time`.
- **WebhookRegistration**: `webhook_id`, `url`, `events`, `active`, `created_at`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Unauthorized gateway requests return 401 in < 10ms.
- **SC-002**: Rate limit of 10/second enforced correctly (verified by load test).
- **SC-003**: Audit log records 100% of gateway commands.
- **SC-004**: Webhook delivery succeeds within 1 second for healthy endpoints.
- **SC-005**: No sensitive payload content appears in the audit log (verified by test).

---

## Assumptions

- API keys are pre-provisioned (no self-service key registration in this feature).
- The gateway is only accessible within the local network (not exposed to the internet without a reverse proxy).
- Webhook URLs must be HTTPS in production; HTTP allowed in dev (`GATEWAY_ALLOW_HTTP_WEBHOOKS=true`).
- The full external agent protocol (OpenClaw) is not defined here; this feature provides the transport layer.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle IV (Safety Gates are Inviolable)
- [Spec 006 — Orchestrator Foundation](../006-orchestrator-foundation/spec.md)
- [Spec 009 — Offline Fallback](../009-offline-fallback/spec.md)
