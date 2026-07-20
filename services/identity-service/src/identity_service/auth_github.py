"""GitHub OAuth Device Code flow for identity-service.

Implements:
  - Device Code flow (no client_secret required)
  - Token storage in TokenStore

Endpoints used:
  - POST https://github.com/login/device/code  (start)
  - POST https://github.com/login/oauth/access_token  (poll)

SECURITY:
  - Tokens stored in TokenStore (keyring), never logged.
  - No client_secret needed for GitHub device flow.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from identity_service.token_store import TokenData, TokenStore

logger = logging.getLogger(__name__)

_DEFAULT_SCOPES = "repo read:org"

_DEVICE_CODE_URL = "https://github.com/login/device/code"
_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubDeviceCodeFlow:
    """Handles GitHub Device Code flow and token storage."""

    def __init__(
        self,
        client_id: str,
        token_store: TokenStore,
        scopes: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._scopes = scopes or _DEFAULT_SCOPES
        self._token_store = token_store

    def start_device_code_flow(self) -> dict:
        """Initiate Device Code flow.

        Returns:
            {
                "device_code": "...",
                "user_code": "ABCD-1234",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            }
        """
        resp = httpx.post(
            _DEVICE_CODE_URL,
            data={"client_id": self._client_id, "scope": self._scopes},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(
                f"GitHub device code error: {data.get('error_description', data['error'])}"
            )
        return data

    def poll_for_token(self, device_code: str, user_id: str) -> TokenData:
        """Exchange device_code for an access token.

        This should be called after the user has authorized at github.com/login/device.
        Returns TokenData on success.

        Raises:
            RuntimeError: if the flow is still pending, expired, or failed.
        """
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            error = data["error"]
            desc = data.get("error_description", error)
            if error == "authorization_pending":
                raise RuntimeError("authorization_pending")
            if error == "slow_down":
                raise RuntimeError("slow_down")
            if error == "expired_token":
                raise RuntimeError("Code expired — click Connect to try again.")
            if error == "access_denied":
                raise RuntimeError("Access denied — the user cancelled authorization.")
            raise RuntimeError(f"GitHub auth failed: {desc}")

        access_token = data.get("access_token", "")
        if not access_token:
            raise RuntimeError("No access_token in GitHub response.")

        # GitHub tokens don't expire (unless the user/org has configured token expiry)
        # Set a far-future expiry for consistency with other providers.
        token = TokenData(
            access_token=access_token,
            refresh_token="",
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            token_type=data.get("token_type", "bearer"),
            scopes=data.get("scope", "").split(",") if data.get("scope") else [],
        )
        self._token_store.set(user_id, "github", token)
        logger.info("GitHub token stored for user=%s", user_id)
        return token

    def get_valid_token(self, user_id: str) -> str:
        """Return the stored GitHub access token.

        GitHub tokens don't expire (for classic PATs / OAuth tokens).
        Raises RuntimeError if no token exists.
        """
        token = self._token_store.get(user_id, "github")
        if token is None:
            raise RuntimeError(f"No GitHub token for user={user_id}. Auth required.")
        return token.access_token
