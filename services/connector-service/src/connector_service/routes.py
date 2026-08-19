"""FastAPI routes for connector-service."""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from shared_schemas.m365.connector import M365Connector

from connector_service import connector_prefs, connector_state
from connector_service.registry import ConnectorRegistry

router = APIRouter(prefix="/connector")
logger = logging.getLogger(__name__)

_connector: M365Connector | None = None
_registry: ConnectorRegistry | None = None


# U254: the brain registers a callback here so that switching a connector on
# updates the tool policy in the same request. Without it the console would
# say "connected" while the assistant still refused to read mail until the
# next restart — the exact gap between a badge and a capability.
_on_change: Callable[[], None] | None = None


def set_on_change(callback: Callable[[], None] | None) -> None:
    global _on_change
    _on_change = callback


def _notify_change() -> None:
    if _on_change is None:
        return
    try:
        _on_change()
    except Exception as exc:  # noqa: BLE001 — a listener must not break the call
        logger.warning("connector change listener failed: %s", exc)


def set_connector(connector: M365Connector) -> None:
    global _connector
    _connector = connector


def set_registry(registry: ConnectorRegistry) -> None:
    global _registry
    _registry = registry


def _require_connector() -> M365Connector:
    if _connector is None:
        raise HTTPException(
            status_code=503,
            detail="No connector available. Complete authentication at POST /identity/auth/microsoft/start.",
        )
    return _connector


# ------------------------------------------------------------------
# Health — now includes per-connector status from registry
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> JSONResponse:
    connectors: dict[str, str] = {} if _registry is None else dict(_registry.health())
    # U52: honest statuses — music runs on canned data without a Spotify token.
    connectors["music"] = "mock" if _music.mock else "ok"
    # U254: the flat map only ever contained connectors that were BUILT, so a
    # switched-off Google was simply absent and the console rendered "unknown"
    # — a word the owner can do nothing with. `details` describes every
    # connector AURA knows how to speak, including the off ones, each with its
    # own next step. The flat map stays for older consoles.
    infos = connector_state.describe(registry=_registry,
                                     enabled=connector_prefs.enabled_keys())
    for info in infos:
        connectors.setdefault(info.key, info.status)
    return JSONResponse({
        "status": "ok" if _registry is None else _registry.overall_status(),
        "connectors": connectors,
        "details": [i.as_dict() for i in infos],
        "live_domains": sorted(connector_state.live_domains(infos)),
    })


@router.post("/enable/{key}")
async def enable_connector(key: str, body: dict | None = None) -> JSONResponse:
    """Switch a connector on or off and rebuild, without a restart.

    U254: enabling used to mean editing ENABLED_CONNECTORS in a generated env
    file. The registry is rebuilt here so the very next question can use it —
    a setting that needs a restart to take effect gets read as broken.
    """
    enabled = True if body is None else bool(body.get("enabled", True))
    try:
        connector_prefs.set_enabled(key, enabled)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    if _registry is not None:
        _registry.build()
        primary = _registry.get_primary_m365()
        if primary is not None:
            set_connector(primary)
    _notify_change()
    infos = connector_state.describe(registry=_registry,
                                     enabled=connector_prefs.enabled_keys())
    return JSONResponse({
        "key": key, "enabled": enabled,
        "details": [i.as_dict() for i in infos],
    })


@router.post("/test/{key}")
async def test_connector(key: str) -> JSONResponse:
    """U52: per-connector probe — one cheap real call so the owner can verify a
    connection actually works (instead of trusting a green badge)."""
    try:
        if key == "music":
            return JSONResponse({"key": key, "ok": not _music.mock,
                                 "detail": await _music.list_devices()})
        if _registry is None:
            return JSONResponse({"key": key, "ok": False, "detail": "no registry"}, status_code=503)
        connector = _registry.get(key)
        if connector is None:
            return JSONResponse({"key": key, "ok": False,
                                 "detail": "not connected — authenticate first"})
        is_mock = getattr(connector, "is_mock", False) or type(connector).__name__.startswith("Mock")
        events = await connector.list_calendar_events_today()
        detail = f"reachable — {len(events)} calendar event(s) today"
        if is_mock:
            detail += " (MOCK data, not a real account)"
        return JSONResponse({"key": key, "ok": not is_mock, "detail": detail})
    except Exception as exc:  # noqa: BLE001 — a probe must report, not 500
        return JSONResponse({"key": key, "ok": False, "detail": f"probe failed: {exc}"})


