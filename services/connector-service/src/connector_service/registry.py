"""ConnectorRegistry — manages multiple connectors with graceful startup.

Connectors are registered by key (e.g. "m365", "google", "github", "slack").
At startup, only connectors listed in ENABLED_CONNECTORS are instantiated.
If a connector's credentials are missing, it starts in UNAUTHENTICATED state
rather than crashing the service.

Usage:
    registry = ConnectorRegistry(settings, token_provider)
    registry.build()

    connector = registry.get("m365")          # None if not enabled / unauthenticated
    health    = registry.health()             # dict[str, str] key→status
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from enum import Enum

import httpx
from shared_config import ConnectorServiceSettings
from shared_schemas.m365.connector import M365Connector

logger = logging.getLogger(__name__)


class ConnectorStatus(str, Enum):
    OK = "ok"
    MOCK = "mock"  # U52: honest badge — canned data, not a real account
    UNAUTHENTICATED = "unauthenticated"
    UNAVAILABLE = "unavailable"


class ConnectorEntry:
    """Wrapper holding a connector instance and its current status."""

    def __init__(self, key: str, connector: M365Connector | None, status: ConnectorStatus) -> None:
        self.key = key
        self.connector = connector
        self.status = status


class ConnectorRegistry:
    """Registry that builds and tracks all enabled connectors."""

    def __init__(
        self,
        settings: ConnectorServiceSettings,
        http_client: httpx.AsyncClient | None = None,
        token_fetcher: Callable[[str, str], Awaitable[str | None]] | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        # When set (aura-brain), connectors fetch tokens from identity in-process
        # instead of over HTTP (Phase 1 seam).
        self._token_fetcher = token_fetcher
        self._entries: dict[str, ConnectorEntry] = {}

    def build(self) -> None:
        """Instantiate all enabled connectors. Missing credentials → UNAUTHENTICATED."""
        for key in self._settings.enabled_connector_list:
            entry = self._build_one(key)
            self._entries[key] = entry
            logger.info("Connector %r registered — status=%s", key, entry.status.value)

    def _build_one(self, key: str) -> ConnectorEntry:
        try:
            connector = self._create_connector(key)
            # U52: honest statuses — a mock connector must never show as
            # "Connected". Mocks self-identify by class name or an `is_mock` flag.
            is_mock = getattr(connector, "is_mock", False) or type(connector).__name__.startswith("Mock")
            status = ConnectorStatus.MOCK if is_mock else ConnectorStatus.OK
            return ConnectorEntry(key=key, connector=connector, status=status)
        except _AuthMissingError as exc:
            logger.warning(
                "Connector %r starting in UNAUTHENTICATED state: %s "
                "(complete auth flow at POST /identity/auth/%s/start)",
                key, exc, key,
            )
            return ConnectorEntry(key=key, connector=None, status=ConnectorStatus.UNAUTHENTICATED)
        except Exception as exc:
            logger.error("Connector %r failed to initialize: %s", key, exc)
            return ConnectorEntry(key=key, connector=None, status=ConnectorStatus.UNAVAILABLE)

    def _create_connector(self, key: str) -> M365Connector:
        s = self._settings
        if key == "m365":
            if s.m365_connector == "mock":
                from connector_service.connectors.mock import MockM365Connector
                return MockM365Connector()
            # workiq — requires Azure credentials
            if not s.azure_client_id or not s.azure_tenant_id:
                raise _AuthMissingError(
                    "AZURE_CLIENT_ID and AZURE_TENANT_ID are required for M365_CONNECTOR=workiq"
                )
            from connector_service.connectors.workiq import WorkIQConnector
            return WorkIQConnector(settings=s, identity_url=s.identity_service_url,
                                   token_fetcher=self._token_fetcher)

        if key == "google":
            if not s.google_client_secrets_file:
                raise _AuthMissingError(
                    "GOOGLE_CLIENT_SECRETS_FILE is required for the google connector"
                )
            from connector_service.connectors.google import GoogleConnector
            return GoogleConnector(settings=s, identity_url=s.identity_service_url,
                                   token_fetcher=self._token_fetcher)

        if key == "github":
            # GitHub token may be stored in keyring — absence is not fatal at startup
            from connector_service.connectors.github import GitHubConnector
            return GitHubConnector(settings=s, identity_url=s.identity_service_url,
                                   token_fetcher=self._token_fetcher)

        if key == "slack":
            from connector_service.connectors.slack import SlackConnector
            return SlackConnector(settings=s, identity_url=s.identity_service_url,
                                  token_fetcher=self._token_fetcher)

        if key.startswith("mcp:"):
            # Generic MCP connector: key format "mcp:<name>"
            from connector_service.connectors.mcp_generic import GenericMCPConnector
            return GenericMCPConnector(key=key, settings=s)

        raise ValueError(f"Unknown connector key: {key!r}")

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get(self, key: str) -> M365Connector | None:
        """Return the live connector for key, or None if unavailable/unauthenticated."""
        entry = self._entries.get(key)
        return entry.connector if entry else None

    def get_primary_m365(self) -> M365Connector | None:
        """Return the first available M365-compatible connector (m365 preferred)."""
        for key in ("m365", "google"):
            c = self.get(key)
            if c is not None:
                return c
        return None

    def health(self) -> dict[str, str]:
        """Return {connector_key: status_string} for all registered connectors."""
        return {k: e.status.value for k, e in self._entries.items()}

    def overall_status(self) -> str:
        statuses = {e.status for e in self._entries.values()}
        if not statuses:
            return ConnectorStatus.UNAVAILABLE.value
        # A MOCK connector is functional (honest canned data), just not real.
        functional = {ConnectorStatus.OK, ConnectorStatus.MOCK}
        if all(s in functional for s in statuses):
            return "ok"
        if any(s in functional for s in statuses):
            return "degraded"
        return "unavailable"


class _AuthMissingError(Exception):
    """Raised when a connector's credentials are absent at startup."""
