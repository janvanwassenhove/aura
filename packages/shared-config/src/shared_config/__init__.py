"""shared-config — pydantic-settings classes for all AURA services.

Usage:
    from shared_config import ConnectorServiceSettings

    settings = ConnectorServiceSettings()
    print(settings.azure_client_id)

Settings are loaded from (in priority order):
  1. Environment variables
  2. .env.local in the current working directory (never committed)
  3. Field defaults

Required fields (no default) raise pydantic_settings.SettingsError if missing.
"""

from shared_config.base import BaseServiceSettings
from shared_config.connector import (
    ConnectorServiceSettings,
    GitHubSettings,
    GoogleSettings,
    KeyringSettings,
    M365Settings,
    SlackSettings,
)
from shared_config.identity import IdentityServiceSettings

__all__ = [
    "BaseServiceSettings",
    "ConnectorServiceSettings",
    "GitHubSettings",
    "GoogleSettings",
    "IdentityServiceSettings",
    "KeyringSettings",
    "M365Settings",
    "SlackSettings",
]
