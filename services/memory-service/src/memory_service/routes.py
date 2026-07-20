"""FastAPI routes for memory-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from shared_schemas.memory.models import Reminder, Todo, Turn

from memory_service.store import SQLiteMemoryStore

router = APIRouter(prefix="/memory")

_store: SQLiteMemoryStore | None = None


def set_store(store: SQLiteMemoryStore) -> None:
    global _store
    _store = store


def _get_store() -> SQLiteMemoryStore:
    assert _store is not None, "Store not initialised"
    return _store


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ------------------------------------------------------------------
# Turns
# ------------------------------------------------------------------


@router.post("/turns")
async def add_turn(body: dict) -> JSONResponse:
    turn = Turn(
        session_id=body["session_id"],
        role=body["role"],
        content=body["content"],
    )
    await _get_store().add_turn(turn)
    return JSONResponse({"turn_id": str(turn.turn_id)})


@router.get("/turns/{session_id}")
async def get_turns(session_id: str, limit: int = 50) -> JSONResponse:
    turns = await _get_store().get_turns(session_id, limit=limit)
    return JSONResponse([t.model_dump(mode="json") for t in turns])


@router.delete("/turns/{session_id}")
async def clear_turns(session_id: str) -> JSONResponse:
    await _get_store().clear_turns(session_id)
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Todos
# ------------------------------------------------------------------


@router.post("/todos")
async def add_todo(body: dict) -> JSONResponse:
    todo = Todo(text=body["text"])
    await _get_store().add_todo(todo)
    return JSONResponse({"todo_id": str(todo.todo_id)})


@router.get("/todos")
async def get_todos(include_done: bool = False) -> JSONResponse:
    todos = await _get_store().get_todos(include_done=include_done)
    return JSONResponse([t.model_dump(mode="json") for t in todos])


@router.post("/todos/{todo_id}/complete")
async def complete_todo(todo_id: str) -> JSONResponse:
    await _get_store().complete_todo(uuid.UUID(todo_id))
    return JSONResponse({"ok": True})


@router.delete("/todos/{todo_id}")
async def delete_todo(todo_id: str) -> JSONResponse:
    await _get_store().delete_todo(uuid.UUID(todo_id))
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Reminders
# ------------------------------------------------------------------


@router.post("/reminders")
async def add_reminder(body: dict) -> JSONResponse:
    reminder = Reminder(
        text=body["text"],
        due_at=datetime.fromisoformat(body["due_at"]),
    )
    await _get_store().add_reminder(reminder)
    return JSONResponse({"reminder_id": str(reminder.reminder_id)})


@router.get("/reminders")
async def get_reminders(include_fired: bool = False) -> JSONResponse:
    reminders = await _get_store().get_reminders(include_fired=include_fired)
    return JSONResponse([r.model_dump(mode="json") for r in reminders])


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str) -> JSONResponse:
    await _get_store().delete_reminder(uuid.UUID(reminder_id))
    return JSONResponse({"ok": True})
