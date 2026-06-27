"""StepUpGate — possession-factor step-up approval (U19c, ADR-008 §9).

When STEP_UP_WEBHOOK_URL is set a POST is made to that URL carrying a token and
callback URLs.  The paired phone (or any HTTP client) resolves the request by
calling back the brain at:

    POST /knowledge/stepup/callback/{token}/grant
    POST /knowledge/stepup/callback/{token}/deny

If STEP_UP_WEBHOOK_URL is not configured every step-up request is auto-denied —
the safe default (no webhook = no possession factor = no access).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

_STEPUP_TIMEOUT_S = 30.0


class StepUpDeniedError(PermissionError):
    """Step-up request denied or STEP_UP_WEBHOOK_URL not configured."""


class StepUpTimeout(TimeoutError):
    """No approval decision arrived within the timeout window."""


class StepUpGate:
    """Manages possession-factor approvals for sensitive knowledge operations.

    Usage::

        gate = StepUpGate()                     # reads env vars
        await gate.request("delete_person", {"person_id": "jan"})
        # Returns True if granted; raises StepUpDeniedError or StepUpTimeout

    The /knowledge/stepup/callback/{token}/grant endpoint calls::

        gate.resolve(token, granted=True)
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        brain_base_url: str | None = None,
        timeout: float = _STEPUP_TIMEOUT_S,
    ) -> None:
        self._webhook_url = webhook_url or os.environ.get("STEP_UP_WEBHOOK_URL")
        self._brain_base_url = (
            brain_base_url or os.environ.get("BRAIN_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future[bool]] = {}

    async def request(self, operation: str, context: dict | None = None) -> bool:
        """Request step-up approval.

        Returns ``True`` if granted.
        Raises :exc:`StepUpDeniedError` when no webhook is configured (safe
        default) or when the user explicitly denies.
        Raises :exc:`StepUpTimeout` when no decision arrives in time.
        """
        if not self._webhook_url:
            logger.warning("step-up denied: STEP_UP_WEBHOOK_URL not set (operation=%r)", operation)
            raise StepUpDeniedError(
                "Step-up webhook not configured — operation denied. "
                "Set STEP_UP_WEBHOOK_URL to enable phone-based approval."
            )

        token = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[token] = future

        payload = {
            "token": token,
            "operation": operation,
            "context": context or {},
            "callback_grant": f"{self._brain_base_url}/knowledge/stepup/callback/{token}/grant",
            "callback_deny": f"{self._brain_base_url}/knowledge/stepup/callback/{token}/deny",
            "requested_at": datetime.now(UTC).isoformat(),
            "expires_in_seconds": self._timeout,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            self._pending.pop(token, None)
            logger.error("step-up webhook POST failed: %s", exc)
            raise StepUpDeniedError(f"Step-up webhook unreachable: {exc}") from exc

        try:
            granted = await asyncio.wait_for(asyncio.shield(future), timeout=self._timeout)
        except TimeoutError:
            self._pending.pop(token, None)
            raise StepUpTimeout(
                f"Step-up timed out after {self._timeout:.0f}s for operation {operation!r}"
            )

        self._pending.pop(token, None)
        if not granted:
            raise StepUpDeniedError(f"Step-up denied by owner for operation {operation!r}")
        return True

    def resolve(self, token: str, granted: bool) -> bool:
        """Resolve a pending step-up request.

        Returns ``True`` if the token was found and the future was set.
        Returns ``False`` if the token is unknown or already resolved.
        """
        future = self._pending.get(token)
        if future is None or future.done():
            return False
        future.set_result(granted)
        return True
