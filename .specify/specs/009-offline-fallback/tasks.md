# Tasks: Offline Fallback and Resilience (Spec 009)

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Status**: All tasks completed (retroactively documented 2026-05-01)

---

## Task List

### Phase 1 — HeartbeatMonitor

- [x] **T-001** Define `RobotMode` enum (`ONLINE`, `DEGRADED`, `OFFLINE`, `RECOVERING`, `MAINTENANCE`) in `shared-schemas` or `heartbeat.py`
- [x] **T-002** Implement `HeartbeatMonitor` class with `run()` async loop (30s interval, configurable)
- [x] **T-003** Implement per-service failure counter; emit `BackendHeartbeatOk` / `BackendHeartbeatFailed` per cycle
- [x] **T-004** Implement `ONLINE → DEGRADED` transition after 3 consecutive failures; emit `RobotModeChanged`
- [x] **T-005** Implement `DEGRADED → RECOVERING` transition when all services respond healthy; emit `RobotModeChanged`
- [x] **T-006** Implement `RECOVERING → ONLINE` transition after 30-second stability window; emit `RobotModeChanged`
- [x] **T-007** Implement `DEGRADED → MAINTENANCE` after 24h degraded; emit `RobotModeChanged`
- [x] **T-008** Start `HeartbeatMonitor` as asyncio background task in orchestrator `main.py` lifespan

### Phase 2 — FallbackAgent

- [x] **T-009** Implement `FallbackAgent.handle(text)` with regex pattern matchers
- [x] **T-010** Pattern: current time → `datetime.now()` formatted string
- [x] **T-011** Pattern: reminder → write to memory-service (best effort) + confirm
- [x] **T-012** Pattern: timer → local asyncio timer (best effort)
- [x] **T-013** Pattern: status query → current mode + uptime
- [x] **T-014** Default: canned "limited capability" message for unmatched queries

### Phase 3 — Pipeline Integration

- [x] **T-015** Modify `Pipeline.orchestrate()` to check `self._heartbeat.mode` before LLM call
- [x] **T-016** Route DEGRADED / OFFLINE / RECOVERING / MAINTENANCE turns to `FallbackAgent`

### Phase 4 — OfflineQueue

- [x] **T-017** Create `offline_queue` SQLite table (`id`, `action_name`, `arguments_json`, `enqueued_at`, `sensitive`)
- [x] **T-018** Implement `OfflineQueue.enqueue(action_name, arguments)` — pre-compute `sensitive` flag from `APPROVAL_REQUIRED`
- [x] **T-019** Implement queue capacity check (reject at 50 items with "queue full" response)
- [x] **T-020** Implement `OfflineQueue.drain()` — emit `OfflineQueueSyncStarted`, process items in order
- [x] **T-021** Drainer: sensitive items → emit `ApprovalRequested`, await approval (timeout → skip, emit `ToolCallFailed`)
- [x] **T-022** Drainer: read-only items → execute directly via connector
- [x] **T-023** Drainer: emit `OfflineQueueSyncCompleted` when done
- [x] **T-024** Trigger drain on `RECOVERING → ONLINE` transition in `HeartbeatMonitor`

### Phase 5 — Unit Tests

- [x] **T-025** `test_heartbeat.py` — failure counting, ONLINE→DEGRADED, DEGRADED→RECOVERING, RECOVERING→ONLINE (30s window), MAINTENANCE after 24h
- [x] **T-026** `test_fallback_agent.py` — all 4 patterns, unmatched → canned message
- [x] **T-027** `test_offline_queue.py` — enqueue, drain sensitive (approval required), drain read-only (auto), queue cap at 50, persist across restart

### Phase 6 — Acceptance Criteria Verification

- [x] **T-028** SC-001: ONLINE→DEGRADED within 5s of 3rd missed heartbeat — verified with mock services
- [x] **T-029** SC-002: Sensitive queued actions require fresh approval on reconnect — verified in test
- [x] **T-030** SC-003: FallbackAgent handles all 4 offline commands — tests passing
- [x] **T-031** SC-004: Queue survives restart (SQLite persistence) — verified in test
- [x] **T-032** SC-005: RECOVERING→ONLINE only after 30s stability window — verified in test

---

## Notes

- OfflineQueue drain currently does not implement automatic retry for failed tool calls; retries are a future enhancement.
- The 24h MAINTENANCE transition threshold is configurable via `HEARTBEAT_MAINTENANCE_HOURS` env var (default: 24).
- FallbackAgent reminder creation falls back to a local in-memory dict if memory-service is unreachable (since we're offline).
