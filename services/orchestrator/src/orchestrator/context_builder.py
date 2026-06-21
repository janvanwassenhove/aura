"""ContextBuilder — assembles the system prompt context from live data sources."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class DailySnapshot(Protocol):
    """Interface for services that provide daily context data."""

    async def get_calendar_summary(self) -> str: ...
    async def get_unread_mail_count(self) -> int: ...
    async def get_pending_tasks_summary(self) -> str: ...


class ContextBuilder:
    """Builds context strings for injection into system prompts.

    Designed to be fast; individual data calls have their own timeouts via
    the connector service.
    """

    def __init__(self, snapshot: DailySnapshot | None = None) -> None:
        self._snapshot = snapshot

    async def build_context(self) -> str:
        if self._snapshot is None:
            return "(no live context available)"
        try:
            calendar = await self._snapshot.get_calendar_summary()
            mail_count = await self._snapshot.get_unread_mail_count()
            tasks = await self._snapshot.get_pending_tasks_summary()
            return (
                f"Calendar: {calendar}\n"
                f"Unread mail: {mail_count}\n"
                f"Tasks: {tasks}"
            )
        except Exception:
            logger.exception("Failed to build context snapshot")
            return "(context unavailable)"

    async def build_tool_list(self, allowed_tools: frozenset[str]) -> str:
        return ", ".join(sorted(allowed_tools))
