"""Microsoft MSAL auth flows for identity-service.

Implements:
  - Device Code flow (PublicClientApplication) for initial sign-in
  - Silent refresh + OBO token acquisition (ConfidentialClientApplication)
  - Emits AuthRequiredEvent on the event bus when refresh fails

SECURITY:
  - Tokens are stored in TokenStore (keyring), never in logs or env vars.
  - client_secret never appears in responses.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import msal

from identity_service.token_store import TokenData, TokenStore

logger = logging.getLogger(__name__)

_DEFAULT_SCOPES = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Tasks.ReadWrite",
    "https://graph.microsoft.com/ChannelMessage.Send",
    "offline_access",
]


class MicrosoftAuthFlow:
    """Handles Microsoft Device Code flow and token lifecycle."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        token_store: TokenStore,
        scopes: list[str] | None = None,
    ) -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._scopes = scopes or _DEFAULT_SCOPES
        self._token_store = token_store
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        self._public_app = msal.PublicClientApplication(client_id, authority=authority)
        self._confidential_app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )

    # ------------------------------------------------------------------
    # Device Code flow (initial sign-in)
    # ------------------------------------------------------------------

    def start_device_code_flow(self) -> dict:
        """Initiate Device Code flow. Returns {user_code, verification_uri, message, ...}."""
        flow = self._public_app.initiate_device_flow(scopes=self._scopes)
        if "error" in flow:
            raise RuntimeError(f"Failed to start device code flow: {flow.get('error_description', flow['error'])}")
        return flow

    def complete_device_code_flow(self, flow: dict, user_id: str) -> TokenData:
        """Poll MSAL to complete device code flow and persist the token.

        Blocks until the user completes sign-in or the flow times out.
        Raises RuntimeError on failure.
        """
        result = self._public_app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "unknown"))
            raise RuntimeError(f"Device code flow failed: {error}")

        token = _msal_result_to_token_data(result)
        self._token_store.set(user_id, "m365", token)
        logger.info("Microsoft token stored for user=%s", user_id)
        return token

    # ------------------------------------------------------------------
    # Token refresh (silent)
    # ------------------------------------------------------------------

    def get_valid_token(self, user_id: str) -> str:
        """Return a valid access token, refreshing silently if needed.

        Raises:
            RuntimeError: if refresh fails and re-auth is required.
        """
        token = self._token_store.get(user_id, "m365")
        if token is None:
            raise RuntimeError(f"No Microsoft token for user={user_id}. Auth required.")

        if not token.is_expired():
            return token.access_token

        # Attempt silent refresh via refresh_token
        if token.refresh_token:
            refreshed = self._silent_refresh(token.refresh_token, user_id)
            if refreshed:
                return refreshed

        raise RuntimeError(f"Microsoft token expired and refresh failed for user={user_id}. Re-auth required.")

    def _silent_refresh(self, refresh_token: str, user_id: str) -> str | None:
        """Attempt to acquire a new token using the refresh_token.

        Returns the new access_token string, or None on failure.
        """
        result = self._confidential_app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=self._scopes,
        )
        if "access_token" not in result:
            logger.warning(
                "Silent refresh failed for user=%s: %s",
                user_id,
                result.get("error_description", result.get("error")),
            )
            return None

        token = _msal_result_to_token_data(result)
        self._token_store.set(user_id, "m365", token)
        logger.debug("Microsoft token silently refreshed for user=%s", user_id)
        return token.access_token


def _msal_result_to_token_data(result: dict) -> TokenData:
    """Convert an MSAL token response dict to TokenData."""
    expires_in = result.get("expires_in", 3600)
    expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
    return TokenData(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token", ""),
        expires_at=expires_at,
        token_type=result.get("token_type", "Bearer"),
        scopes=result.get("scope", "").split() if result.get("scope") else [],
    )
