"""Connector-level exceptions for M365Connector implementations."""

from __future__ import annotations


class ConnectorError(Exception):
    """Base class for all connector errors."""


class ConnectorAuthError(ConnectorError):
    """Raised when MSAL authentication fails (wrong credentials, OBO rejected, etc.)."""


class ConnectorUnavailableError(ConnectorError):
    """Raised when the Work IQ MCP server is unreachable or returns a 5xx."""


class ConnectorPermissionError(ConnectorError):
    """Raised when the OBO token lacks a required Microsoft Graph scope."""

    def __init__(self, missing_scope: str) -> None:
        self.missing_scope = missing_scope
        super().__init__(f"Missing required scope: {missing_scope}")
