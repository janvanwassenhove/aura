"""AsyncEventBus — asyncio in-process pub/sub bus."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from shared_schemas.events.base import BaseEvent

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=BaseEvent)
Handler = Callable[[BaseEvent], Awaitable[None]]


class EventBusNotStartedError(RuntimeError):
    """Raised when publish() is called before start()."""


class AsyncEventBus:
    """Asyncio-native pub/sub event bus.

    Handlers are dispatched with asyncio.create_task so that slow or failing
    handlers cannot block the publisher.

    Usage::

        bus = AsyncEventBus()
        await bus.start()
        bus.subscribe(RobotConnected, my_handler)
        await bus.publish(RobotConnected(session_id="s1", adapter_name="fake"))
        await bus.stop()
    """

    def __init__(self) -> None:
        self._handlers: dict[type[BaseEvent], list[Handler]] = defaultdict(list)
        self._started = False

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._started = False

    def subscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], Awaitable[None]],
    ) -> None:
        self._handlers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], Awaitable[None]],
    ) -> None:
        try:
            self._handlers[event_type].remove(handler)  # type: ignore[arg-type]
        except ValueError:
            pass

    async def publish(self, event: BaseEvent) -> None:
        if not self._started:
            raise EventBusNotStartedError(
                "AsyncEventBus.start() must be called before publish()"
            )
        # Exact-type handlers first, then BaseEvent catch-all handlers
        exact = list(self._handlers.get(type(event), []))
        wildcard = [
            h for h in self._handlers.get(BaseEvent, [])
            if h not in exact
        ]
        for handler in exact + wildcard:
            asyncio.create_task(self._safe_call(handler, event))

    @staticmethod
    async def _safe_call(handler: Handler, event: BaseEvent) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception(
                "Unhandled exception in event handler %s for event %s",
                handler,
                type(event).__name__,
            )
