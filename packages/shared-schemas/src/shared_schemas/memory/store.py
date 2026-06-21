"""MemoryStore abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from shared_schemas.memory.models import Reminder, Todo, Turn


class MemoryStore(ABC):
    """Contract for the AURA memory persistence layer.

    Implementations: SQLiteMemoryStore, FakeMemoryStore (tests only).
    """

    # --- Session turns ---

    @abstractmethod
    async def add_turn(self, turn: Turn) -> None:
        """Persist a conversation turn."""

    @abstractmethod
    async def get_turns(self, session_id: str, limit: int = 50) -> list[Turn]:
        """Return the most recent turns for a session, newest last."""

    @abstractmethod
    async def clear_turns(self, session_id: str) -> None:
        """Delete all turns for a session."""

    # --- Todos ---

    @abstractmethod
    async def add_todo(self, todo: Todo) -> None:
        """Persist a new todo."""

    @abstractmethod
    async def get_todos(self, *, include_done: bool = False) -> list[Todo]:
        """Return todos; pending only by default."""

    @abstractmethod
    async def complete_todo(self, todo_id: UUID) -> None:
        """Mark a todo as complete."""

    @abstractmethod
    async def delete_todo(self, todo_id: UUID) -> None:
        """Delete a todo."""

    # --- Reminders ---

    @abstractmethod
    async def add_reminder(self, reminder: Reminder) -> None:
        """Persist a new reminder."""

    @abstractmethod
    async def get_reminders(self, *, include_fired: bool = False) -> list[Reminder]:
        """Return reminders; active only by default."""

    @abstractmethod
    async def mark_reminder_fired(self, reminder_id: UUID) -> None:
        """Mark a reminder as fired so it doesn't re-trigger."""

    @abstractmethod
    async def delete_reminder(self, reminder_id: UUID) -> None:
        """Delete a reminder."""

    # --- Due reminders (used by scheduler) ---

    @abstractmethod
    async def get_due_reminders(self) -> list[Reminder]:
        """Return all reminders that are due and not yet fired."""
