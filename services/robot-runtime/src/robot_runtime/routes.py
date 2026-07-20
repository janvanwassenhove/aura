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
budget_guard = None  # BudgetGuard | None — set by main.py (U26)


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
    # U79: a status poll is proof the brain link is alive. The brain's
    # RobotEventBridge polls this regularly, so without touching liveness here
    # a brain that is up but just not commanding (ordinary conversation) wrongly
    # trips the offline loop after BRAIN_LINK_TIMEOUT — its idle-nod loop then
    # holds the head and kills follow-me + recognition greetings.
    _touch()
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


@router.post("/robot/speak/segment")
async def speak_segment(body: dict) -> JSONResponse:
    """U153 streaming playback: play ONE PCM segment of a reply as it arrives
    from the Realtime API, instead of buffering the whole utterance first.

    This bypasses the behaviour engine's speak() (gestures + paired
    SpeechPlaybackStarted/Completed events) on purpose — the brain owns the
    conversation UI state, and firing those events per segment would spam the
    console and re-trigger gestures many times per reply. Segments serialize
    on the adapter's motion lock, so they play back-to-back in order. Uses
    ``normalize=False`` + a small tail margin so the segments don't pump in
    volume or leave gaps (see ReachyAdapter.play_audio)."""
    assert engine is not None
    _touch()
    audio_b64 = body.get("audio_b64")
    if not audio_b64:
        return JSONResponse({"error": "audio_b64 is required"}, status_code=422)
    import base64

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return JSONResponse({"error": "audio_b64 is not valid base64"}, status_code=422)
    adapter = getattr(engine, "_adapter", None)
    # U155: prefer the gapless appsrc path — no per-segment pipeline restart
    # (the playbin path's rebuild per segment was the audible stutter), returns
    # once buffered, and feeds the AEC echo probe when active (U156).
    # ROBOT_APPSRC_PLAYBACK=false → the old blocking playbin path.
    import os as _os

    stream_play = getattr(adapter, "play_stream_segment", None)
    if stream_play is not None and _os.environ.get(
            "ROBOT_APPSRC_PLAYBACK", "true").lower() == "true":
        await stream_play(audio_bytes)
        return JSONResponse({"ok": True, "path": "appsrc"})
    play = getattr(adapter, "play_audio", None)
    if play is None:
        return JSONResponse({"error": "adapter has no play_audio"}, status_code=501)
    await play(audio_bytes, normalize=False, tail_margin=0.06)
    return JSONResponse({"ok": True, "path": "playbin"})


@router.get("/robot/audio/stream")
async def audio_stream(raw: bool = False):
    """U154 conversation-session mode: stream the mic continuously as raw
    s16le mono 16 kHz PCM chunks (chunked HTTP — no WebSocket needed for a
    one-way stream). The brain forwards these to the Realtime API, whose
    server-side VAD does the endpointing — this replaces fixed capture
    windows entirely while a session is active."""
    from fastapi.responses import StreamingResponse

    assert adapter is not None
    _touch()
    stream = getattr(adapter, "stream_audio", None)
    if stream is None:
        return JSONResponse({"error": "adapter has no stream_audio"}, status_code=501)

    import inspect

    kwargs = {}
    if "raw" in inspect.signature(stream).parameters:
        kwargs["raw"] = raw

    async def _gen():
        async for chunk in stream(**kwargs):
            yield chunk

    return StreamingResponse(
        _gen(),
        media_type="audio/L16",
        headers={"X-Sample-Rate": "16000", "X-Channels": "1"},
    )


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
# Microphone (U45: capture from the robot's onboard mic → WAV)
# ------------------------------------------------------------------


@router.post("/robot/listen")
async def listen(body: dict) -> Response:
    """Record from the robot's microphone and return a 16 kHz mono WAV."""
    assert adapter is not None
    _touch()
    duration = float((body or {}).get("duration_s", 5.0))
    duration = max(1.0, min(duration, 15.0))
    pcm = await adapter.capture_audio(duration_s=duration)
    if not pcm:
        return JSONResponse({"error": "no audio captured (is the mic enabled?)"}, status_code=503)
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(pcm)
    peak = getattr(adapter, "last_capture_peak", lambda: 0.0)()
    return Response(
        content=buf.getvalue(), media_type="audio/wav",
        headers={"X-Audio-Peak": f"{peak:.5f}"},
    )


