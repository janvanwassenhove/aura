"""Robot proxy API — the console reaches the robot THROUGH the brain.

The console only ever talks to the brain origin; these routes forward to
robot-runtime over the one brain↔robot network hop (RobotClient). This keeps
CORS single-origin and the robot URL a server-side concern.

    GET  /robot/status        → robot-runtime /robot/status
    GET  /robot/camera/frame  → one PNG frame (for the live video panel)
    POST /robot/motion        → quick actions (wave/nod/…) from the UI
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from shared_schemas.robot.models import MotionCommand

router = APIRouter(prefix="/robot", tags=["robot"])

_robot: Any = None  # RobotClient — set by init()


def init(robot: Any) -> None:
    global _robot
    _robot = robot


def _unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"error": f"robot unreachable: {type(exc).__name__}"}, status_code=503,
    )


@router.get("/status")
async def status() -> JSONResponse:
    try:
        return JSONResponse(await _robot.status())
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.get("/camera/stream")
async def camera_stream() -> Response:
    """Proxy the robot's MJPEG stream to the console (single origin)."""
    from fastapi.responses import StreamingResponse

    base_url = getattr(_robot, "_base_url", "http://robot-runtime:8001")
    client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=None))

    async def _relay():
        try:
            async with client.stream("GET", f"{base_url}/robot/camera/stream") as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk
        except (httpx.HTTPError, OSError):
            return  # robot gone — the <img> onerror handler retries
        finally:
            await client.aclose()

    return StreamingResponse(
        _relay(), media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/camera/frame")
async def camera_frame() -> Response:
    try:
        png = await _robot.camera_frame()
    except httpx.HTTPStatusError as exc:
        # Robot answered but has no camera (e.g. media disabled) → pass along.
        return JSONResponse({"error": "camera unavailable"}, status_code=exc.response.status_code)
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/motion")
async def motion(command: MotionCommand) -> JSONResponse:
    try:
        ok = await _robot.execute_motion(command)
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)
    return JSONResponse({"ok": ok})


@router.post("/tracking")
async def tracking(body: dict) -> JSONResponse:
    try:
        return JSONResponse(await _robot.set_tracking(bool(body.get("enabled", True))))
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.post("/body_follow")
async def body_follow(body: dict) -> JSONResponse:
    """U37: torso turns with the tracked face."""
    try:
        return JSONResponse(await _robot.set_body_follow(bool(body.get("enabled", True))))
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.get("/volume")
async def get_volume() -> JSONResponse:
    try:
        return JSONResponse(await _robot.get_volume())
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.post("/volume")
async def set_volume(body: dict) -> JSONResponse:
    try:
        return JSONResponse(await _robot.set_volume(float(body.get("volume", 0.8))))
    except (TypeError, ValueError):
        return JSONResponse({"error": "volume must be a number 0..1"}, status_code=422)
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.post("/say")
async def say(body: dict) -> JSONResponse:
    """Make the robot SAY something out loud: brain-side TTS → robot speaker.

    Optional ``motion_id`` plays a gesture along with the speech (U36g
    speak-and-move quick actions). Degrades to text-only without TTS.
    """
    text = (body or {}).get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=422)
    from aura_brain import voice

    audio_b64 = await voice.synthesize_b64(text)
    motion_id = (body or {}).get("motion_id")
    try:
        if motion_id:
            import asyncio

            await asyncio.gather(
                _robot.execute_motion(MotionCommand(
                    motion_id=motion_id, speed=1.0, amplitude=0.6, direction=None,
                )),
                _robot.speak(text, audio_b64=audio_b64),
            )
            ok = True
        else:
            ok = await _robot.speak(text, audio_b64=audio_b64)
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)
    return JSONResponse({"ok": ok, "voiced": audio_b64 is not None})
