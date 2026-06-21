"""ApprovalManager — holds tool calls pending user approval with a 30 s timeout."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED
from shared_schemas.events.orchestrator import (
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
)

logger = logging.getLogger(__name__)

_APPROVAL_TIMEOUT_S = 30.0


class ApprovalTimeout(TimeoutError):
    """Raised when no approval decision arrives within the timeout window."""


class ApprovalDeniedError(PermissionError):
    """Raised when the user explicitly denies the approval request."""


@dataclass
class _PendingApproval:
    approval_id: str
    tool_name: str
    arguments: dict
    session_id: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    future: asyncio.Future[bool] = field(default_factory=asyncio.get_event_loop().create_future)


class ApprovalManager:
    """Manages the approval lifecycle for sensitive tool calls.

    Usage::

        manager = ApprovalManager(bus, session_id="s1")
        # In orchestrator flow:
        result = await manager.request_approval("send_mail", {"to": "...", "body": "..."})
        # Returns True if approved; raises on timeout or denial
    """

    def __init__(self, bus: AsyncEventBus, session_id: str) -> None:
        self._bus = bus
        self._session_id = session_id
        self._pending: dict[str, _PendingApproval] = {}

    def needs_approval(self, tool_name: str) -> bool:
        return tool_name in APPROVAL_REQUIRED

    async def request_approval(self, tool_name: str, arguments: dict) -> bool:
        """Request user approval. Raises ApprovalTimeout or ApprovalDeniedError."""
        approval_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        pending = _PendingApproval(
            approval_id=approval_id,
            tool_name=tool_name,
            arguments=arguments,
            session_id=self._session_id,
            future=loop.create_future(),
        )
        self._pending[approval_id] = pending

        await self._bus.publish(
            ApprovalRequested(
                session_id=self._session_id,
                approval_id=approval_id,
                tool_name=tool_name,
                arguments_summary=str(arguments)[:200],
            )
        )
        logger.info("Approval requested: %s tool=%s", approval_id, tool_name)

        try:
            approved = await asyncio.wait_for(pending.future, timeout=_APPROVAL_TIMEOUT_S)
        except TimeoutError:
            self._pending.pop(approval_id, None)
            raise ApprovalTimeout(
                f"No approval response for {tool_name!r} within {_APPROVAL_TIMEOUT_S}s"
            )

        if not approved:
            raise ApprovalDeniedError(f"Approval denied for tool {tool_name!r}")

        return True

    async def grant(self, approval_id: str) -> None:
        pending = self._pending.pop(approval_id, None)
        if pending is None:
            logger.warning("Grant for unknown approval_id %s", approval_id)
            return
        if not pending.future.done():
            pending.future.set_result(True)
        await self._bus.publish(
            ApprovalGranted(
                session_id=self._session_id,
                approval_id=approval_id,
                tool_name=pending.tool_name,
            )
        )

    async def deny(self, approval_id: str) -> None:
        pending = self._pending.pop(approval_id, None)
        if pending is None:
            logger.warning("Deny for unknown approval_id %s", approval_id)
            return
        if not pending.future.done():
            pending.future.set_result(False)
        await self._bus.publish(
            ApprovalDenied(
                session_id=self._session_id,
                approval_id=approval_id,
                tool_name=pending.tool_name,
            )
        )