# ------------------------------------------------------------------
# Head tracking (U36g: follow the person)
# ------------------------------------------------------------------


@router.post("/robot/aim")
async def aim(body: dict) -> JSONResponse:
    """U161: point the head (camera) and torso from the console joystick.

    yaw/pitch/body_yaw are -1..1 fractions of the safe range; body_yaw may be
    omitted to leave the torso alone. Aiming pauses follow-me (see
    ReachyRobotAdapter.aim) — the console's tracking toggle gives it back.
    """
    assert adapter is not None
    _touch()
    fn = getattr(adapter, "aim", None)
    if fn is None:
        return JSONResponse({"error": "adapter cannot aim"}, status_code=501)
    body = body or {}

    def _num(key: str, default: float | None) -> float | None:
        raw = body.get(key, default)
        if raw is None:
            return None
        try:
            return max(-1.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return default

    try:
        result = await fn(
            yaw=_num("yaw", 0.0) or 0.0,
            pitch=_num("pitch", 0.0) or 0.0,
            body_yaw=_num("body_yaw", None),
            duration=float(body.get("duration", 0.35) or 0.35),
        )
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse({"ok": True, **(result or {})})


@router.post("/robot/tracking")
async def set_tracking(body: dict) -> JSONResponse:
    assert adapter is not None
    _touch()
    enabled = bool(body.get("enabled", True))
    toggler = getattr(adapter, "set_tracking", None)
    if toggler is None:
        return JSONResponse({"error": "adapter has no head tracking"}, status_code=501)
    try:
        await toggler(enabled)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"tracking failed: {exc}"}, status_code=500)
    return JSONResponse({"tracking": enabled})


@router.post("/robot/audio/stop")
async def audio_stop() -> JSONResponse:
    """U84 barge-in: abort the current utterance immediately."""
    assert adapter is not None
    _touch()
    stopper = getattr(adapter, "stop_audio", None)
    if stopper is None:
        return JSONResponse({"error": "adapter has no stop_audio"}, status_code=501)
    return JSONResponse({"stopped": bool(stopper())})


@router.get("/robot/budget")
async def budget() -> JSONResponse:
    """U26: on-Pi resource budget (CPU/mem/temp) and constrained state."""
    if budget_guard is None:
        return JSONResponse({"constrained": False, "reasons": [], "budgets": {}})
    return JSONResponse(budget_guard.status())


@router.post("/robot/body_follow")
async def set_body_follow(body: dict) -> JSONResponse:
    """U37: torso turns with the tracked face (automatic body yaw)."""
    assert adapter is not None
    _touch()
    enabled = bool(body.get("enabled", True))
    toggler = getattr(adapter, "set_body_follow", None)
    if toggler is None:
        return JSONResponse({"error": "adapter has no body follow"}, status_code=501)
    try:
        await toggler(enabled)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"body follow failed: {exc}"}, status_code=500)
    return JSONResponse({"body_follow": enabled})


# ------------------------------------------------------------------
# Volume (U36e: app-controlled speaker gain)
# ------------------------------------------------------------------


@router.get("/robot/volume")
async def get_volume() -> JSONResponse:
    assert adapter is not None
    level = getattr(adapter, "get_volume", lambda: 1.0)()
    return JSONResponse({"volume": level})


@router.post("/robot/volume")
async def set_volume(body: dict) -> JSONResponse:
    assert adapter is not None
    _touch()
    try:
        level = float(body.get("volume"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "volume must be a number 0..1"}, status_code=422)
    setter = getattr(adapter, "set_volume", None)
    if setter is None:
        return JSONResponse({"error": "adapter has no volume control"}, status_code=501)
    return JSONResponse({"volume": setter(level)})


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
