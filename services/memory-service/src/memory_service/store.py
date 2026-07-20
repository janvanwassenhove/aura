"""SQLiteMemoryStore — async SQLite-backed MemoryStore implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from shared_schemas.memory.models import Reminder, Todo, Turn
from shared_schemas.memory.store import MemoryStore
from sqlalchemy import delete, select, update

from memory_service.db.models import ReminderRow, TodoRow, TurnRow
from memory_service.db.session import SessionLocal


class SQLiteMemoryStore(MemoryStore):
    """Concrete MemoryStore backed by SQLite via aiosqlite + SQLAlchemy async."""

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    async def add_turn(self, turn: Turn) -> None:
        row = TurnRow(
            turn_id=str(turn.turn_id),
            session_id=turn.session_id,
            role=turn.role,
            content=turn.content,
            timestamp=turn.timestamp.isoformat(),
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()

    async def get_turns(self, session_id: str, limit: int = 50) -> list[Turn]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(TurnRow)
                .where(TurnRow.session_id == session_id)
                .order_by(TurnRow.timestamp.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
        return [
            Turn(
                turn_id=uuid.UUID(r.turn_id),
                session_id=r.session_id,
                role=r.role,
                content=r.content,
                timestamp=datetime.fromisoformat(r.timestamp),
            )
            for r in reversed(rows)
        ]

    async def clear_turns(self, session_id: str) -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(TurnRow).where(TurnRow.session_id == session_id)
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Todos
    # ------------------------------------------------------------------

    async def add_todo(self, todo: Todo) -> None:
        row = TodoRow(
            todo_id=str(todo.todo_id),
            text=todo.text,
            done=todo.done,
            created_at=todo.created_at.isoformat(),
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()

    async def get_todos(self, *, include_done: bool = False) -> list[Todo]:
        async with SessionLocal() as session:
            stmt = select(TodoRow)
            if not include_done:
                stmt = stmt.where(TodoRow.done == False)  # noqa: E712
            result = await session.execute(stmt.order_by(TodoRow.created_at))
            rows = result.scalars().all()
        return [
            Todo(
                todo_id=uuid.UUID(r.todo_id),
                text=r.text,
                done=r.done,
                created_at=datetime.fromisoformat(r.created_at),
            )
            for r in rows
        ]

    async def complete_todo(self, todo_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(TodoRow)
                .where(TodoRow.todo_id == str(todo_id))
                .values(done=True)
            )
            await session.commit()

    async def delete_todo(self, todo_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(TodoRow).where(TodoRow.todo_id == str(todo_id))
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    async def add_reminder(self, reminder: Reminder) -> None:
        row = ReminderRow(
            reminder_id=str(reminder.reminder_id),
            text=reminder.text,
            due_at=reminder.due_at.isoformat(),
            fired=reminder.fired,
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()

    async def get_reminders(self, *, include_fired: bool = False) -> list[Reminder]:
        async with SessionLocal() as session:
            stmt = select(ReminderRow)
            if not include_fired:
                stmt = stmt.where(ReminderRow.fired == False)  # noqa: E712
            result = await session.execute(stmt.order_by(ReminderRow.due_at))
            rows = result.scalars().all()
        return [
            Reminder(
                reminder_id=uuid.UUID(r.reminder_id),
                text=r.text,
                due_at=datetime.fromisoformat(r.due_at),
                fired=r.fired,
            )
            for r in rows
        ]

    async def mark_reminder_fired(self, reminder_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(ReminderRow)
                .where(ReminderRow.reminder_id == str(reminder_id))
                .values(fired=True)
            )
            await session.commit()

    async def delete_reminder(self, reminder_id: uuid.UUID) -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(ReminderRow).where(ReminderRow.reminder_id == str(reminder_id))
            )
            await session.commit()

    async def get_due_reminders(self) -> list[Reminder]:
        now = datetime.now(UTC).isoformat()
        async with SessionLocal() as session:
            result = await session.execute(
                select(ReminderRow)
                .where(ReminderRow.fired == False)  # noqa: E712
                .where(ReminderRow.due_at <= now)
            )
            rows = result.scalars().all()
        return [
            Reminder(
                reminder_id=uuid.UUID(r.reminder_id),
                text=r.text,
                due_at=datetime.fromisoformat(r.due_at),
                fired=r.fired,
            )
            for r in rows
        ]
