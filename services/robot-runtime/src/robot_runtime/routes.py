"""FastAPI routes for robot-runtime service."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from shared_events.broadcaster import WebSocketBroadcaster
from shared_schemas.robot.models import BehaviorState, MotionCommand, RobotMode

router = APIRouter()

# Populated by main.py at startup
adapter: FakeRobotAdapter | None = None
engine: BehaviorEngine | None = None
broadcaster: WebSocketBroadcaster | None = None


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> JSONResponse:
    if adapter is None:
        return JSONResponse({"status": "starting"}, status_code=503)
    status = await adapter.get_status()
    return JSONResponse({"status": "ok", "robot": status.model_dump()})


# ------------------------------------------------------------------
# Robot status
# ------------------------------------------------------------------


@router.get("/robot/status")
async def get_status() -> JSONResponse:
    assert adapter is not None
    status = await adapter.get_status()
    return JSONResponse(status.model_dump())


@router.post("/robot/connect")
async def connect() -> JSONResponse:
    assert adapter is not None
    await adapter.connect()
    return JSONResponse({"connected": True})


@router.post("/robot/disconnect")
async def disconnect() -> JSONResponse:
    assert adapter is not None
    await adapter.disconnect()
    return JSONResponse({"connected": False})


# ------------------------------------------------------------------
# Speech
# ------------------------------------------------------------------


@router.post("/robot/speak")
async def speak(body: dict) -> JSONResponse:
    assert engine is not None
    text: str = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=422)
    await engine.speak(text)
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Motion
# ------------------------------------------------------------------


@router.post("/robot/motion")
async def execute_motion(command: MotionCommand) -> JSONResponse:
    assert adapter is not None
    await adapter.execute_motion(command)
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Mode
# ------------------------------------------------------------------


@router.post("/robot/mode")
async def set_mode(body: dict) -> JSONResponse:
    assert engine is not None
    mode_str: str = body.get("mode", "")
    try:
        mode = RobotMode(mode_str)
    except ValueError:
        return JSONResponse({"error": f"Unknown mode: {mode_str!r}"}, status_code=422)
    await engine.transition(BehaviorState.IDLE)
    await adapter.set_state(mode, BehaviorState.IDLE)  # type: ignore[union-attr]
    return JSONResponse({"mode": mode})


# ------------------------------------------------------------------
# WebSocket event stream
# ------------------------------------------------------------------


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    assert broadcaster is not None
    await broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(websocket)
