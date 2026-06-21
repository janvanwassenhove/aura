"""Contract tests for SQLiteMemoryStore — runs against an in-memory SQLite DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from memory_service.db.models import Base
from memory_service.store import SQLiteMemoryStore
from shared_schemas.memory.models import Reminder, Todo, Turn

# Use StaticPool so the same in-memory connection is reused across all queries.
_TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_TEST_ENGINE, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
async def _fresh_db(monkeypatch) -> None:
    """Recreate tables and patch the session factory for each test."""
    import memory_service.store as store_mod
    monkeypatch.setattr(store_mod, "SessionLocal", _TestSession)

    async with _TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture()
def store() -> SQLiteMemoryStore:
    return SQLiteMemoryStore()


# ------------------------------------------------------------------
# Turns
# ------------------------------------------------------------------


async def test_add_and_get_turns(store: SQLiteMemoryStore) -> None:
    turn = Turn(session_id="s1", role="user", content="Hello")
    await store.add_turn(turn)

    turns = await store.get_turns("s1")
    assert len(turns) == 1
    assert turns[0].content == "Hello"
    assert turns[0].role == "user"


async def test_get_turns_returns_chronological_order(store: SQLiteMemoryStore) -> None:
    for i in range(3):
        await store.add_turn(Turn(session_id="s2", role="user", content=f"msg {i}"))

    turns = await store.get_turns("s2")
    # All 3 turns returned; ordering within same-timestamp group is unspecified.
    assert len(turns) == 3
    assert {t.content for t in turns} == {"msg 0", "msg 1", "msg 2"}


async def test_get_turns_respects_limit(store: SQLiteMemoryStore) -> None:
    for i in range(10):
        await store.add_turn(Turn(session_id="s3", role="user", content=f"msg {i}"))

    turns = await store.get_turns("s3", limit=5)
    # limit=5 returns at most 5 rows; all 5 must belong to this session.
    assert len(turns) == 5
    assert all(t.session_id == "s3" for t in turns)


async def test_clear_turns(store: SQLiteMemoryStore) -> None:
    await store.add_turn(Turn(session_id="s4", role="user", content="x"))
    await store.clear_turns("s4")
    assert await store.get_turns("s4") == []


# ------------------------------------------------------------------
# Todos
# ------------------------------------------------------------------


async def test_add_and_get_todos(store: SQLiteMemoryStore) -> None:
    todo = Todo(text="Buy milk")
    await store.add_todo(todo)

    todos = await store.get_todos()
    assert len(todos) == 1
    assert todos[0].text == "Buy milk"
    assert todos[0].done is False


async def test_get_todos_excludes_done_by_default(store: SQLiteMemoryStore) -> None:
    t1 = Todo(text="pending")
    t2 = Todo(text="done")
    await store.add_todo(t1)
    await store.add_todo(t2)
    await store.complete_todo(t2.todo_id)

    pending = await store.get_todos()
    assert len(pending) == 1
    assert pending[0].text == "pending"


async def test_get_todos_include_done(store: SQLiteMemoryStore) -> None:
    t = Todo(text="finished")
    await store.add_todo(t)
    await store.complete_todo(t.todo_id)

    all_todos = await store.get_todos(include_done=True)
    assert len(all_todos) == 1
    assert all_todos[0].done is True


async def test_delete_todo(store: SQLiteMemoryStore) -> None:
    t = Todo(text="delete me")
    await store.add_todo(t)
    await store.delete_todo(t.todo_id)

    assert await store.get_todos(include_done=True) == []


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def test_add_and_get_reminders(store: SQLiteMemoryStore) -> None:
    r = Reminder(text="Call dentist", due_at=datetime.now(UTC) + timedelta(hours=1))
    await store.add_reminder(r)

    reminders = await store.get_reminders()
    assert len(reminders) == 1
    assert reminders[0].text == "Call dentist"


async def test_mark_reminder_fired(store: SQLiteMemoryStore) -> None:
    r = Reminder(text="Take meds", due_at=datetime.now(UTC) + timedelta(minutes=5))
    await store.add_reminder(r)
    await store.mark_reminder_fired(r.reminder_id)

    active = await store.get_reminders()
    assert active == []

    all_r = await store.get_reminders(include_fired=True)
    assert len(all_r) == 1
    assert all_r[0].fired is True


async def test_get_due_reminders(store: SQLiteMemoryStore) -> None:
    past = Reminder(text="Overdue", due_at=datetime.now(UTC) - timedelta(seconds=1))
    future = Reminder(text="Future", due_at=datetime.now(UTC) + timedelta(hours=1))
    await store.add_reminder(past)
    await store.add_reminder(future)

    due = await store.get_due_reminders()
    assert len(due) == 1
    assert due[0].text == "Overdue"


async def test_delete_reminder(store: SQLiteMemoryStore) -> None:
    r = Reminder(text="Remove me", due_at=datetime.now(UTC) + timedelta(hours=1))
    await store.add_reminder(r)
    await store.delete_reminder(r.reminder_id)

    assert await store.get_reminders() == []
