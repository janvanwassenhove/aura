# Tasks: OpenClaw External Agent Gateway (Spec 012)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: All tasks completed (retroactively documented 2026-05-01)

---

## Task List

### Phase 1 — Pydantic Models & Schemas

- [x] **T-001** Define `GatewayCommand(BaseModel)` — `action`, `payload: dict`, `priority: int = 5`
- [x] **T-002** Define `AuditEntry(BaseModel)` — `id`, `action_type`, `key_id`, `timestamp`, `status`, `mode_at_time`
- [x] **T-003** Define `WebhookRegistration(BaseModel)` — `webhook_id`, `url`, `events: list[str]`, `active`, `created_at`

### Phase 2 — API Key Store

- [x] **T-004** Parse `GATEWAY_API_KEYS` env var (format: `key_id:key_value,...`) into a `dict[str, str]` at startup
- [x] **T-005** Implement `authenticate(token: str) → str | None` — returns `key_id` using `hmac.compare_digest()`; returns `None` if invalid

### Phase 3 — Rate Limiter

- [x] **T-006** Implement sliding-window rate limiter using `dict[str, deque[float]]` keyed by `key_id`
- [x] **T-007** Configurable limit via `GATEWAY_RATE_LIMIT` env var (default: 10)
- [x] **T-008** Return 429 with `Retry-After: 1` header when limit exceeded

### Phase 4 — Audit Log

- [x] **T-009** Create `gateway_audit` SQLite table (`id`, `action_type`, `key_id`, `timestamp`, `status`, `mode_at_time`, `payload_hash`)
- [x] **T-010** Implement `write_audit(action_type, key_id, status, mode, payload)` — hash payload with SHA-256; never store raw payload
- [x] **T-011** Implement `GET /gateway/audit` with `limit`/`offset` pagination

### Phase 5 — Command Processing

- [x] **T-012** `POST /gateway/command` — auth check (401 on fail)
- [x] **T-013** Mode check — 503 if OFFLINE/MAINTENANCE with retry_after body
- [x] **T-014** Rate limit check (429)
- [x] **T-015** Pydantic validation — 422 on fail
- [x] **T-016** Write `received` audit entry
- [x] **T-017** Route sensitive actions through `ApprovalManager`; write `approved`/`denied` audit entry
- [x] **T-018** Execute command via pipeline; write `executed`/`failed` audit entry
- [x] **T-019** Handle unknown `action` type → 422 with supported actions list

### Phase 6 — Webhook Dispatcher

- [x] **T-020** Create `webhooks` SQLite table (`webhook_id`, `url`, `events`, `active`, `created_at`)
- [x] **T-021** `POST /gateway/webhooks` — register new webhook (validate URL format; HTTPS required unless `GATEWAY_ALLOW_HTTP_WEBHOOKS=true`)
- [x] **T-022** Implement `WebhookDispatcher.dispatch(event)` — POST to all active matching webhooks
- [x] **T-023** Implement retry: 3 attempts, exponential backoff (1s, 2s, 4s)
- [x] **T-024** Mark webhook `active=False` after 3 consecutive failures; log warning
- [x] **T-025** Start `WebhookDispatcher` subscriber in orchestrator `main.py` lifespan

### Phase 7 — Unit Tests

- [x] **T-026** `test_gateway.py` — valid auth → 200; invalid auth → 401; rate limit (10 ok, 11th → 429)
- [x] **T-027** Sensitive command → `ApprovalRequested` emitted (mock assert)
- [x] **T-028** OFFLINE mode → 503 with retry_after body
- [x] **T-029** Unknown action → 422
- [x] **T-030** Audit: 5 commands → 5 entries; `payload_hash` present, no raw payload
- [x] **T-031** Webhook: healthy URL → POST within 1s (mock httpx)
- [x] **T-032** Webhook: 3 failures → marked inactive, warning logged

### Phase 8 — Acceptance Criteria Verification

- [x] **T-033** SC-001: Unauthorized request → 401 in < 10ms — timing test passes
- [x] **T-034** SC-002: Rate limit 10/second enforced — unit test confirms
- [x] **T-035** SC-003: 100% of gateway commands have audit entries — verified in test
- [x] **T-036** SC-004: Webhook delivery < 1s for healthy endpoints — mock timing verified
- [x] **T-037** SC-005: No sensitive payload in audit log — SHA-256 hash only, verified

---

## Notes

- Rate limiter is in-process only (not distributed). If orchestrator is scaled horizontally, each instance has its own limit counter. Redis-backed limiter is documented as future work.
- `payload_hash` uses SHA-256 of `json.dumps(payload, sort_keys=True)` for determinism.
- Webhook URL validation: must be parseable by `urllib.parse.urlparse` with `http` or `https` scheme; `localhost` / `127.0.0.1` targets are allowed in dev only.
- The `GATEWAY_API_KEYS` env var accepts an empty string (no keys configured) — in this state, all gateway requests return 403 with a "gateway not configured" message.
