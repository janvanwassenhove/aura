---
spec: "007-memory-service"
status: in-progress
created: "2026-04-25"
---

# 007 — Memory Service: Tasks

## Task Group 1: Core Store (already implemented)

- [x] **T-007-01** `SQLiteMemoryStore.add_turn / get_turns / clear_turns` — SQLAlchemy async ✓
- [x] **T-007-02** `SQLiteMemoryStore.add_todo / get_todos / complete_todo / delete_todo` ✓
- [x] **T-007-03** `SQLiteMemoryStore.add_reminder / get_reminders / mark_reminder_fired / delete_reminder / get_due_reminders` ✓
- [x] **T-007-04** `ReminderScheduler` — polls every 10 s, emits `ReminderTriggered` events ✓

## Task Group 2: REST Routes (already implemented)

- [x] **T-007-05** `POST /memory/turns`, `GET /memory/turns/{session_id}`, `DELETE /memory/turns/{session_id}` ✓
- [x] **T-007-06** `POST /memory/todos`, `GET /memory/todos`, `POST /memory/todos/{id}/complete`, `DELETE /memory/todos/{id}` ✓
- [x] **T-007-07** `POST /memory/reminders`, `GET /memory/reminders` ✓
- [x] **T-007-08** `DELETE /memory/reminders/{reminder_id}` — exists in routes.py ✓

## Task Group 3: Tests

- [x] **T-007-09** `tests/test_store.py` — in-memory SQLite store contract tests ✓ (exists, covers turns/todos/reminders)
- [x] **T-007-10** `tests/test_routes.py` ✓ — 5 tests pass (health, turn round-trip, clear turns, todo CRUD, reminder CRUD+delete)
