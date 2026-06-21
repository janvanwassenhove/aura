"""WorkIQConnector — Microsoft Work IQ MCP via MSAL OBO flow.

CRITICAL: MCPStreamableHTTPTool silently ignores the `headers=` constructor
parameter. Auth MUST be supplied via:
    http_client=httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"})

See ADR-006 for full rationale.

Token lifecycle:
  - Access token is retrieved from identity-service at call time.
  - identity-service handles Device Code flow, silent refresh, and keyring storage.
  - WorkIQConnector never stores credentials; it fetches a live token per-request.
  - On 401 from identity-service, ConnectorAuthError is raised; the caller
    (connector-service) emits AuthRequiredEvent on the event bus.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
import msal

from connector_service.connectors.errors import (
    ConnectorAuthError,
    ConnectorUnavailableError,
)
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage
from shared_config import ConnectorServiceSettings

logger = logging.getLogger(__name__)

_BASE_URL = "https://agent365.svc.cloud.microsoft/agents/servers"

_SCOPES = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Tasks.ReadWrite",
    "https://graph.microsoft.com/ChannelMessage.Send",
]


class WorkIQConnector(M365Connector):
    """Live connector using Microsoft Work IQ MCP.

    Token acquisition flow:
      1. Calls identity-service GET /identity/token/{user_id}/m365 for a user token.
      2. Exchanges it for a service token via MSAL OBO (ConfidentialClientApplication).
      3. Uses the service token for all Work IQ MCP calls.
      4. identity-service handles silent refresh; on 401 we raise ConnectorAuthError.
    """

    def __init__(
        self,
        settings: ConnectorServiceSettings,
        identity_url: str = "http://identity-service:8006",
        user_id: str = "default",
    ) -> None:
        self._identity_url = identity_url.rstrip("/")
        self._user_id = user_id
        self._client_id = settings.azure_client_id
        self._client_secret = settings.azure_client_secret.get_secret_value()
        self._tenant_id = settings.azure_tenant_id
        self._app = msal.ConfidentialClientApplication(
            self._client_id,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            client_credential=self._client_secret,
        )
        self._obo_token: str | None = None
        self._obo_expires_at: datetime | None = None

    async def _get_user_token(self) -> str:
        """Fetch a valid user access token from identity-service."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{self._identity_url}/identity/token/{self._user_id}/m365"
            )
        if resp.status_code == 401:
            raise ConnectorAuthError(
                f"identity-service returned 401 for user={self._user_id!r}: "
                f"{resp.json().get('detail', 'token expired or missing')}. "
                "Re-authenticate via POST /identity/auth/microsoft/start."
            )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _acquire_obo_token(self, user_token: str) -> str:
        """Exchange a user token for an OBO service token; raises ConnectorAuthError on failure."""
        result = self._app.acquire_token_on_behalf_of(
            user_assertion=user_token,
            scopes=_SCOPES,
        )
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "unknown"))
            raise ConnectorAuthError(f"MSAL OBO failed: {error}")
        return result["access_token"]

    async def _client(self) -> httpx.AsyncClient:
        """Return a pre-authed httpx client.

        Refreshes the OBO token if absent or near expiry.
        """
        now = datetime.now(UTC)
        if self._obo_token is None or (
            self._obo_expires_at and now >= self._obo_expires_at
        ):
            user_token = await self._get_user_token()
            self._obo_token = self._acquire_obo_token(user_token)
            # OBO tokens typically live 1 h; expire 5 min early
            from datetime import timedelta
            self._obo_expires_at = now + timedelta(minutes=55)

        return httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self._obo_token}"},
            timeout=10.0,
        )

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        async with await self._client() as client:
            resp = await client.get(
                f"{_BASE_URL}/mcp_CalendarTools/calendar/today"
            )
            resp.raise_for_status()
        return [CalendarEvent(**item) for item in resp.json()]

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        async with await self._client() as client:
            resp = await client.get(
                f"{_BASE_URL}/mcp_MailTools/mail/unread",
                params={"limit": limit},
            )
            resp.raise_for_status()
        return [MailItem(**item) for item in resp.json()]

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        async with await self._client() as client:
            resp = await client.post(
                f"{_BASE_URL}/mcp_TeamsServer/teams/message",
                json={"channel": channel, "content": content},
            )
            resp.raise_for_status()
        return TeamsMessage(**resp.json())

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        async with await self._client() as client:
            resp = await client.post(
                f"{_BASE_URL}/mcp_MailTools/mail/send",
                json={"to": to, "subject": subject, "body": body},
            )
            resp.raise_for_status()

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        params = {}
        if plan_id:
            params["plan_id"] = plan_id
        async with await self._client() as client:
            resp = await client.get(
                f"{_BASE_URL}/mcp_PlannerServer/tasks",
                params=params,
            )
            resp.raise_for_status()
        return [Task(**item) for item in resp.json()]

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        payload: dict = {"title": title}
        if plan_id:
            payload["plan_id"] = plan_id
        if due_date:
            payload["due_date"] = due_date
        async with await self._client() as client:
            resp = await client.post(
                f"{_BASE_URL}/mcp_PlannerServer/tasks",
                json=payload,
            )
            resp.raise_for_status()
        return Task(**resp.json())
