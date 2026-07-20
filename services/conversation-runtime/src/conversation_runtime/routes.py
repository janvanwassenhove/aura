"""FastAPI routes for conversation-runtime service."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from shared_events.bus import AsyncEventBus
from shared_schemas.events.audio import TranscriptUpdated
from shared_schemas.events.conversation import ResponseDrafted
from shared_schemas.voice.providers import STTProvider, TTSProvider

from conversation_runtime.session_manager import SessionManager

router = APIRouter()
logger = logging.getLogger(__name__)

_stt: STTProvider | None = None
_tts: TTSProvider | None = None
_bus: AsyncEventBus | None = None
_sessions: SessionManager | None = None
_orchestrator_url: str = "http://orchestrator:8003"
_memory_url: str = "http://memory-service:8005"
# When set (aura-brain), orchestrator + memory calls go in-process via this
# client's ASGI transport instead of over HTTP (Phase 1 seam, U9).
_inproc_client: httpx.AsyncClient | None = None


def init(
    stt: STTProvider,
    tts: TTSProvider,
    bus: AsyncEventBus,
    sessions: SessionManager,
    *,
    orchestrator_url: str = "http://orchestrator:8003",
    memory_url: str = "http://memory-service:8005",
    inproc_client: httpx.AsyncClient | None = None,
) -> None:
    global _stt, _tts, _bus, _sessions, _orchestrator_url, _memory_url, _inproc_client
    _stt = stt
    _tts = tts
    _bus = bus
    _sessions = sessions
    _orchestrator_url = orchestrator_url
    _memory_url = memory_url
    _inproc_client = inproc_client


async def _call_orchestrator(text: str, session_id: str) -> str:
    """Forward turn to orchestrator; fall back to echo on connection error."""
    payload = {"text": text, "session_id": session_id}
    try:
        if _inproc_client is not None:
            resp = await _inproc_client.post("/orchestrator/turn", json=payload)
            resp.raise_for_status()
            return resp.json().get("reply", text)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{_orchestrator_url}/orchestrator/turn", json=payload)
            resp.raise_for_status()
            return resp.json().get("reply", text)
    except Exception as exc:
        logger.warning("Orchestrator unavailable (%s); using echo fallback", exc)
        return f"[echo] {text}"


async def _persist_turn(session_id: str, role: str, content: str) -> None:
    """Best-effort persist turn to memory-service."""
    payload = {"session_id": session_id, "role": role, "content": content}
    try:
        if _inproc_client is not None:
            await _inproc_client.post("/memory/turns", json=payload)
            return
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{_memory_url}/memory/turns", json=payload)
    except Exception as exc:
        logger.debug("Turn persistence skipped: %s", exc)


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "active_sessions": _sessions.active_count() if _sessions else 0,
    })


# ------------------------------------------------------------------
# Session
# ------------------------------------------------------------------


@router.post("/conversation/sessions")
async def create_session() -> JSONResponse:
    assert _sessions is not None
    session = _sessions.create()
    return JSONResponse({"session_id": session.session_id})


@router.delete("/conversation/sessions/{session_id}")
async def end_session(session_id: str) -> JSONResponse:
    assert _sessions is not None
    _sessions.end(session_id)
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Text turn (no audio)
# ------------------------------------------------------------------


@router.post("/conversation/turn")
async def text_turn(body: dict) -> JSONResponse:
    """Process a text-only turn; returns assistant reply as text."""
    assert _sessions is not None
    assert _bus is not None

    session_id = body.get("session_id", "default")
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=422)

    _sessions.touch(session_id)

    await _bus.publish(
        TranscriptUpdated(session_id=session_id, transcript=text, is_final=True)
    )

    reply = await _call_orchestrator(text, session_id)

    await _bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))

    # Persist both turns (best-effort)
    await _persist_turn(session_id, "user", text)
    await _persist_turn(session_id, "assistant", reply)

    return JSONResponse({"session_id": session_id, "reply": reply})


# ------------------------------------------------------------------
# Audio WebSocket turn
# ------------------------------------------------------------------


@router.websocket("/conversation/audio/{session_id}")
async def audio_turn(websocket: WebSocket, session_id: str) -> None:
    assert _stt is not None
    assert _tts is not None
    assert _bus is not None
    assert _sessions is not None

    await websocket.accept()
    _sessions.get_or_create(session_id)

    try:
        while True:
            raw = await websocket.receive_bytes()
            transcript = await _stt.transcribe(raw)
            _sessions.touch(session_id)

            await _bus.publish(
                TranscriptUpdated(session_id=session_id, transcript=transcript, is_final=True)
            )

            reply = await _call_orchestrator(transcript, session_id)

            await _bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))

            await _persist_turn(session_id, "user", transcript)
            await _persist_turn(session_id, "assistant", reply)

            audio = await _tts.synthesize(reply)
            await websocket.send_bytes(audio)

    except WebSocketDisconnect:
        pass
    finally:
        _sessions.end(session_id)
