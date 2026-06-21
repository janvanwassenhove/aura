"""Connectors sub-package."""

from connector_service.connectors.errors import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorPermissionError,
    ConnectorUnavailableError,
)
from connector_service.connectors.mock import MockM365Connector

__all__ = [
    "MockM365Connector",
    "ConnectorError",
    "ConnectorAuthError",
    "ConnectorUnavailableError",
    "ConnectorPermissionError",
]
