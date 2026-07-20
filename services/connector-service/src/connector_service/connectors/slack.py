"""SlackConnector — Slack Web API connector (skeleton).

Token stored in OS keyring via identity-service.
Required Slack bot token scopes: chat:write, channels:read, channels:history.

Methods:
  - post_message(channel, text) → Slack message permalink
  - list_channels() → list of channel names/IDs

M365Connector ABC methods that don't map to Slack raise ConnectorUnavailableError.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import httpx
from shared_config import ConnectorServiceSettings
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

from connector_service.connectors.errors import ConnectorAuthError, ConnectorUnavailableError

logger = logging.getLogger(__name__)

_API_BASE = "https://slack.com/api"


class SlackConnector(M365Connector):
    """Slack Web API connector — messaging and channel management."""

    def __init__(
        self,
        settings: ConnectorServiceSettings,
        identity_url: str = "http://identity-service:8006",
        user_id: str = "default",
        token_fetcher: Callable[[str, str], Awaitable[str | None]] | None = None,
    ) -> None:
        self._identity_url = identity_url.rstrip("/")
        self._user_id = user_id
        self._token_fetcher = token_fetcher

    async def _get_token(self) -> str:
        if self._token_fetcher is not None:  # Phase 1 in-process seam
            token = await self._token_fetcher(self._user_id, "slack")
            if not token:
                raise ConnectorAuthError(
                    f"Slack token not found for user={self._user_id!r}."
                )
            return token
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{self._identity_url}/identity/token/{self._user_id}/slack"
            )
        if resp.status_code == 401:
            raise ConnectorAuthError(
                f"Slack token not found for user={self._user_id!r}. "
                "Store via PUT /identity/token/{user_id}/slack."
            )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def post_message(self, channel: str, text: str) -> dict:
        """Post a message to a Slack channel. Returns the response payload."""
        token = await self._get_token()
        async with httpx.AsyncClient(headers=self._headers(token), timeout=10.0) as client:
            resp = await client.post(
                f"{_API_BASE}/chat.postMessage",
                json={"channel": channel, "text": text},
            )
            resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ConnectorUnavailableError(f"Slack error: {data.get('error', 'unknown')}")
        return data

    async def list_channels(self) -> list[dict]:
        """Return a list of public channels (id, name)."""
        token = await self._get_token()
        async with httpx.AsyncClient(headers=self._headers(token), timeout=10.0) as client:
            resp = await client.get(
                f"{_API_BASE}/conversations.list",
                params={"types": "public_channel", "limit": 200},
            )
            resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ConnectorUnavailableError(f"Slack error: {data.get('error', 'unknown')}")
        return [{"id": c["id"], "name": c["name"]} for c in data.get("channels", [])]

    # ------------------------------------------------------------------
    # M365Connector ABC — Teams messages map to Slack post_message
    # ------------------------------------------------------------------

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        """Routes Teams-style post_teams_message to Slack post_message."""
        import uuid
        from datetime import UTC, datetime
        await self.post_message(channel=channel, text=content)
        return TeamsMessage(
            message_id=str(uuid.uuid4()),
            channel=channel,
            content=content,
            sent_at=datetime.now(UTC),
        )

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        raise ConnectorUnavailableError("Slack connector does not expose calendar.")

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        raise ConnectorUnavailableError("Slack connector does not expose mail.")

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        raise ConnectorUnavailableError("Slack connector does not expose mail.")

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        raise ConnectorUnavailableError("Slack connector does not expose Tasks.")

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        raise ConnectorUnavailableError("Slack connector does not expose Tasks.")
