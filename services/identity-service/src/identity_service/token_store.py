"""TokenStore — abstract token storage with OS keyring and cryptfile backends.

Hierarchy:
    TokenStore (ABC)
    ├── KeyringTokenStore  — Windows Credential Manager / macOS Keychain / GNOME Keyring
    └── CryptfileTokenStore — keyrings.cryptfile encrypted file (Docker/headless)

Token data stored as JSON:
    {
        "access_token":  "<opaque>",
        "refresh_token": "<opaque>",   # may be absent for non-refreshable tokens
        "expires_at":    "<ISO-8601>", # UTC
        "token_type":    "Bearer",
        "scopes":        ["...", ...]
    }

SECURITY: tokens are never logged. keyring service name is namespaced to "aura".
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_SERVICE_NAME = "aura"
_REFRESH_MARGIN_SECONDS = 60  # refresh if < 60 s remain


class TokenData:
    """Parsed token envelope. Does not expose raw values in repr/str."""

    __slots__ = ("access_token", "refresh_token", "expires_at", "token_type", "scopes")

    def __init__(
        self,
        access_token: str,
        expires_at: datetime,
        refresh_token: str = "",
        token_type: str = "Bearer",
        scopes: list[str] | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_type = token_type
        self.scopes = scopes or []

    def is_expired(self, margin_seconds: int = _REFRESH_MARGIN_SECONDS) -> bool:
        return datetime.now(UTC) >= self.expires_at - timedelta(seconds=margin_seconds)

    def to_json(self) -> str:
        return json.dumps(
            {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at.isoformat(),
                "token_type": self.token_type,
                "scopes": self.scopes,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> TokenData:
        data = json.loads(raw)
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            token_type=data.get("token_type", "Bearer"),
            scopes=data.get("scopes", []),
        )

    def __repr__(self) -> str:
        return f"<TokenData provider=? expires_at={self.expires_at.isoformat()} expired={self.is_expired()}>"


class TokenStore(ABC):
    """Abstract token storage interface."""

    @abstractmethod
    def get(self, user_id: str, provider: str) -> TokenData | None:
        """Return stored token data, or None if not found."""

    @abstractmethod
    def set(self, user_id: str, provider: str, token: TokenData) -> None:
        """Persist token data for (user_id, provider)."""

    @abstractmethod
    def delete(self, user_id: str, provider: str) -> None:
        """Remove stored token for (user_id, provider). No-op if absent."""

    def _key(self, user_id: str, provider: str) -> str:
        """Derive keyring username key."""
        return f"{user_id}:{provider}"


class KeyringTokenStore(TokenStore):
    """Stores tokens in the OS native keyring.

    Backend priority (automatic):
      Windows → Windows Credential Manager
      macOS   → Keychain
      Linux   → GNOME Keyring / KDE Wallet / SecretService
    """

    def __init__(self) -> None:
        import keyring  # deferred — not available in all test environments
        self._kr = keyring

    def get(self, user_id: str, provider: str) -> TokenData | None:
        raw = self._kr.get_password(_SERVICE_NAME, self._key(user_id, provider))
        if raw is None:
            return None
        try:
            return TokenData.from_json(raw)
        except (KeyError, ValueError, json.JSONDecodeError):
            logger.warning("Corrupted token data for %s/%s — clearing.", user_id, provider)
            self.delete(user_id, provider)
            return None

    def set(self, user_id: str, provider: str, token: TokenData) -> None:
        self._kr.set_password(_SERVICE_NAME, self._key(user_id, provider), token.to_json())

    def delete(self, user_id: str, provider: str) -> None:
        try:
            self._kr.delete_password(_SERVICE_NAME, self._key(user_id, provider))
        except Exception:  # noqa: BLE001 — keyring raises backend-specific exceptions
            pass


class CryptfileTokenStore(TokenStore):
    """Stores tokens in an encrypted file (keyrings.cryptfile).

    Suitable for Docker / headless environments where no OS keyring daemon
    is available. Requires KEYRING_PASSPHRASE to be set (non-empty).
    """

    def __init__(self, passphrase: str, file_path: str = "/data/keyring.cfg") -> None:
        if not passphrase:
            raise ValueError(
                "CryptfileTokenStore requires a non-empty KEYRING_PASSPHRASE. "
                "Set KEYRING_BACKEND=auto to use the OS native keyring instead."
            )
        import keyring
        from keyrings.cryptfile.cryptfile import CryptFileKeyring  # type: ignore[import]

        kr = CryptFileKeyring()
        kr.file_path = file_path
        kr._keyring_key = passphrase  # noqa: SLF001 — library private attr
        keyring.set_keyring(kr)
        self._kr = keyring

    def get(self, user_id: str, provider: str) -> TokenData | None:
        raw = self._kr.get_password(_SERVICE_NAME, self._key(user_id, provider))
        if raw is None:
            return None
        try:
            return TokenData.from_json(raw)
        except (KeyError, ValueError, json.JSONDecodeError):
            logger.warning("Corrupted cryptfile token for %s/%s — clearing.", user_id, provider)
            self.delete(user_id, provider)
            return None

    def set(self, user_id: str, provider: str, token: TokenData) -> None:
        self._kr.set_password(_SERVICE_NAME, self._key(user_id, provider), token.to_json())

    def delete(self, user_id: str, provider: str) -> None:
        try:
            self._kr.delete_password(_SERVICE_NAME, self._key(user_id, provider))
        except Exception:  # noqa: BLE001
            pass


def build_token_store(
    backend: str = "auto",
    passphrase: str = "",
    cryptfile_path: str = "/data/keyring.cfg",
) -> TokenStore:
    """Factory — returns the appropriate TokenStore for the configured backend.

    Args:
        backend: "auto" (OS native keyring) or "cryptfile" (encrypted file).
        passphrase: Required when backend == "cryptfile".
        cryptfile_path: Path to the encrypted keyring file.
    """
    if backend == "cryptfile":
        return CryptfileTokenStore(passphrase=passphrase, file_path=cryptfile_path)
    return KeyringTokenStore()
