"""Google OAuth 2.0 Device Code flow for identity-service.

Replaces the previous InstalledAppFlow (which required a client_secrets.json
file mount). Device Code flow works headless — user signs in on any browser
at google.com/device with the displayed code.

Scopes requested:
  - calendar.readonly
  - gmail.readonly
  - gmail.send

Endpoints used:
  - POST https://oauth2.googleapis.com/device/code  (start)
  - POST https://oauth2.googleapis.com/token  (poll + refresh)

SECURITY: Tokens stored in TokenStore (keyring). Client credentials are
shipped as defaults for dev use (standard pattern). Never logged.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from identity_service.token_store import TokenData, TokenStore

logger = logging.getLogger(__name__)

_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.send"
)

_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleDeviceCodeFlow:
    """Handles Google Device Code flow and token lifecycle."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_store: TokenStore,
        scopes: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._scopes = scopes or _SCOPES
        self._token_store = token_store

    def start_device_code_flow(self) -> dict:
        """Initiate Device Code flow.

        Returns:
            {
                "device_code": "...",
                "user_code": "ABCD-EFGH",
                "verification_url": "https://www.google.com/device",
                "expires_in": 1800,
                "interval": 5,
            }
        """
        resp = httpx.post(
            _DEVICE_CODE_URL,
            data={"client_id": self._client_id, "scope": self._scopes},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(
                f"Google device code error: {data.get('error_description', data['error'])}"
            )
        return data

    def poll_for_token(self, device_code: str, user_id: str) -> TokenData:
        """Exchange device_code for tokens.

        Should be called after user has authorized at google.com/device.
        Returns TokenData on success.

        Raises:
            RuntimeError: if flow is pending, expired, or failed.
        """
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
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
            raise RuntimeError(f"Google auth failed: {desc}")

        access_token = data.get("access_token", "")
        if not access_token:
            raise RuntimeError("No access_token in Google response.")

        expires_in = data.get("expires_in", 3600)
        token = TokenData(
            access_token=access_token,
            refresh_token=data.get("refresh_token", ""),
            expires_at=datetime.now(UTC) + timedelta(seconds=int(expires_in)),
            token_type=data.get("token_type", "Bearer"),
            scopes=self._scopes.split(),
        )
        self._token_store.set(user_id, "google", token)
        logger.info("Google token stored for user=%s", user_id)
        return token

    def get_valid_token(self, user_id: str) -> str:
        """Return a valid access token, refreshing silently if needed.

        Raises:
            RuntimeError: if no token or refresh fails.
        """
        token = self._token_store.get(user_id, "google")
        if token is None:
            raise RuntimeError(f"No Google token for user={user_id}. Auth required.")

        if not token.is_expired():
            return token.access_token

        # Attempt refresh
        if token.refresh_token:
            refreshed = self._refresh(token.refresh_token, user_id)
            if refreshed:
                return refreshed

        raise RuntimeError(
            f"Google token expired and refresh failed for user={user_id}. Re-auth required."
        )

    def _refresh(self, refresh_token: str, user_id: str) -> str | None:
        """Refresh the access token using the refresh_token.

        Returns new access_token string, or None on failure.
        """
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        data = resp.json()

        if "access_token" not in data:
            logger.warning(
                "Google refresh failed for user=%s: %s",
                user_id,
                data.get("error_description", data.get("error")),
            )
            return None

        expires_in = data.get("expires_in", 3600)
        token = TokenData(
            access_token=data["access_token"],
            refresh_token=refresh_token,  # Google doesn't rotate refresh tokens
            expires_at=datetime.now(UTC) + timedelta(seconds=int(expires_in)),
            token_type=data.get("token_type", "Bearer"),
            scopes=self._scopes.split(),
        )
        self._token_store.set(user_id, "google", token)
        logger.debug("Google token refreshed for user=%s", user_id)
        return token.access_token


def _credentials_to_token_data(creds: object) -> TokenData:
    """Convert google-auth Credentials to TokenData."""
    expiry: datetime | None = getattr(creds, "expiry", None)
    if expiry is None:
        expires_at = datetime.now(UTC) + timedelta(hours=1)
    elif expiry.tzinfo is None:
        expires_at = expiry.replace(tzinfo=UTC)
    else:
        expires_at = expiry

    return TokenData(
        access_token=creds.token,  # type: ignore[attr-defined]
        refresh_token=creds.refresh_token or "",  # type: ignore[attr-defined]
        expires_at=expires_at,
        token_type="Bearer",
        scopes=list(getattr(creds, "scopes", []) or []),
    )
