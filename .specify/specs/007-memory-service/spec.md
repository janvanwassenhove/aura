---
feature: "007-memory-service"
status: "in-progress"
owner: "memory-service"
priority: P2
risk: Low
plan_required: false
plan_note: "P2/Low-risk feature — tasks.md provides sufficient planning detail; no separate plan.md warranted."
created: "2026-04-25"
---

# Feature Specification: Memory Service

**Feature Branch**: `007-memory-service`
**Created**: 2026-04-25
**Status**: In Progress
**Owner**: memory-service
**Priority**: P2
**Risk**: Low
**Note**: No `plan.md` — P2/Low-risk scope; `tasks.md` provides sufficient planning detail.

## User Scenarios & Testing

### User Story 1 — Session Transcript is Persisted and Retrievable (Priority: P2)

Conversation turns are saved to the memory service and retrieved by session ID so the orchestrator can include historical context.

**Why this priority**: Without persistence, every conversation starts cold. Essential for multi-turn usefulness.

**Independent Test**: Save 5 turns; call `GET /session/{id}/turns`; assert 5 items returned in order.

**Acceptance Scenarios**:

1. **Given** a completed conversation turn, **When** the memory service receives `TranscriptUpdated` event, **Then** the turn is persisted to SQLite.
2. **Given** a session ID, **When** `GET /session/{session_id}/turns` is called, **Then** all turns for that session are returned in chronological order.
3. **Given** a session older than the retention period (default: 30 days), **When** the cleanup job runs, **Then** old sessions are deleted and storage is reclaimed.

---

### User Story 2 — Todos are Managed via REST (Priority: P2)

AURA can add, list, complete, and delete todos on behalf of the user, stored locally in SQLite.

**Why this priority**: Local todos are the simplest form of personal productivity support. Low risk, high user value.

**Independent Test**: `POST /todos` creates item; `GET /todos` returns it; `PATCH /todos/{id}` marks it complete; `GET /todos?status=pending` returns 0.

**Acceptance Scenarios**:

1. **Given** a todo creation request, **When** `POST /todos` is called, **Then** the todo is persisted with a UUID, title, created_at, and status=pending.
2. **Given** pending todos, **When** `GET /todos?status=pending` is called, **Then** only pending items are returned.
3. **Given** a todo ID, **When** `PATCH /todos/{id}` with `{status: "complete"}` is called, **Then** the todo is marked complete and `ReminderTriggered` event is emitted if it had a due date.
4. **Given** a deleted todo, **When** `GET /todos/{id}` is called, **Then** 404 is returned.

---

### User Story 3 — Reminders Fire at the Correct Time (Priority: P2)

When a reminder is due, the memory service emits a `ReminderTriggered` event on the bus so AURA can announce it.

**Why this priority**: Reminders are a core personal assistant capability.

**Independent Test**: Create a reminder 5 seconds in the future; assert `ReminderTriggered` event is emitted within 1 second of the due time.

**Acceptance Scenarios**:

1. **Given** a reminder with a future `due_at`, **When** the current time passes `due_at`, **Then** `ReminderTriggered` event is emitted with the reminder content.
2. **Given** AURA is OFFLINE when a reminder fires, **When** AURA reconnects, **Then** missed reminders within the last 24 hours are announced.
3. **Given** a reminder is deleted before it fires, **When** the due time passes, **Then** no `ReminderTriggered` event is emitted.

---

### User Story 4 — MemoryStore ABC Enables Future Postgres Migration (Priority: P2)

The `MemoryStore` interface is implemented by `SQLiteMemoryStore`; a `PostgresMemoryStore` can be added without changing any service code.

**Why this priority**: Architecture quality gate — ensures we don't have to rewrite all persistence code for production.

**Independent Test**: Implement a `FakeMemoryStore`; run the `MemoryStore` contract tests against it; all pass.

**Acceptance Scenarios**:

1. **Given** `MemoryStore` contract tests, **When** run against `SQLiteMemoryStore`, **Then** all tests pass.
2. **Given** `MemoryStore` contract tests, **When** run against a `FakeMemoryStore`, **Then** all tests pass.
3. **Given** `MEMORY_STORE=sqlite` env var, **When** the service starts, **Then** SQLiteMemoryStore is instantiated.

---

### Edge Cases

- What happens when SQLite file is corrupted? → Service fails to start with a clear error; does not silently use empty store.
- What happens when a session is written concurrently from multiple async tasks? → SQLAlchemy async session handles serialization; no data loss.
- What happens when the reminder scheduler is restarted? → All pending reminders are reloaded from the database.

---

## Requirements

### Functional Requirements

- **FR-001**: Memory service MUST expose: `POST /todos`, `GET /todos`, `PATCH /todos/{id}`, `DELETE /todos/{id}`.
- **FR-002**: Memory service MUST expose: `POST /reminders`, `GET /reminders`, `DELETE /reminders/{id}`.
- **FR-003**: Memory service MUST expose: `POST /session/{id}/turns`, `GET /session/{id}/turns`.
- **FR-004**: `MemoryStore` ABC MUST define all CRUD operations for sessions, turns, todos, reminders.
- **FR-005**: `SQLiteMemoryStore` MUST implement `MemoryStore` using SQLAlchemy async with aiosqlite.
- **FR-006**: Reminder scheduler MUST be an asyncio background task checking for due reminders every 10 seconds.
- **FR-007**: `ReminderTriggered` event MUST be emitted when a reminder fires.
- **FR-008**: Session turns MUST be retrievable with a `limit` parameter (default: 100, max: 1000).

### Key Entities

- **Session**: `session_id`, `persona`, `created_at`, `updated_at`.
- **Turn**: `turn_id`, `session_id`, `role`, `text`, `timestamp`.
- **Todo**: `todo_id`, `title`, `description?`, `status`, `due_at?`, `created_at`.
- **Reminder**: `reminder_id`, `title`, `due_at`, `triggered_at?`, `created_at`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: `MemoryStore` contract tests pass for `SQLiteMemoryStore`.
- **SC-002**: `pytest services/memory-service/tests/` passes 100%.
- **SC-003**: Reminder fires within 1 second of due time in a 10-second scheduler loop.
- **SC-004**: 1000 turn writes complete in < 2 seconds (SQLite async benchmark).
- **SC-005**: `FakeMemoryStore` passes all contract tests (enables test isolation across other services).

---

## Assumptions

- SQLite is the only persistence backend needed until a production deployment spec is written.
- The memory service is not multi-user — all data belongs to one AURA instance.
- `FakeMemoryStore` is an in-memory dict implementation used for testing only.
- Encryption at rest for the SQLite database is out of scope for the initial implementation.

---

## References

- [Constitution](.specify/memory/constitution.md) — Principle VII (Simplicity Over Cleverness)
- [Spec 006 — Orchestrator Foundation](../006-orchestrator-foundation/spec.md)
