"""Connector-service settings — M365, Google, GitHub, Slack, and keyring."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class _ConnectorBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class KeyringSettings(_ConnectorBase):
    """Controls which keyring backend is used for token storage.

    KEYRING_BACKEND options:
      - "auto"       Use OS native (Windows Credential Manager / macOS Keychain /
                     GNOME Keyring). Best for local installs.
      - "cryptfile"  Encrypted file backend for headless/Docker. Requires
                     KEYRING_PASSPHRASE to be set.
    """

    keyring_backend: Literal["auto", "cryptfile"] = "auto"
    keyring_passphrase: SecretStr = Field(
        default=SecretStr(""),
        description="Passphrase for cryptfile backend. Empty → OS native keyring.",
    )
    keyring_cryptfile_path: str = Field(
        default="/data/keyring.cfg",
        description="Path to the encrypted keyring file (cryptfile backend only).",
    )


class M365Settings(_ConnectorBase):
    """Azure Entra App Registration credentials for M365 / Work IQ MCP."""

    m365_connector: Literal["mock", "workiq"] = "mock"

    # Optional — only required when m365_connector == "workiq"
    azure_client_id: str = ""
    azure_client_secret: SecretStr = Field(default=SecretStr(""))
    azure_tenant_id: str = ""
    azure_sp_id: str = "ea9ffc3e-8a23-4a7d-836d-234d7c7565c1"

    # Managed at runtime by identity-service Device Code flow — not set manually
    m365_user_access_token: SecretStr = Field(
        default=SecretStr(""),
        description="Per-user OBO source token. Supplied by identity-service at runtime.",
    )


class GoogleSettings(_ConnectorBase):
    """Google OAuth 2.0 credentials for Calendar + Gmail."""

    google_client_secrets_file: str = Field(
        default="",
        description="Path to the client_secrets.json downloaded from Google Cloud Console.",
    )
    google_oauth_redirect_port: int = Field(
        default=8080,
        description="Local loopback port for Google OAuth callback.",
    )


class GitHubSettings(_ConnectorBase):
    """GitHub connector credentials."""

    github_token: SecretStr = Field(
        default=SecretStr(""),
        description="GitHub personal access token. Stored in OS keyring at runtime.",
    )


class SlackSettings(_ConnectorBase):
    """Slack connector credentials."""

    slack_bot_token: SecretStr = Field(
        default=SecretStr(""),
        description="Slack Bot Token (xoxb-...). Stored in OS keyring at runtime.",
    )


class ConnectorServiceSettings(
    KeyringSettings,
    M365Settings,
    GoogleSettings,
    GitHubSettings,
    SlackSettings,
):
    """Combined settings for the connector-service.

    Merges all connector credential groups plus service-level vars.
    """

    port: int = 8004
    reload: bool = False

    enabled_connectors: str = Field(
        default="m365",
        description="Comma-separated connector keys to activate (e.g. 'm365,google,github').",
    )
    identity_service_url: str = "http://identity-service:8006"

    @property
    def enabled_connector_list(self) -> list[str]:
        """Return parsed list of enabled connector keys."""
        return [k.strip() for k in self.enabled_connectors.split(",") if k.strip()]
