"""Reminder scheduler — fires due reminders every 10 seconds."""

from __future__ import annotations

import asyncio
import logging

from shared_events.bus import AsyncEventBus
from shared_schemas.events.system import ReminderTriggered

from memory_service.store import SQLiteMemoryStore

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 10.0


class ReminderScheduler:
    def __init__(self, store: SQLiteMemoryStore, bus: AsyncEventBus, session_id: str) -> None:
        self._store = store
        self._bus = bus
        self._session_id = session_id
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())
        logger.info("ReminderScheduler started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(_POLL_INTERVAL_S)
            try:
                due = await self._store.get_due_reminders()
                for reminder in due:
                    await self._store.mark_reminder_fired(reminder.reminder_id)
                    await self._bus.publish(
                        ReminderTriggered(
                            session_id=self._session_id,
                            reminder_id=reminder.reminder_id,
                            message=reminder.text,
                        )
                    )
                    logger.info("Reminder fired: %s", reminder.text[:60])
            except Exception:
                logger.exception("Error in reminder scheduler loop")
