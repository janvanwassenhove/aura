# Implementation Plan: OpenClaw External Agent Gateway (Spec 012)

**Spec**: [spec.md](spec.md)
**Status**: Implemented (plan retroactively documented 2026-05-01)
**Risk**: Medium (API key auth, rate limiting, audit log correctness, webhook delivery)

---

## Technical Decisions

### TD-001 — Gateway in Orchestrator

The gateway lives in `services/orchestrator/src/orchestrator/gateway.py` and `webhook_dispatcher.py`. Routing it through the orchestrator ensures all incoming commands automatically pass through the existing `ApprovalManager` and mode-aware `Pipeline`.

### TD-002 — API Key Authentication

API keys are pre-provisioned via the `GATEWAY_API_KEYS` env var (comma-separated `key_id:key_value` pairs). On each request, the `Authorization: Bearer <token>` header is extracted and compared using `hmac.compare_digest()` (constant-time) against the stored key values. The `key_id` (not the key value) is extracted for audit logging.

No self-service key registration in this feature. Keys are rotated by updating the env var and restarting the orchestrator.

### TD-003 — Rate Limiting

Implemented as an in-process sliding-window counter (`dict[str, deque[float]]`) keyed by `api_key_id`. The deque stores timestamps of the last N requests; old entries beyond the 1-second window are pruned on each request. Limit is configurable via `GATEWAY_RATE_LIMIT` env var (default: 10/second). Returns `429 Too Many Requests` with `Retry-After: 1` header when limit is exceeded.

This is per-process only — not distributed. A Redis-backed limiter is documented as a future upgrade path in ADR.

### TD-004 — Audit Log (SQLite)

Audit entries are written to a `gateway_audit` SQLite table (same DB as memory-service, accessed via `aiosqlite`):
- `id`, `action_type`, `key_id`, `timestamp`, `status` (`received` / `approved` / `denied` / `executed` / `failed`)
- `mode_at_time` (ONLINE / DEGRADED / etc.)
- **No payload content** — `payload_hash` (SHA-256 of payload) is stored for integrity without exposing content

`GET /gateway/audit?limit=20&offset=0` returns audit entries with pagination.

### TD-005 — Command Processing Flow

`POST /gateway/command`:
1. Auth check (401 if invalid)
2. Mode check (503 if OFFLINE / MAINTENANCE)
3. Rate limit check (429 if exceeded)
4. Pydantic validation of `GatewayCommand` (422 if invalid)
5. Write `received` audit entry
6. If action is in `APPROVAL_REQUIRED` → emit `ApprovalRequested`, await approval
7. Execute via orchestrator pipeline
8. Write `executed` / `failed` audit entry

### TD-006 — Webhook Dispatcher

`webhook_dispatcher.py` maintains a list of registered webhooks (`WebhookRegistration`). On each bus event, if the event type matches a webhook's `events` list, the dispatcher POSTs the event JSON to the webhook URL via `httpx.AsyncClient`. Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s). After 3 failures, the webhook is marked `active=False` and an admin warning is logged.

Webhook registrations are stored in SQLite for persistence.

### TD-007 — OFFLINE Mode Guard

When `HeartbeatMonitor.mode` is `OFFLINE` or `MAINTENANCE`, the gateway returns `503 Service Unavailable` with `{"mode": "OFFLINE", "retry_after": 30}`. Commands queued at the gateway level are not supported (differs from offline queue which is for assistant-initiated actions).

---

## File Structure

```
services/orchestrator/src/orchestrator/
  gateway.py              ← GatewayRouter, auth, rate limiting, command processing, audit
  webhook_dispatcher.py   ← WebhookDispatcher, retry logic, activation/deactivation

services/orchestrator/tests/
  test_gateway.py
```

---

## Test Strategy

### Unit Tests (`test_gateway.py`)
- Valid API key → 200 (speak command)
- Invalid API key → 401, no action taken
- Rate limit: 10 requests succeed, 11th → 429 with `Retry-After` header
- Sensitive command → `ApprovalRequested` emitted before execution
- OFFLINE mode → 503 with retry_after
- Unknown action → 422
- Malformed payload → 422 with field errors
- Audit log: 5 commands → 5 entries; no payload content in entries
- Webhook delivery: healthy URL receives POST within 1s
- Webhook retry: URL returns 500 → 3 retries → marked inactive
- Constant-time API key comparison (not timing-testable in unit tests; documented)

---

## Complexity Tracking

The audit log `payload_hash` approach was chosen over storing no payload at all to enable forensic analysis without exposing content. SHA-256 is deterministic and content-agnostic. This was a non-obvious design decision documented here.

The rate limiter deque approach is O(n) per request where n is the rate limit — acceptable at 10/s limits. A ring buffer would be O(1) but adds complexity not justified at this scale.

---

## Files Touched

| File | Action |
|------|--------|
| `services/orchestrator/src/orchestrator/gateway.py` | Created |
| `services/orchestrator/src/orchestrator/webhook_dispatcher.py` | Created |
| `services/orchestrator/src/orchestrator/routes.py` | Modified — added `/gateway/*` routes |
| `services/orchestrator/src/orchestrator/main.py` | Modified — start WebhookDispatcher in lifespan |
| `services/orchestrator/tests/test_gateway.py` | Created |
