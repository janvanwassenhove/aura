"""IntentRouter — maps user intents to tools/handlers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from shared_policies import MODE_TOOL_MAP

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    name: str
    confidence: float
    parameters: dict = field(default_factory=dict)
    raw_text: str = ""


class IntentRouter:
    """Routes recognized intents to callable handlers.

    Handlers are registered per-intent-name.  If the current mode does not
    allow the tool associated with the intent, the call is blocked and a
    PermissionError is raised.
    """

    def __init__(self, mode: str = "work") -> None:
        self._mode = mode
        self._handlers: dict[str, list] = {}

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in MODE_TOOL_MAP:
            raise ValueError(f"Unknown mode: {mode!r}")
        self._mode = mode
        logger.info("IntentRouter mode → %s", mode)

    def register(self, tool_name: str, handler) -> None:  # noqa: ANN001
        self._handlers.setdefault(tool_name, []).append(handler)

    def allowed_tools(self) -> frozenset[str]:
        return MODE_TOOL_MAP.get(self._mode, frozenset())

    def is_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools()

    async def route(self, tool_name: str, parameters: dict) -> object:
        if not self.is_allowed(tool_name):
            raise PermissionError(
                f"Tool {tool_name!r} is not available in mode {self._mode!r}"
            )
        handlers = self._handlers.get(tool_name, [])
        if not handlers:
            raise LookupError(f"No handler registered for tool {tool_name!r}")
        result = None
        for handler in handlers:
            result = await handler(**parameters)
        return result
