"""FastAPI routes for orchestrator service."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.gateway import (
    GatewayActionError,
    GatewayAuthError,
    GatewayManager,
    GatewayModeError,
    GatewayRateLimitError,
)
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.presentation import (
    PresentationError,
    PresentationManager,
    SlideOutOfRangeError,
)
from orchestrator.config import get_config, update_config
from orchestrator.webhook_dispatcher import WebhookDispatcher
from shared_personas import Persona
from shared_schemas.gateway.models import CommandStatus


# ------------------------------------------------------------------
# LLM config schemas
# ------------------------------------------------------------------

class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    openai_key_set: bool
    openrouter_key_set: bool
    gemini_key_set: bool


class LLMConfigUpdate(BaseModel):
    provider: Literal["openai", "openrouter", "gemini", "echo"]
    model: str = ""


class ModelOption(BaseModel):
    id: str
    name: str
    free: bool = False


# Simple in-memory cache: {provider: (timestamp, list[ModelOption])}
_models_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL = 300.0  # 5 minutes

router = APIRouter()
logger = logging.getLogger(__name__)

# Populated by main.py at startup
_router: IntentRouter | None = None
_approval_mgr: ApprovalManager | None = None
_context_builder: ContextBuilder | None = None
_persona_mgr: PersonaManager | None = None
_pipeline: OrchestratorPipeline | None = None
_presentation_mgr: PresentationManager | None = None
_gateway_mgr: GatewayManager | None = None
_webhook_dispatcher: WebhookDispatcher | None = None


def init(
    router_: IntentRouter,
    approval_mgr: ApprovalManager,
    context_builder: ContextBuilder,
    persona_mgr: PersonaManager,
    pipeline: OrchestratorPipeline,
    presentation_mgr: PresentationManager | None = None,
    gateway_mgr: GatewayManager | None = None,
    webhook_dispatcher: WebhookDispatcher | None = None,
) -> None:
    global _router, _approval_mgr, _context_builder, _persona_mgr, _pipeline
    global _presentation_mgr, _gateway_mgr, _webhook_dispatcher
    _router = router_
    _approval_mgr = approval_mgr
    _context_builder = context_builder
    _persona_mgr = persona_mgr
    _pipeline = pipeline
    _presentation_mgr = presentation_mgr
    _gateway_mgr = gateway_mgr
    _webhook_dispatcher = webhook_dispatcher


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "mode": _router.mode if _router else "unknown",
        "persona": str(_persona_mgr.current_persona) if _persona_mgr else "unknown",
    })


# ------------------------------------------------------------------
# LLM config
# ------------------------------------------------------------------


def _llm_config_response(cfg) -> LLMConfigResponse:
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        openai_key_set=bool(os.environ.get("OPENAI_API_KEY")),
        openrouter_key_set=bool(os.environ.get("OPENROUTER_API_KEY")),
        gemini_key_set=bool(os.environ.get("GEMINI_API_KEY")),
    )


@router.get("/orchestrator/config/llm", response_model=LLMConfigResponse)
async def get_llm_config() -> LLMConfigResponse:
    """Return the current runtime LLM provider and model."""
    return _llm_config_response(get_config())


@router.patch("/orchestrator/config/llm", response_model=LLMConfigResponse)
async def patch_llm_config(body: LLMConfigUpdate) -> LLMConfigResponse:
    """Update the runtime LLM provider and model without restarting."""
    model = body.model
    if not model:
        if body.provider == "openrouter":
            model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
        elif body.provider == "gemini":
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        elif body.provider == "echo":
            model = ""
        else:
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    cfg = update_config(body.provider, model)
    return _llm_config_response(cfg)


@router.get("/orchestrator/config/llm/models")
async def list_models(provider: str = Query(...)) -> JSONResponse:
    """Return available models for the given provider (cached 5 min)."""
    now = time.monotonic()
    cached = _models_cache.get(provider)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return JSONResponse({"provider": provider, "models": cached[1]})

    models: list[dict[str, Any]] = []

    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            return JSONResponse(
                {"error": "OPENROUTER_API_KEY not configured"},
                status_code=503,
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                data = resp.json()
            for m in data.get("data", []):
                mid = m.get("id", "")
                pricing = m.get("pricing", {})
                is_free = (
                    mid.endswith(":free")
                    or (str(pricing.get("prompt", "1")) == "0")
                )
                models.append({"id": mid, "name": m.get("name", mid), "free": is_free})
            models.sort(key=lambda x: (not x["free"], x["id"]))
        except Exception as exc:
            logger.warning("OpenRouter model list failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=502)

    elif provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return JSONResponse(
                {"error": "OPENAI_API_KEY not configured"},
                status_code=503,
            )
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=key)
            page = await client.models.list()
            chat_prefixes = ("gpt-", "o1", "o3", "o4")
            for m in page.data:
                if any(m.id.startswith(p) for p in chat_prefixes):
                    models.append({"id": m.id, "name": m.id, "free": False})
            models.sort(key=lambda x: x["id"])
        except Exception as exc:
            logger.warning("OpenAI model list failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=502)

    elif provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            return JSONResponse(
                {"error": "GEMINI_API_KEY not configured"},
                status_code=503,
            )
        try:
            from google import genai as google_genai
            gclient = google_genai.Client(api_key=key)
            result = await gclient.aio.models.list(config={"query_base": True})
            for m in result:
                mid = m.name or ""
                if "/" in mid:
                    mid = mid.split("/", 1)[1]
                if not mid.startswith("gemini"):
                    continue
                models.append({"id": mid, "name": m.display_name or mid, "free": False})
            models.sort(key=lambda x: x["id"])
        except Exception as exc:
            logger.warning("Gemini model list failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=502)

    elif provider == "echo":
        models = [{"id": "echo", "name": "Echo (test)", "free": True}]

    else:
        return JSONResponse({"error": f"Unknown provider: {provider}"}, status_code=422)

    _models_cache[provider] = (now, models)
    return JSONResponse({"provider": provider, "models": models})


# ------------------------------------------------------------------
# Turn (main pipeline entry)
# ------------------------------------------------------------------


@router.post("/orchestrator/turn")
async def process_turn(body: dict) -> JSONResponse:
    """Process a text turn through the full orchestrator pipeline."""
    assert _pipeline is not None
    text = body.get("text", "")
    session_id = body.get("session_id", "default")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=422)
    reply = await _pipeline.orchestrate(text, session_id)
    return JSONResponse({"session_id": session_id, "reply": reply})


# ------------------------------------------------------------------
# Mode
# ------------------------------------------------------------------


@router.post("/orchestrator/mode")
async def set_mode(body: dict) -> JSONResponse:
    assert _router is not None
    mode = body.get("mode", "")
    try:
        _router.set_mode(mode)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"mode": _router.mode})


# ------------------------------------------------------------------
# Persona
# ------------------------------------------------------------------


@router.post("/orchestrator/persona")
async def set_persona(body: dict) -> JSONResponse:
    assert _persona_mgr is not None
    persona_str = body.get("persona", "")
    try:
        cfg = _persona_mgr.switch(persona_str)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({"persona": cfg.name, "voice_style": cfg.voice_style})


# ------------------------------------------------------------------
# Context
# ------------------------------------------------------------------


@router.get("/orchestrator/context")
async def get_context() -> JSONResponse:
    assert _context_builder is not None
    assert _router is not None
    context = await _context_builder.build_context()
    tools = await _context_builder.build_tool_list(_router.allowed_tools())
    return JSONResponse({"context": context, "tools": tools})


# ------------------------------------------------------------------
# Approval
# ------------------------------------------------------------------


@router.post("/orchestrator/approval/{approval_id}/grant")
async def grant_approval(approval_id: str) -> JSONResponse:
    assert _approval_mgr is not None
    await _approval_mgr.grant(approval_id)
    return JSONResponse({"ok": True})


@router.post("/orchestrator/approval/{approval_id}/deny")
async def deny_approval(approval_id: str) -> JSONResponse:
    assert _approval_mgr is not None
    await _approval_mgr.deny(approval_id)
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Presentation
# ------------------------------------------------------------------


@router.post("/presentation/load")
async def load_presentation(body: dict) -> JSONResponse:
    """Load a YAML presentation script.

    Body: ``{"yaml": "<raw YAML string>"}``
    """
    if _presentation_mgr is None:
        return JSONResponse({"error": "presentation manager not initialised"}, status_code=503)
    raw = body.get("yaml", "")
    if not raw:
        return JSONResponse({"error": "yaml field is required"}, status_code=422)
    try:
        script = _presentation_mgr.load_from_yaml(raw)
        # Switch to presentation persona
        if _persona_mgr is not None:
            _persona_mgr.switch(Persona.PRESENTATION)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({
        "ok": True,
        "title": script.title,
        "slide_count": len(script.slides),
    })


@router.post("/presentation/slide/{slide_index}")
async def activate_slide(slide_index: int) -> JSONResponse:
    """Activate a slide cue by index (0-based)."""
    if _presentation_mgr is None:
        return JSONResponse({"error": "presentation manager not initialised"}, status_code=503)
    try:
        slide = await _presentation_mgr.activate_slide(slide_index)
    except SlideOutOfRangeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PresentationError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse({
        "slide_index": slide.slide_index,
        "speech_cue": slide.speech_cue,
        "motion_cue": slide.motion_cue,
    })


@router.delete("/presentation/session")
async def clear_presentation_session() -> JSONResponse:
    """End the active presentation session and revert persona."""
    if _presentation_mgr is None:
        return JSONResponse({"error": "presentation manager not initialised"}, status_code=503)
    _presentation_mgr.clear_session()
    # Revert to work persona
    if _persona_mgr is not None:
        _persona_mgr.switch(Persona.WORK)
    return JSONResponse({"ok": True})


@router.get("/presentation/script")
async def get_script() -> JSONResponse:
    """Return the currently loaded script."""
    if _presentation_mgr is None:
        return JSONResponse({"error": "presentation manager not initialised"}, status_code=503)
    if _presentation_mgr.script is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=404)
    return JSONResponse(_presentation_mgr.script.model_dump())


# ------------------------------------------------------------------
# Gateway — external agent commands (FR-001 to FR-009)
# ------------------------------------------------------------------


@router.post("/gateway/command")
async def gateway_command(body: dict, x_api_key: str = Header("")) -> JSONResponse:
    """Accept a command from an external agent (e.g. OpenClaw).

    Headers: ``X-Api-Key: <raw key>``
    Body: ``{"action": "speak", "payload": {...}, "priority": "normal"}``
    """
    if _gateway_mgr is None:
        return JSONResponse({"error": "gateway not initialised"}, status_code=503)

    current_mode = _router.mode.upper() if _router else "ONLINE"

    try:
        cmd, entry = _gateway_mgr.dispatch(
            raw_key=x_api_key,
            action_str=body.get("action", ""),
            payload=body.get("payload", {}),
            priority=body.get("priority", "normal"),
            current_mode=current_mode,
        )
    except GatewayAuthError:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    except GatewayRateLimitError as exc:
        return JSONResponse(
            {"error": "Rate limit exceeded", "retry_after": exc.retry_after},
            status_code=429,
            headers={"Retry-After": str(int(exc.retry_after) + 1)},
        )
    except GatewayModeError as exc:
        return JSONResponse(
            {"error": f"AURA is in {exc.mode} mode", "mode": exc.mode, "retry_after": exc.retry_after},
            status_code=503,
        )
    except GatewayActionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    # Check if action needs approval (FR-004)
    needs_approval = (
        _approval_mgr is not None and _approval_mgr.needs_approval(cmd.action)
    )
    if needs_approval:
        _gateway_mgr.update_audit_status(entry.entry_id, CommandStatus.APPROVED)

    _gateway_mgr.update_audit_status(entry.entry_id, CommandStatus.EXECUTED)
    return JSONResponse({
        "ok": True,
        "action": cmd.action,
        "entry_id": entry.entry_id,
        "needs_approval": needs_approval,
    })


@router.get("/gateway/audit")
async def gateway_audit(limit: int = 20) -> JSONResponse:
    """Return the last N gateway audit entries (FR-002)."""
    if _gateway_mgr is None:
        return JSONResponse({"error": "gateway not initialised"}, status_code=503)
    entries = _gateway_mgr.get_audit_log(limit=limit)
    return JSONResponse({
        "entries": [e.model_dump(mode="json") for e in entries],
        "count": len(entries),
    })


@router.post("/gateway/webhooks")
async def register_webhook(body: dict) -> JSONResponse:
    """Register a webhook callback URL (FR-003).

    Body: ``{"url": "https://...", "events": ["RobotModeChanged"]}``
    """
    if _webhook_dispatcher is None:
        return JSONResponse({"error": "webhook dispatcher not initialised"}, status_code=503)
    url = body.get("url", "")
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=422)
    events = body.get("events", [])
    try:
        reg = _webhook_dispatcher.register(url=url, events=events)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse({
        "ok": True,
        "webhook_id": reg.webhook_id,
        "url": reg.url,
        "events": reg.events,
    })


@router.get("/gateway/webhooks")
async def list_webhooks() -> JSONResponse:
    """List all registered webhooks."""
    if _webhook_dispatcher is None:
        return JSONResponse({"error": "webhook dispatcher not initialised"}, status_code=503)
    return JSONResponse({
        "webhooks": [w.model_dump(mode="json") for w in _webhook_dispatcher.list_webhooks()]
    })


