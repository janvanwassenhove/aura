"""WebhookDispatcher — delivers AURA events to registered external URLs.

SECURITY:
- Webhook URLs are validated to be http/https only.
- No secrets are included in outbound webhook payloads beyond the event JSON.
- Exponential backoff with a cap of 3 retries (FR-008).
- Inactive webhooks (failed all retries) are flagged and skipped.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from shared_events.bus import AsyncEventBus
from shared_schemas.events.base import BaseEvent
from shared_schemas.gateway.models import WebhookRegistration

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5  # 0.5s, 1s, 2s
_MAX_FAILURE_COUNT = _MAX_RETRIES


class WebhookDispatcher:
    """Subscribes to the event bus and fans out to registered webhook URLs.

    Usage::

        dispatcher = WebhookDispatcher(bus)
        dispatcher.register("https://agent.example.com/hook", events=["RobotModeChanged"])
        # Events matching the filter are POSTed to the URL.
    """

    def __init__(self, bus: AsyncEventBus, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._bus = bus
        self._webhooks: dict[str, WebhookRegistration] = {}
        self._http = http_client or httpx.AsyncClient(timeout=5.0)
        # Subscribe to ALL events via the base type catch-all
        bus.subscribe(BaseEvent, self._on_event)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        url: str,
        events: list[str] | None = None,
        webhook_id: str | None = None,
    ) -> WebhookRegistration:
        """Register a webhook callback URL.

        Args:
            url: Must start with ``http://`` or ``https://``.
            events: Event type names to filter on.  Empty list = all events.
            webhook_id: Optional stable ID; auto-generated if omitted.

        Raises:
            ValueError: if *url* is not a valid http/https URL.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Webhook URL must be http(s): {url!r}")
        reg = WebhookRegistration(
            url=url,
            events=events or [],
        )
        if webhook_id:
            reg.webhook_id = webhook_id
        self._webhooks[reg.webhook_id] = reg
        logger.info("Webhook registered: id=%s url=%s events=%s", reg.webhook_id, url, events)
        return reg

    def deregister(self, webhook_id: str) -> bool:
        """Remove a webhook by ID. Returns True if it existed."""
        return self._webhooks.pop(webhook_id, None) is not None

    def list_webhooks(self) -> list[WebhookRegistration]:
        return list(self._webhooks.values())

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _on_event(self, event: BaseEvent) -> None:
        """Fan-out handler — called for every bus event."""
        event_type_name = type(event).__name__
        payload = event.model_dump(mode="json")

        for webhook_id, reg in list(self._webhooks.items()):
            if not reg.active:
                continue
            # Filter: if events list is non-empty, only send matching types
            if reg.events and event_type_name not in reg.events:
                continue
            asyncio.create_task(self._deliver(webhook_id, reg.url, payload))

    async def _deliver(self, webhook_id: str, url: str, payload: dict) -> None:
        """Attempt delivery with exponential backoff; deactivate after max failures."""
        reg = self._webhooks.get(webhook_id)
        if reg is None:
            return

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._http.post(url, json=payload)
                if resp.is_success:
                    logger.debug("Webhook %s delivered (attempt %d)", webhook_id, attempt)
                    return
                logger.warning(
                    "Webhook %s HTTP %d (attempt %d/%d)",
                    webhook_id, resp.status_code, attempt, _MAX_RETRIES,
                )
            except Exception as exc:
                logger.warning(
                    "Webhook %s delivery error (attempt %d/%d): %s",
                    webhook_id, attempt, _MAX_RETRIES, exc,
                )

            # Backoff before retry (except after last attempt)
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE_S * (2 ** (attempt - 1)))

        # All retries exhausted — deactivate webhook (FR-008)
        if reg.webhook_id in self._webhooks:
            self._webhooks[reg.webhook_id].active = False
            self._webhooks[reg.webhook_id].failure_count += 1
            logger.error(
                "Webhook %s deactivated after %d failed attempts",
                webhook_id, _MAX_RETRIES,
            )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
