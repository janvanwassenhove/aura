# memory-service

**Port**: 8005  
**Spec**: [007-memory-service](../../.specify/specs/007-memory-service/spec.md)

## Responsibilities

- Persists conversation sessions and turns (transcript history)
- Manages todos: create, list, complete, delete
- Manages reminders: create, list, delete; fires `ReminderTriggered` events
- Provides the `MemoryStore` ABC enabling future Postgres migration
- `SQLiteMemoryStore` is the only concrete implementation

## Key Interfaces

- `MemoryStore` ABC — all CRUD operations for sessions, turns, todos, reminders
- `SQLiteMemoryStore` — aiosqlite + SQLAlchemy async
- `FakeMemoryStore` — in-memory dict implementation for testing
- Reminder scheduler — asyncio background task, fires every 10 seconds
- REST: `POST/GET /session/{id}/turns`, `POST/GET/PATCH/DELETE /todos`, `POST/GET/DELETE /reminders`

## Running Locally

```bash
cd services/memory-service
cp ../../infra/dev/.env.example .env
uv run uvicorn memory_service.main:app --reload --port 8005
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_STORE` | `sqlite` | `sqlite` (only option for now) |
| `SQLITE_PATH` | `./data/aura.db` | SQLite database file path |
| `SESSION_RETENTION_DAYS` | `30` | Session cleanup age |
| `REMINDER_CHECK_INTERVAL` | `10` | Seconds between reminder checks |

## Tests

```bash
uv run pytest tests/
uv run pytest ../../tests/contract/test_memory_store_contract.py --store=sqlite
uv run pytest ../../tests/contract/test_memory_store_contract.py --store=fake
```

## Architecture Notes

- `FakeMemoryStore` exists only for testing; never used in production
- SQLite file is stored at `./data/aura.db` (volume-mounted in Docker)
- Encryption at rest is out of scope for the initial implementation
- All reads are async; no blocking SQLite calls
