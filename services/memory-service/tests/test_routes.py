"""FastAPI route tests for memory-service (spec 007 T-007-10).

Uses httpx.AsyncClient with a bare router app (no lifespan) so we can
monkeypatch the SessionLocal to an in-memory SQLite engine with StaticPool,
mirroring the pattern used in test_store.py.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from memory_service import routes
from memory_service.db.models import Base
from memory_service.store import SQLiteMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_TEST_ENGINE, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
async def _fresh_db(monkeypatch) -> None:
    """Recreate tables and inject the store before each test."""
    import memory_service.store as store_mod
    monkeypatch.setattr(store_mod, "SessionLocal", _TestSession)

    async with _TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    routes.set_store(SQLiteMemoryStore())


@pytest.fixture()
async def client() -> AsyncClient:
    """Bare FastAPI app with only the memory router (no lifespan)."""
    app = FastAPI()
    app.include_router(routes.router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


async def test_memory_health(client: AsyncClient) -> None:
    resp = await client.get("/memory/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------
# Turns
# ------------------------------------------------------------------


async def test_turn_round_trip(client: AsyncClient) -> None:
    resp = await client.post(
        "/memory/turns",
        json={"session_id": "s1", "role": "user", "content": "Hello"},
    )
    assert resp.status_code == 200
    assert "turn_id" in resp.json()

    get_resp = await client.get("/memory/turns/s1")
    assert get_resp.status_code == 200
    turns = get_resp.json()
    assert any(t["content"] == "Hello" for t in turns)


async def test_clear_turns(client: AsyncClient) -> None:
    await client.post("/memory/turns", json={"session_id": "s2", "role": "user", "content": "bye"})
    await client.delete("/memory/turns/s2")
    get_resp = await client.get("/memory/turns/s2")
    assert get_resp.json() == []


# ------------------------------------------------------------------
# Todos
# ------------------------------------------------------------------


async def test_todo_crud(client: AsyncClient) -> None:
    add_resp = await client.post("/memory/todos", json={"text": "Buy milk"})
    assert add_resp.status_code == 200
    todo_id = add_resp.json()["todo_id"]

    get_resp = await client.get("/memory/todos")
    assert any(t["todo_id"] == todo_id for t in get_resp.json())

    complete_resp = await client.post(f"/memory/todos/{todo_id}/complete")
    assert complete_resp.status_code == 200

    delete_resp = await client.delete(f"/memory/todos/{todo_id}")
    assert delete_resp.status_code == 200


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


async def test_reminder_crud_with_delete(client: AsyncClient) -> None:
    add_resp = await client.post(
        "/memory/reminders",
        json={"text": "Stand-up", "due_at": "2030-01-01T09:00:00+00:00"},
    )
    assert add_resp.status_code == 200
    reminder_id = add_resp.json()["reminder_id"]

    get_resp = await client.get("/memory/reminders")
    assert any(r["reminder_id"] == reminder_id for r in get_resp.json())

    delete_resp = await client.delete(f"/memory/reminders/{reminder_id}")
    assert delete_resp.status_code == 200

    get_after = await client.get("/memory/reminders")
    assert not any(r["reminder_id"] == reminder_id for r in get_after.json())
