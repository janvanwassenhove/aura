"""identity-service FastAPI application.

Responsibilities:
  - Persona state management
  - OAuth token storage and retrieval (OS keyring)
  - Microsoft Device Code flow
  - Google Device Code flow
  - GitHub Device Code flow
  - Per-user token endpoint for connector-service

SECURITY: No token values are returned in API responses. Tokens are stored
exclusively in the OS keyring (or encrypted cryptfile for Docker). Credentials
(client_secret, passphrase) are never logged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared_personas import Persona, get_persona_config
from shared_config import IdentityServiceSettings
from identity_service.token_store import TokenStore, build_token_store
from identity_service import defaults

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

_settings = IdentityServiceSettings()
_token_store: TokenStore = build_token_store(
    backend=_settings.keyring_backend,
    passphrase=_settings.keyring_passphrase.get_secret_value(),
    cryptfile_path=_settings.keyring_cryptfile_path,
)

# Routes live on an APIRouter so the identity module can be mounted into the
# unified aura-brain process (Phase 1) as well as run standalone (create_app).
router = APIRouter()

_active_persona = Persona(_settings.active_persona)

# In-progress Device Code flows keyed by a server-generated flow_id
_pending_ms_flows: dict[str, dict] = {}
_pending_google_flows: dict[str, dict] = {}
_pending_github_flows: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Auth helpers — use env vars if set, otherwise shipped defaults
# ---------------------------------------------------------------------------

def _get_ms_client_id() -> str:
    return _settings.azure_client_id or defaults.MICROSOFT_CLIENT_ID

def _get_ms_tenant_id() -> str:
    return _settings.azure_tenant_id or defaults.MICROSOFT_TENANT_ID

def _get_ms_client_secret() -> str:
    s = _settings.azure_client_secret.get_secret_value()
    return s or defaults.MICROSOFT_CLIENT_SECRET

def _get_google_client_id() -> str:
    return _settings.google_client_id or defaults.GOOGLE_CLIENT_ID

def _get_google_client_secret() -> str:
    s = _settings.google_client_secret.get_secret_value()
    return s or defaults.GOOGLE_CLIENT_SECRET

def _get_github_client_id() -> str:
    return _settings.github_client_id or defaults.GITHUB_CLIENT_ID


def _ms_flow() -> object:
    """Return a MicrosoftAuthFlow using env vars or shipped defaults."""
    client_id = _get_ms_client_id()
    tenant_id = _get_ms_tenant_id()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="Microsoft OAuth app not configured. Set AZURE_CLIENT_ID or register the default AURA dev app.",
        )
    from identity_service.auth_microsoft import MicrosoftAuthFlow
    return MicrosoftAuthFlow(
        client_id=client_id,
        client_secret=_get_ms_client_secret(),
        tenant_id=tenant_id,
        token_store=_token_store,
    )


def _google_flow() -> object:
    """Return a GoogleDeviceCodeFlow using env vars or shipped defaults."""
    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth app not configured. Set GOOGLE_CLIENT_ID or register the default AURA dev app.",
        )
    from identity_service.auth_google import GoogleDeviceCodeFlow
    return GoogleDeviceCodeFlow(
        client_id=client_id,
        client_secret=client_secret,
        token_store=_token_store,
    )


def _github_flow() -> object:
    """Return a GitHubDeviceCodeFlow using env vars or shipped defaults."""
    client_id = _get_github_client_id()
    if not client_id:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth app not configured. Set GITHUB_CLIENT_ID or register the default AURA dev app.",
        )
    from identity_service.auth_github import GitHubDeviceCodeFlow
    return GitHubDeviceCodeFlow(
        client_id=client_id,
        token_store=_token_store,
    )


# ---------------------------------------------------------------------------
# In-process token access (Phase 1 seam — used by aura-brain instead of HTTP)
# ---------------------------------------------------------------------------

async def get_valid_token(user_id: str, provider: str) -> str | None:
    """Return a valid access token for (user_id, provider), or None.

    The in-process equivalent of GET /identity/token/{user_id}/{provider}: used by
    the connector module when both run inside aura-brain, avoiding an HTTP hop.
    Returns None (instead of raising) when unconfigured or no token — the caller
    decides how to surface that.
    """
    try:
        if provider == "m365":
            return _ms_flow().get_valid_token(user_id)  # type: ignore[union-attr]
        if provider == "google":
            return _google_flow().get_valid_token(user_id)  # type: ignore[union-attr]
        if provider == "github":
            return _github_flow().get_valid_token(user_id)  # type: ignore[union-attr]
        token_data = _token_store.get(user_id, provider)
        return token_data.access_token if token_data is not None else None
    except (HTTPException, RuntimeError):
        return None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

@router.get("/identity/persona")
async def get_persona() -> JSONResponse:
    cfg = get_persona_config(_active_persona)
    # Report which providers have stored (possibly expired) tokens for the active user.
    # We use "default" as the user_id until multi-user session management is built.
    authenticated: list[str] = []
    for provider in ("m365", "google", "github", "slack"):
        if _token_store.get("default", provider) is not None:
            authenticated.append(provider)
    return JSONResponse({
        "persona": cfg.name,
        "voice_style": cfg.voice_style,
        "authenticated_providers": authenticated,
    })


@router.post("/identity/persona")
async def set_persona(body: dict) -> JSONResponse:
    global _active_persona
    try:
        _active_persona = Persona(body.get("persona", "work"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    cfg = get_persona_config(_active_persona)
    return JSONResponse({"persona": cfg.name})


# ---------------------------------------------------------------------------
# Token endpoint (for connector-service)
# ---------------------------------------------------------------------------

@router.get("/identity/token/{user_id}/{provider}")
async def get_token(user_id: str, provider: str) -> JSONResponse:
    """Return a valid access token for (user_id, provider).

    Performs silent refresh if the stored token is near expiry.
    Returns 401 if no token exists or refresh fails (caller should trigger re-auth).

    SECURITY: only the access_token is returned; refresh_token is never exposed.
    """
    if provider == "m365":
        try:
            flow = _ms_flow()
            token = flow.get_valid_token(user_id)  # type: ignore[union-attr]
            return JSONResponse({"access_token": token, "provider": provider})
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    if provider == "google":
        try:
            flow = _google_flow()
            token = flow.get_valid_token(user_id)  # type: ignore[union-attr]
            return JSONResponse({"access_token": token, "provider": provider})
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    if provider == "github":
        try:
            flow = _github_flow()
            token = flow.get_valid_token(user_id)  # type: ignore[union-attr]
            return JSONResponse({"access_token": token, "provider": provider})
        except HTTPException:
            raise
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    # For simple API-key providers (slack) — return raw stored token
    token_data = _token_store.get(user_id, provider)
    if token_data is None:
        raise HTTPException(status_code=401, detail=f"No token for provider={provider!r}. Auth required.")
    return JSONResponse({"access_token": token_data.access_token, "provider": provider})


# ---------------------------------------------------------------------------
# Microsoft Device Code flow
# ---------------------------------------------------------------------------

@router.post("/identity/auth/microsoft/start")
async def microsoft_auth_start(body: dict) -> JSONResponse:
    """Start Microsoft Device Code flow.

    Request body: {"user_id": "alice"}  (optional, defaults to "default")

    Returns:
        {
            "user_code": "ABCD-1234",
            "verification_uri": "https://microsoft.com/devicelogin",
            "message": "Go to https://microsoft.com/devicelogin and enter ABCD-1234",
            "flow_id": "<server-side flow handle>"
        }

    Reachy should speak 'message' aloud to guide the user.
    """
    user_id = body.get("user_id", "default")
    flow_obj = _ms_flow()
    flow_data = flow_obj.start_device_code_flow()  # type: ignore[union-attr]
    # Store the MSAL flow dict under a server-side key so /poll can retrieve it
    flow_id = f"ms-{user_id}-{id(flow_data)}"
    _pending_ms_flows[flow_id] = {"flow": flow_data, "user_id": user_id}
    return JSONResponse({
        "user_code": flow_data.get("user_code"),
        "verification_uri": flow_data.get("verification_uri"),
        "message": flow_data.get("message"),
        "expires_in": flow_data.get("expires_in"),
        "flow_id": flow_id,
    })


@router.post("/identity/auth/microsoft/poll")
async def microsoft_auth_poll(body: dict) -> JSONResponse:
    """Complete a Device Code flow previously started via /start.

    Request body: {"flow_id": "<id from /start>"}

    Blocks (up to the flow's expires_in) until the user authenticates.
    Returns 200 on success, 408 on timeout, 401 on denial/error.
    """
    flow_id = body.get("flow_id", "")
    pending = _pending_ms_flows.pop(flow_id, None)
    if pending is None:
        raise HTTPException(status_code=404, detail=f"Unknown flow_id: {flow_id!r}")

    flow_obj = _ms_flow()
    try:
        # Run blocking MSAL poll in a thread pool to avoid blocking the event loop
        token_data = await asyncio.get_event_loop().run_in_executor(
            None,
            flow_obj.complete_device_code_flow,  # type: ignore[union-attr]
            pending["flow"],
            pending["user_id"],
        )
        _ = token_data  # stored in keyring inside complete_device_code_flow
        return JSONResponse({"status": "authenticated", "provider": "m365", "user_id": pending["user_id"]})
    except RuntimeError as exc:
        msg = str(exc)
        if "expired" in msg.lower() or "timeout" in msg.lower():
            raise HTTPException(status_code=408, detail=msg) from exc
        raise HTTPException(status_code=401, detail=msg) from exc


# ---------------------------------------------------------------------------
# Google Device Code flow
# ---------------------------------------------------------------------------

@router.post("/identity/auth/google/start")
async def google_auth_start(body: dict) -> JSONResponse:
    """Start Google Device Code flow.

    Request body: {"user_id": "alice"}  (optional, defaults to "default")

    Returns:
        {
            "user_code": "ABCD-EFGH",
            "verification_url": "https://www.google.com/device",
            "expires_in": 1800,
            "flow_id": "<server-side flow handle>"
        }
    """
    user_id = body.get("user_id", "default")
    flow_obj = _google_flow()
    flow_data = flow_obj.start_device_code_flow()  # type: ignore[union-attr]
    flow_id = f"google-{user_id}-{id(flow_data)}"
    _pending_google_flows[flow_id] = {
        "device_code": flow_data.get("device_code"),
        "user_id": user_id,
    }
    return JSONResponse({
        "user_code": flow_data.get("user_code"),
        "verification_url": flow_data.get("verification_url"),
        "expires_in": flow_data.get("expires_in"),
        "interval": flow_data.get("interval", 5),
        "flow_id": flow_id,
    })


@router.post("/identity/auth/google/poll")
async def google_auth_poll(body: dict) -> JSONResponse:
    """Complete a Google Device Code flow previously started via /start.

    Request body: {"flow_id": "<id from /start>"}

    Returns 200 on success, 202 if still pending, 408 on timeout, 401 on error.
    """
    flow_id = body.get("flow_id", "")
    pending = _pending_google_flows.get(flow_id)
    if pending is None:
        raise HTTPException(status_code=404, detail=f"Unknown flow_id: {flow_id!r}")

    flow_obj = _google_flow()
    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            flow_obj.poll_for_token,  # type: ignore[union-attr]
            pending["device_code"],
            pending["user_id"],
        )
        _pending_google_flows.pop(flow_id, None)
        return JSONResponse({"status": "authenticated", "provider": "google", "user_id": pending["user_id"]})
    except RuntimeError as exc:
        msg = str(exc)
        if "authorization_pending" in msg or "slow_down" in msg:
            raise HTTPException(status_code=202, detail="Authorization pending — user has not yet signed in.")
        if "expired" in msg.lower():
            _pending_google_flows.pop(flow_id, None)
            raise HTTPException(status_code=408, detail=msg) from exc
        _pending_google_flows.pop(flow_id, None)
        raise HTTPException(status_code=401, detail=msg) from exc


# ---------------------------------------------------------------------------
# GitHub Device Code flow
# ---------------------------------------------------------------------------

@router.post("/identity/auth/github/start")
async def github_auth_start(body: dict) -> JSONResponse:
    """Start GitHub Device Code flow.

    Request body: {"user_id": "alice"}  (optional, defaults to "default")

    Returns:
        {
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "flow_id": "<server-side flow handle>"
        }
    """
    user_id = body.get("user_id", "default")
    flow_obj = _github_flow()
    flow_data = flow_obj.start_device_code_flow()  # type: ignore[union-attr]
    flow_id = f"github-{user_id}-{id(flow_data)}"
    _pending_github_flows[flow_id] = {
        "device_code": flow_data.get("device_code"),
        "user_id": user_id,
    }
    return JSONResponse({
        "user_code": flow_data.get("user_code"),
        "verification_uri": flow_data.get("verification_uri"),
        "expires_in": flow_data.get("expires_in"),
        "interval": flow_data.get("interval", 5),
        "flow_id": flow_id,
    })


@router.post("/identity/auth/github/poll")
async def github_auth_poll(body: dict) -> JSONResponse:
    """Complete a GitHub Device Code flow previously started via /start.

    Request body: {"flow_id": "<id from /start>"}

    Returns 200 on success, 202 if still pending, 408 on timeout, 401 on error.
    """
    flow_id = body.get("flow_id", "")
    pending = _pending_github_flows.get(flow_id)
    if pending is None:
        raise HTTPException(status_code=404, detail=f"Unknown flow_id: {flow_id!r}")

    flow_obj = _github_flow()
    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            flow_obj.poll_for_token,  # type: ignore[union-attr]
            pending["device_code"],
            pending["user_id"],
        )
        _pending_github_flows.pop(flow_id, None)
        return JSONResponse({"status": "authenticated", "provider": "github", "user_id": pending["user_id"]})
    except RuntimeError as exc:
        msg = str(exc)
        if "authorization_pending" in msg or "slow_down" in msg:
            raise HTTPException(status_code=202, detail="Authorization pending — user has not yet signed in.")
        if "expired" in msg.lower():
            _pending_github_flows.pop(flow_id, None)
            raise HTTPException(status_code=408, detail=msg) from exc
        _pending_github_flows.pop(flow_id, None)
        raise HTTPException(status_code=401, detail=msg) from exc


# ---------------------------------------------------------------------------
# Generic token management (GitHub, Slack — simple API-key storage)
# ---------------------------------------------------------------------------

@router.put("/identity/token/{user_id}/{provider}")
async def store_token(user_id: str, provider: str, body: dict) -> JSONResponse:
    """Store an API key / token for a simple provider (e.g. github, slack).

    Request body: {"access_token": "<value>"}

    SECURITY: tokens are persisted to OS keyring only — never returned in responses.
    """
    access_token = body.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=422, detail="access_token must not be empty.")

    from identity_service.token_store import TokenData

    token = TokenData(
        access_token=access_token,
        expires_at=datetime.now(UTC) + timedelta(days=365),  # effectively non-expiring
    )
    _token_store.set(user_id, provider, token)
    return JSONResponse({"status": "stored", "provider": provider, "user_id": user_id})


@router.delete("/identity/token/{user_id}/{provider}")
async def revoke_token(user_id: str, provider: str) -> JSONResponse:
    """Remove stored token for (user_id, provider)."""
    _token_store.delete(user_id, provider)
    return JSONResponse({"status": "revoked", "provider": provider, "user_id": user_id})


# ---------------------------------------------------------------------------
# Provider configuration status
# ---------------------------------------------------------------------------

@router.get("/identity/config")
async def get_config() -> JSONResponse:
    """Report which OAuth providers are ready (have client_ids configured).

    SECURITY: No secrets are returned — only boolean readiness and non-secret identifiers.
    """
    return JSONResponse({
        "microsoft": {
            "ready": bool(_get_ms_client_id()),
            "client_id": _get_ms_client_id()[:8] + "…" if _get_ms_client_id() else None,
        },
        "google": {
            "ready": bool(_get_google_client_id()),
            "client_id": _get_google_client_id()[:8] + "…" if _get_google_client_id() else None,
        },
        "github": {
            "ready": bool(_get_github_client_id()),
            "client_id": _get_github_client_id()[:8] + "…" if _get_github_client_id() else None,
        },
        "slack": {
            "ready": True,  # Slack always accepts token paste — no OAuth app needed
        },
    })


# ---------------------------------------------------------------------------
# Application factory (standalone) — the brain mounts `router` directly instead
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="AURA Identity Service", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def run() -> None:
    import uvicorn
    uvicorn.run(
        "identity_service.main:app",
        host="0.0.0.0",
        port=_settings.port,
        reload=_settings.reload,
    )

