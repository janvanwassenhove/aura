# Implementation Plan: Offline Fallback and Resilience (Spec 009)

**Spec**: [spec.md](spec.md)
**Status**: Implemented (plan retroactively documented 2026-05-01)
**Risk**: High (state machine correctness, safety gate on offline queue)

---

## Technical Decisions

### TD-001 — HeartbeatMonitor as Asyncio Background Task

`HeartbeatMonitor` runs as a long-lived `asyncio.Task` started at orchestrator startup (in `main.py` `lifespan`). It pings each backend service's `/health` endpoint via `httpx.AsyncClient` every 30 seconds. Consecutive failure counts are tracked per-service in a `dict[str, int]`. The monitor emits `BackendHeartbeatOk` or `BackendHeartbeatFailed` events after each check cycle.

### TD-002 — Mode State Machine

Mode is tracked as a `RobotMode` string enum on the `HeartbeatMonitor` instance. Transitions:
- `ONLINE` → `DEGRADED` after 3 consecutive failures for any tracked service
- `DEGRADED` → `RECOVERING` once all services respond healthy
- `RECOVERING` → `ONLINE` after a 30-second stability window with no failures
- Any mode → `MAINTENANCE` if `DEGRADED` persists for 24 hours (configurable)

Each transition emits `RobotModeChanged`. The orchestrator `Pipeline` reads `heartbeat.mode` before every turn to decide whether to use `FallbackAgent`.

### TD-003 — FallbackAgent via Pattern Matching

`FallbackAgent` uses `re.search` keyword matching (case-insensitive). Supported patterns:
- Time: `/what.*time|current time/i` → `datetime.now().strftime(...)`
- Reminder: `/remind|reminder/i` → writes to memory-service if reachable, else local dict
- Timer: `/timer|set.*timer/i` → local asyncio timer (best effort)
- Status: `/status|how are you|online/i` → mode string + uptime

Unmatched queries return a canned "limited capability" message.

### TD-004 — OfflineQueue with SQLite Persistence

`OfflineQueue` uses the existing `memory-service` SQLite connection via a shared `aiosqlite` instance. Queue items are rows in an `offline_queue` table: `(id, action_name, arguments_json, enqueued_at, sensitive)`. The `sensitive` flag is pre-computed from `shared-policies.APPROVAL_REQUIRED` at enqueue time.

On reconnect (mode: `RECOVERING` → `ONLINE`), the queue drainer:
1. Fetches all pending items ordered by `enqueued_at`
2. Emits `OfflineQueueSyncStarted`
3. For each item: if `sensitive` → emit `ApprovalRequested` and await approval; if not → execute directly
4. Emits `OfflineQueueSyncCompleted` when all items are processed

### TD-005 — Orchestrator Pipeline Integration

`Pipeline.orchestrate()` checks `self._heartbeat.mode` at the top of each call:
- `DEGRADED` / `OFFLINE` / `MAINTENANCE` → delegate to `FallbackAgent`
- `RECOVERING` → also delegate to `FallbackAgent` (stability window still in progress)
- `ONLINE` → proceed with LLM call

---

## File Structure

```
services/orchestrator/src/orchestrator/
  heartbeat.py          ← HeartbeatMonitor, mode state machine, BackendHeartbeat* events
  fallback_agent.py     ← FallbackAgent, pattern matchers
  offline_queue.py      ← OfflineQueue, SQLite persistence, drainer
  pipeline.py           ← Reads heartbeat.mode to route to FallbackAgent
  main.py               ← Starts HeartbeatMonitor task in lifespan
```

---

## Test Strategy

### Unit Tests
- `tests/test_heartbeat.py` — mock httpx, verify failure counting, mode transitions, event emission
- `tests/test_fallback_agent.py` — each pattern, unmatched fallback, RECOVERING delegates to fallback
- `tests/test_offline_queue.py` — enqueue, drainer (sensitive requires approval, read-only auto-executes), queue full (50 item cap), survive restart (SQLite)

### Integration
- Full text turn while heartbeat mock returns failure → FallbackAgent responds
- Queue an action offline → restore mock health → approval emitted before execution

---

## Complexity Tracking

The 30-second stability window in RECOVERING mode was the trickiest part: it requires tracking `first_healthy_at` timestamp and comparing on each successful heartbeat. Implemented with a simple `Optional[datetime]` field on `HeartbeatMonitor`.

The offline queue drainer must handle approval timeout gracefully: if `ApprovalTimeout` is raised, the item is skipped (not retried), and `ToolCallFailed(error_code="approval_timeout")` is emitted.

---

## Files Touched

| File | Action |
|------|--------|
| `services/orchestrator/src/orchestrator/heartbeat.py` | Created |
| `services/orchestrator/src/orchestrator/fallback_agent.py` | Created |
| `services/orchestrator/src/orchestrator/offline_queue.py` | Created |
| `services/orchestrator/src/orchestrator/pipeline.py` | Modified — added heartbeat mode check |
| `services/orchestrator/src/orchestrator/main.py` | Modified — start HeartbeatMonitor in lifespan |
| `services/orchestrator/tests/test_heartbeat.py` | Created |
| `services/orchestrator/tests/test_fallback_agent.py` | Created |
| `services/orchestrator/tests/test_offline_queue.py` | Created |
