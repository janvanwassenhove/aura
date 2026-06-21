"""Identity-service settings."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdentityServiceSettings(BaseSettings):
    """Settings for the identity-service."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8006
    reload: bool = False
    active_persona: str = "work"

    # Keyring
    keyring_backend: Literal["auto", "cryptfile"] = "auto"
    keyring_passphrase: SecretStr = Field(default=SecretStr(""))
    keyring_cryptfile_path: str = "/data/keyring.cfg"

    # Microsoft Device Code flow app registration
    azure_client_id: str = ""
    azure_client_secret: SecretStr = Field(default=SecretStr(""))
    azure_tenant_id: str = ""
    azure_sp_id: str = "ea9ffc3e-8a23-4a7d-836d-234d7c7565c1"

    # Google OAuth
    google_client_secrets_file: str = ""
    google_oauth_redirect_port: int = 8080
    google_client_id: str = ""
    google_client_secret: SecretStr = Field(default=SecretStr(""))

    # GitHub OAuth (Device Code flow)
    github_client_id: str = ""
