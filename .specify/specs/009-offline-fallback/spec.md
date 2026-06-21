---
feature: "009-offline-fallback"
status: "in-progress"
owner: "orchestrator"
priority: P2
risk: High
created: "2026-04-25"
---

# Feature Specification: Offline Fallback and Resilience

**Feature Branch**: `009-offline-fallback`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: orchestrator
**Priority**: P2
**Risk**: High

## User Scenarios & Testing

### User Story 1 — AURA Detects Network Loss and Enters DEGRADED Mode (Priority: P2)

When the backend services (LLM, Work IQ MCP) are unreachable, AURA transitions to DEGRADED mode and informs the user.

**Why this priority**: A robot that silently fails is worse than one that clearly communicates its limitations. DEGRADED mode preserves trust.

**Independent Test**: Stop the LLM mock; send a turn; assert `RobotModeChanged(mode=DEGRADED)` event is emitted within 5 seconds.

**Acceptance Scenarios**:

1. **Given** the heartbeat monitor detects 3 consecutive missed heartbeats, **When** the threshold is reached, **Then** `RobotModeChanged(mode=DEGRADED)` is emitted.
2. **Given** AURA is in DEGRADED mode, **When** the user asks a question, **Then** AURA responds with a local fallback message explaining limited capability.
3. **Given** AURA is in DEGRADED mode, **When** the user asks for a reminder, **Then** AURA accepts it (local-only operation) and confirms.
4. **Given** AURA is in DEGRADED mode, **When** connectivity is restored, **Then** AURA transitions to RECOVERING mode, runs self-check, and returns to ONLINE.

---

### User Story 2 — Sensitive Actions Are Not Auto-Executed from the Offline Queue (Priority: P2)

Actions queued while offline (e.g., "send a Teams message when you're back online") do NOT execute automatically on reconnect. They require fresh approval.

**Why this priority**: This is a hard safety requirement from the constitution. Auto-execution of queued sensitive actions must never happen.

**Independent Test**: Queue a `send_teams_message` action while offline; restore connectivity; assert `ApprovalRequested` event is emitted BEFORE the action executes.

**Acceptance Scenarios**:

1. **Given** an offline-queued `send_teams_message`, **When** AURA reconnects, **Then** `ApprovalRequested` is emitted for the queued action.
2. **Given** an offline-queued `list_calendar_events` (read-only), **When** AURA reconnects, **Then** the action executes automatically (no approval needed for reads).
3. **Given** the user cancels an offline-queued sensitive action, **When** the cancellation is confirmed, **Then** the action is removed from the queue.
4. **Given** multiple queued sensitive actions, **When** AURA reconnects, **Then** each action triggers a separate `ApprovalRequested` event in queue order.

---

### User Story 3 — FallbackAgent Handles Basic Commands Offline (Priority: P2)

When the LLM is unavailable, a local `FallbackAgent` handles a predefined set of commands using pattern matching.

**Why this priority**: Enables basic utility (reminders, time, weather) without cloud access.

**Independent Test**: Set LLM to unavailable; ask "What time is it?"; assert FallbackAgent responds with local time.

**Acceptance Scenarios**:

1. **Given** LLM is unavailable, **When** user asks "What time is it?", **Then** FallbackAgent responds with the current local time.
2. **Given** LLM is unavailable, **When** user says "Remind me to call Alice at 3pm", **Then** FallbackAgent creates the reminder locally.
3. **Given** LLM is unavailable, **When** user asks "What meetings do I have?", **Then** FallbackAgent explains it cannot retrieve calendar data offline.
4. **Given** LLM is restored, **When** AURA transitions to ONLINE, **Then** all subsequent requests use the LLM again (FallbackAgent is bypassed).

---

### User Story 4 — Heartbeat Monitoring Tracks Service Health (Priority: P2)

The heartbeat monitor checks all backend services every 30 seconds and emits health events.

**Independent Test**: Mock all services healthy; assert `BackendHeartbeatOk` is emitted every 30 seconds.

**Acceptance Scenarios**:

1. **Given** all services are healthy, **When** the heartbeat runs, **Then** `BackendHeartbeatOk` is emitted.
2. **Given** one service (e.g., connector-service) is unhealthy, **When** the heartbeat runs, **Then** `BackendHeartbeatFailed(service="connector-service")` is emitted.
3. **Given** 3 consecutive heartbeat failures for a service, **When** the threshold is exceeded, **Then** the service is marked DEGRADED and AURA is notified.

---

### Edge Cases

- What happens if AURA is in DEGRADED mode for more than 24 hours? → AURA emits a maintenance alert and transitions to MAINTENANCE mode.
- What happens if the offline queue grows beyond 50 items? → New items are rejected with a "queue full" response; oldest non-critical items may be pruned.
- What happens if connectivity is intermittent (on/off repeatedly)? → RECOVERING mode enforces a minimum 30-second stability window before returning to ONLINE.

---

## Requirements

### Functional Requirements

- **FR-001**: `HeartbeatMonitor` MUST ping all backend services every 30 seconds and emit `BackendHeartbeatOk` or `BackendHeartbeatFailed`.
- **FR-002**: After 3 consecutive failures, `HeartbeatMonitor` MUST emit `RobotModeChanged(mode=DEGRADED)`.
- **FR-003**: `OfflineQueue` MUST store pending actions persistently (SQLite) so they survive restarts.
- **FR-004**: On reconnect, `OfflineQueue` MUST emit `OfflineQueueSyncStarted` and then process each item.
- **FR-005**: Sensitive actions (in `APPROVAL_REQUIRED` policy) MUST emit `ApprovalRequested` before executing from the queue.
- **FR-006**: Read-only actions MUST execute automatically from the queue on reconnect (no approval needed).
- **FR-007**: `FallbackAgent` MUST handle: current time, set reminder, set timer, status query.
- **FR-008**: Mode transitions MUST follow the defined state machine: ONLINE → DEGRADED → RECOVERING → ONLINE.
- **FR-009**: RECOVERING mode MUST enforce a 30-second stability window before returning to ONLINE.

### Key Entities

- **HeartbeatMonitor**: Asyncio background task pinging services.
- **OfflineQueue**: Persistent SQLite queue of pending actions.
- **FallbackAgent**: Pattern-matching command handler for offline mode.
- **RobotMode**: ONLINE, DEGRADED, OFFLINE, RECOVERING, MAINTENANCE.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Mode transition ONLINE → DEGRADED occurs within 5 seconds of 3rd missed heartbeat.
- **SC-002**: 100% of sensitive queued actions require fresh approval on reconnect (no bypasses).
- **SC-003**: FallbackAgent handles all 4 offline commands in tests.
- **SC-004**: Offline queue survives service restart (data persisted in SQLite).
- **SC-005**: RECOVERING → ONLINE transition only occurs after 30-second stability window.

---

## Assumptions

- Heartbeat check uses simple HTTP GET to `/health` endpoint of each service.
- Offline queue is per-AURA-instance (single user); no cross-instance sync.
- "Sensitive" is defined by `shared-policies.APPROVAL_REQUIRED`; this list is static for this feature.
- FallbackAgent uses regex/keyword matching, not ML.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle IV (Safety Gates are Inviolable)
- [ADR-004](docs/adr/ADR-004-offline-fallback.md)
- [Spec 003 — Event Bus](../003-event-bus-schemas/spec.md)
- [Spec 006 — Orchestrator](../006-orchestrator-foundation/spec.md)