# ------------------------------------------------------------------
# Calendar
# ------------------------------------------------------------------


@router.get("/calendar/today")
async def calendar_today() -> JSONResponse:
    events = await _require_connector().list_calendar_events_today()
    return JSONResponse([e.model_dump(mode="json") for e in events])


# ------------------------------------------------------------------
# Mail
# ------------------------------------------------------------------


@router.get("/mail/unread")
async def unread_mail(limit: int = 10) -> JSONResponse:
    items = await _require_connector().get_unread_mail(limit=limit)
    return JSONResponse([m.model_dump(mode="json") for m in items])


@router.post("/mail/send")
async def send_mail(body: dict) -> JSONResponse:
    await _require_connector().send_mail(
        to=body["to"],
        subject=body["subject"],
        body=body["body"],
    )
    return JSONResponse({"ok": True})


@router.post("/teams/message")
async def post_teams_message(body: dict) -> JSONResponse:
    msg = await _require_connector().post_teams_message(
        channel=body["channel"],
        content=body["content"],
    )
    return JSONResponse(msg.model_dump(mode="json"))


# ------------------------------------------------------------------
# OneDrive / files
# ------------------------------------------------------------------


@router.get("/onedrive/files")
async def onedrive_files() -> JSONResponse:
    connector = _require_connector()
    lister = getattr(connector, "list_onedrive_files", None)
    if lister is None:
        return JSONResponse(
            {"note": "This connector does not expose OneDrive files yet."},
        )
    files = await lister()
    return JSONResponse(files)


# ------------------------------------------------------------------
# Music (Spotify + Sonos via Spotify Connect, U39)
# ------------------------------------------------------------------

from connector_service.music import SpotifyMusic  # noqa: E402

_music = SpotifyMusic()


@router.get("/music/devices")
async def music_devices() -> JSONResponse:
    return JSONResponse({"result": await _music.list_devices()})


@router.get("/music/playlists")
async def music_playlists() -> JSONResponse:
    return JSONResponse({"result": await _music.list_playlists()})


@router.post("/music/play")
async def music_play(body: dict) -> JSONResponse:
    return JSONResponse({"result": await _music.play(
        query=body.get("query"),
        playlist=body.get("playlist"),
        favorites=bool(body.get("favorites", False)),
        device=body.get("device"),
    )})


@router.post("/music/pause")
async def music_pause() -> JSONResponse:
    return JSONResponse({"result": await _music.pause()})


@router.post("/music/next")
async def music_next() -> JSONResponse:
    return JSONResponse({"result": await _music.next_track()})


# ------------------------------------------------------------------
# Tasks
# ------------------------------------------------------------------


@router.get("/tasks")
async def list_tasks(plan_id: str = "") -> JSONResponse:
    tasks = await _require_connector().list_tasks(plan_id=plan_id)
    return JSONResponse([t.model_dump(mode="json") for t in tasks])


@router.post("/tasks")
async def create_task(body: dict) -> JSONResponse:
    task = await _require_connector().create_task(
        title=body["title"],
        plan_id=body.get("plan_id", ""),
        due_date=body.get("due_date", ""),
    )
    return JSONResponse(task.model_dump(mode="json"))



# ------------------------------------------------------------------
# Browser (U52: Chrome via CDP — read free, navigate approval-gated)
# ------------------------------------------------------------------

from connector_service.browser import ChromeBrowser  # noqa: E402

_browser = ChromeBrowser()


@router.get("/browser/tabs")
async def browser_tabs() -> JSONResponse:
    return JSONResponse({"result": await _browser.list_tabs()})


@router.post("/browser/open")
async def browser_open(body: dict) -> JSONResponse:
    return JSONResponse({"result": await _browser.open_url(str(body.get("url", "")))})
