"""BaseServiceSettings — common fields shared by every AURA microservice."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Base class for all AURA service settings.

    Reads from environment variables and .env.local (never committed to VCS).
    """

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8000
    reload: bool = False
    cors_origins: str = "http://localhost:5173"
