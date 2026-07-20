"""GenericMCPConnector — connects to any MCP-compatible Streamable HTTP server.

Configuration (per connector instance, via key "mcp:<name>"):
  MCP_<NAME>_URL          Base URL of the MCP server (required)
  MCP_<NAME>_AUTH_TYPE    "bearer" | "api_key" | "none" (default: "none")
  MCP_<NAME>_AUTH_VALUE   Token/key value (can be stored in keyring)

Example ENABLED_CONNECTORS entry: "mcp:my-tool-server"
  → reads MCP_MY_TOOL_SERVER_URL, MCP_MY_TOOL_SERVER_AUTH_TYPE, etc.

The GenericMCPConnector implements the M365Connector ABC by raising
ConnectorUnavailableError for all M365-specific methods. It is primarily
used as a pass-through for tool calls via the MCP protocol.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx
from shared_config import ConnectorServiceSettings
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

from connector_service.connectors.errors import ConnectorAuthError, ConnectorUnavailableError

logger = logging.getLogger(__name__)

AuthType = Literal["bearer", "api_key", "none"]


class GenericMCPConnector(M365Connector):
    """Connects to any MCP-compatible Streamable HTTP server.

    The connector key format is "mcp:<name>" where <name> is an upper-cased
    identifier. Environment variables are derived from the name:
      MCP_<NAME>_URL, MCP_<NAME>_AUTH_TYPE, MCP_<NAME>_AUTH_VALUE
    """

    def __init__(self, key: str, settings: ConnectorServiceSettings) -> None:
        # key is e.g. "mcp:my-tool-server" → env prefix "MCP_MY_TOOL_SERVER"
        suffix = key.removeprefix("mcp:").upper().replace("-", "_")
        self._env_prefix = f"MCP_{suffix}"
        self._base_url = os.environ.get(f"{self._env_prefix}_URL", "").rstrip("/")
        if not self._base_url:
            raise ValueError(
                f"{self._env_prefix}_URL is required for generic MCP connector {key!r}"
            )
        self._auth_type: AuthType = os.environ.get(f"{self._env_prefix}_AUTH_TYPE", "none")  # type: ignore[assignment]
        self._auth_value = os.environ.get(f"{self._env_prefix}_AUTH_VALUE", "")
        logger.info(
            "GenericMCPConnector %r → %s (auth=%s)", key, self._base_url, self._auth_type
        )

    def _headers(self) -> dict[str, str]:
        if self._auth_type == "bearer":
            return {"Authorization": f"Bearer {self._auth_value}"}
        if self._auth_type == "api_key":
            return {"X-API-Key": self._auth_value}
        return {}

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Invoke a named MCP tool on this server.

        Args:
            tool_name: MCP tool name (e.g. "search", "create_issue").
            arguments: Tool-specific keyword arguments.

        Returns:
            The parsed JSON response from the MCP server.
        """
        payload = {"tool": tool_name, "arguments": arguments}
        async with httpx.AsyncClient(headers=self._headers(), timeout=15.0) as client:
            resp = await client.post(f"{self._base_url}/tools/call", json=payload)
            if resp.status_code == 401:
                raise ConnectorAuthError(
                    f"MCP server {self._base_url!r} returned 401. Check auth credentials."
                )
            resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # M365Connector ABC — all unsupported (graceful)
    # ------------------------------------------------------------------

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose M365 calendar.")

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose M365 mail.")

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose M365 mail.")

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose Teams.")

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose Tasks.")

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        raise ConnectorUnavailableError("GenericMCPConnector does not expose Tasks.")
