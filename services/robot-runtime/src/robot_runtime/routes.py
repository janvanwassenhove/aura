"""FastAPI routes for robot-runtime service."""

from __future__ import annotations

from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.engine.behavior import BehaviorEngine
from shared_events.broadcaster import WebSocketBroadcaster
from shared_schemas.events.behavior import MotionCompleted, MotionFailed, MotionStarted
from shared_schemas.robot.models import BehaviorState, MotionCommand, RobotMode

router = APIRouter()

# Populated by main.py at startup
adapter: FakeRobotAdapter | None = None
engine: BehaviorEngine | None = None
broadcaster: WebSocketBroadcaster | None = None
bus = None  # AsyncEventBus | None — set by main.py (U36d: motion events)
offline_loop = None  # OfflineBehaviorLoop | None — set by main.py (U15)


def _touch() -> None:
    """Record brain liveness — any brain command means the link is up."""
    if offline_loop is not None:
        offline_loop.touch()


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
    _touch()
    text: str = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=422)
    # Optional synthesized speech (U36b): base64 PCM s16le mono @ 24 kHz.
    # The brain does TTS; the robot only plays — it never holds API keys.
    audio_bytes: bytes | None = None
    audio_b64 = body.get("audio_b64")
    if audio_b64:
        import base64

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            return JSONResponse({"error": "audio_b64 is not valid base64"}, status_code=422)
    await engine.speak(text, audio_bytes)
    return JSONResponse({"ok": True, "audio": audio_bytes is not None})


# ------------------------------------------------------------------
# Motion
# ------------------------------------------------------------------


@router.post("/robot/motion")
async def execute_motion(command: MotionCommand) -> JSONResponse:
    assert adapter is not None
    _touch()
    # U36d: this route calls the adapter directly (full speed/amplitude
    # control), so it must publish the motion events itself — the console's
    # motion log listens for them.
    if bus is not None:
        await bus.publish(MotionStarted(session_id="robot", motion_id=command.motion_id))
    try:
        await adapter.execute_motion(command)
    except Exception as exc:
        if bus is not None:
            await bus.publish(MotionFailed(
                session_id="robot", motion_id=command.motion_id, reason=str(exc),
            ))
        return JSONResponse({"error": f"motion failed: {exc}"}, status_code=500)
    if bus is not None:
        await bus.publish(MotionCompleted(session_id="robot", motion_id=command.motion_id))
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------
# Camera (U18: one frame per request; the brain's perception loop polls)
# ------------------------------------------------------------------


@router.get("/robot/camera/frame")
async def camera_frame() -> Response:
    assert adapter is not None
    _touch()
    try:
        png = await adapter.get_camera_frame()
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)
    return Response(content=png, media_type="image/png")


_STREAM_FPS = 8.0


@router.get("/robot/camera/stream")
async def camera_stream() -> Response:
    """MJPEG stream (multipart/x-mixed-replace) — smooth live video for the
    console. One consumer per connection; frames straight from the adapter."""
    assert adapter is not None
    _touch()
    import asyncio

    from fastapi.responses import StreamingResponse

    grab = getattr(adapter, "get_camera_frame_jpeg", adapter.get_camera_frame)

    async def _frames():
        while True:
            _touch()  # a live stream to the console proves the brain link is up
            try:
                jpeg = await grab()
            except RuntimeError:
                await asyncio.sleep(1.0)
                continue
            yield (
                b"--frame\r\nContent-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                + jpeg + b"\r\n"
            )
            await asyncio.sleep(1.0 / _STREAM_FPS)

    return StreamingResponse(
        _frames(), media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ------------------------------------------------------------------
# Mode
# ------------------------------------------------------------------


@router.post("/robot/mode")
async def set_mode(body: dict) -> JSONResponse:
    assert engine is not None
    _touch()
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
