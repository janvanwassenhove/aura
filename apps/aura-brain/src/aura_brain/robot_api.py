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


# U195: one shared, keep-alive client for the live view. A fresh connection per
# frame would spend a TCP+HTTP handshake on every single frame — the polling
# model only beats streaming if asking is cheap.
_frame_client: httpx.AsyncClient | None = None

# U196: the robot is deployed SEPARATELY from this app — the owner installs a
# new AURA release on the laptop while the Pi keeps running whatever was last
# pulled there. Measured on a live setup: the Pi was still sending unscaled
# 1280x720 / 487 KB frames, i.e. code from before U188's downscaling, months
# after that shipped. So a console that simply required the new endpoint would
# have found a 404 and shown "No camera feed" — a fix that breaks the thing it
# fixes. `None` = not probed yet, True/False = robot has /camera/frame.jpg.
_robot_has_frame_jpg: bool | None = None

_LATEST: dict[str, Any] = {"jpeg": b"", "task": None}

_FALLBACK_WIDTH = 640
_FALLBACK_QUALITY = 70


def _shrink(jpeg: bytes) -> bytes:
    """Downscale a legacy robot's full-size frame. Returns the input on any
    problem — a failed optimisation must never cost us the picture."""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(jpeg))
        if img.width <= _FALLBACK_WIDTH:
            return jpeg
        h = max(1, round(img.height * _FALLBACK_WIDTH / img.width))
        img = img.convert("RGB").resize((_FALLBACK_WIDTH, h), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_FALLBACK_QUALITY)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return jpeg


async def shutdown_camera() -> None:
    """Stop the background reader and close the shared client (app shutdown)."""
    task = _LATEST.get("task")
    if task is not None and not task.done():
        task.cancel()
    _LATEST["task"] = None
    global _frame_client
    if _frame_client is not None:
        await _frame_client.aclose()
        _frame_client = None


def _base() -> str:
    return getattr(_robot, "_base_url", "http://robot-runtime:8001")


def _client() -> httpx.AsyncClient:
    global _frame_client
    if _frame_client is None:
        _frame_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    return _frame_client


async def _pump_latest_frame() -> None:
    """Keep ONLY the newest frame from an old robot's MJPEG stream.

    An old Pi has no per-frame endpoint, so the brain reads its stream
    continuously and throws away everything but the last frame. Draining
    without buffering is what keeps the picture current: the console then polls
    for the newest frame we hold, and no queue can build on either hop.
    """
    import asyncio

    backoff = 1.0
    while True:
        try:
            async with _client().stream(
                "GET", f"{_base()}/robot/camera/stream",
                timeout=httpx.Timeout(10.0, read=None),
            ) as resp:
                if resp.status_code != 200:
                    raise httpx.HTTPError(f"HTTP {resp.status_code}")
                backoff = 1.0
                buf = b""
                async for chunk in resp.aiter_bytes():
                    buf += chunk
                    # Keep the last COMPLETE JPEG in the buffer; drop the rest.
                    end = buf.rfind(b"\xff\xd9")
                    if end == -1:
                        if len(buf) > 4_000_000:   # no marker → corrupt, reset
                            buf = b""
                        continue
                    start = buf.rfind(b"\xff\xd8", 0, end)
                    if start != -1:
                        # Shrink once per received frame, not once per poll:
                        # the console asks more often than the robot delivers,
                        # and an old robot's frames are 1280x720 for a panel a
                        # few hundred pixels wide.
                        _LATEST["jpeg"] = await asyncio.to_thread(
                            _shrink, buf[start:end + 2])
                    buf = buf[end + 2:]
        except asyncio.CancelledError:
            return          # shutdown: expected, not an error worth a traceback
        except (httpx.HTTPError, OSError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15.0)       # robot down — stop hammering


@router.get("/camera/frame.jpg")
async def camera_frame_jpeg() -> Response:
    """One current JPEG frame. The console polls this for the live view.

    Streaming queues frames it cannot deliver, so the picture drifts further
    behind the longer it runs; asking per frame cannot queue and the delay
    stays flat. Works against an old robot too — see `_pump_latest_frame`.
    """
    global _robot_has_frame_jpg
    import asyncio

    if _robot_has_frame_jpg is not False:
        try:
            resp = await _client().get(f"{_base()}/robot/camera/frame.jpg")
        except (httpx.HTTPError, OSError) as exc:
            if _robot_has_frame_jpg is None:
                _robot_has_frame_jpg = False       # can't probe → assume old
            else:
                return _unavailable(exc)
        else:
            if resp.status_code == 200:
                _robot_has_frame_jpg = True
                return Response(content=resp.content, media_type="image/jpeg",
                                headers={"Cache-Control": "no-store"})
            if resp.status_code == 404:
                _robot_has_frame_jpg = False       # older robot — fall through
            else:
                return JSONResponse({"error": "camera unavailable"},
                                    status_code=resp.status_code)

    # Old robot: serve the newest frame the background reader has seen.
    if _LATEST["task"] is None or _LATEST["task"].done():
        _LATEST["task"] = asyncio.create_task(_pump_latest_frame())
    for _ in range(50):                            # first frame: wait up to 5 s
        if _LATEST["jpeg"]:
            break
        await asyncio.sleep(0.1)
    if not _LATEST["jpeg"]:
        return JSONResponse({"error": "camera unavailable"}, status_code=503)
    return Response(content=_LATEST["jpeg"], media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


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


@router.post("/sleep")
async def sleep() -> JSONResponse:
    """U100: sleep MODE — take no action. Suppresses greetings + spoken replies
    (ROBOT_ASLEEP), stops mic listening (VOICE_MODE=off), stops idle head
    tracking, and puts the robot in a sleep pose."""
    import os as _os

    _os.environ["ROBOT_ASLEEP"] = "true"
    _os.environ["VOICE_MODE"] = "off"
    from aura_brain.setup_api import _write_env
    _write_env({"ROBOT_ASLEEP": "true", "VOICE_MODE": "off"})
    try:
        await _robot.set_tracking(False)
        from shared_schemas.robot.models import MotionCommand
        await _robot.execute_motion(MotionCommand(motion_id="sleep", speed=1.0, amplitude=0.6, direction=None))
    except (httpx.HTTPError, OSError):
        pass
    return JSONResponse({"asleep": True})


@router.post("/wake")
async def wake() -> JSONResponse:
    """U100: wake up — resume normal behavior (greetings, replies, listening)."""
    import os as _os

    _os.environ["ROBOT_ASLEEP"] = "false"
    _os.environ["VOICE_MODE"] = "wake_word"
    from aura_brain.setup_api import _write_env
    _write_env({"ROBOT_ASLEEP": "false", "VOICE_MODE": "wake_word"})
    try:
        from shared_schemas.robot.models import MotionCommand
        await _robot.execute_motion(MotionCommand(motion_id="wake_up", speed=1.0, amplitude=0.7, direction=None))
        await _robot.set_tracking(True)
    except (httpx.HTTPError, OSError):
        pass
    return JSONResponse({"asleep": False})


@router.get("/sleep")
async def sleep_status() -> JSONResponse:
    import os as _os
    return JSONResponse({"asleep": _os.environ.get("ROBOT_ASLEEP", "false").lower() == "true"})


@router.get("/proactive")
async def get_proactive() -> JSONResponse:
    """U110: is proactive speech (reminders + daily briefing) on?"""
    import os as _os
    return JSONResponse({
        "enabled": _os.environ.get("PROACTIVE_ENABLED", "true").lower() == "true",
        "briefing_time": _os.environ.get("PROACTIVE_BRIEFING_TIME", ""),
    })


@router.post("/proactive")
async def set_proactive(body: dict) -> JSONResponse:
    """U110: toggle proactive speech + set the daily-briefing time (HH:MM)."""
    import os as _os

    from aura_brain.setup_api import _write_env

    changes: dict = {}
    if "enabled" in (body or {}):
        val = "true" if body["enabled"] else "false"
        _os.environ["PROACTIVE_ENABLED"] = val
        changes["PROACTIVE_ENABLED"] = val
    if "briefing_time" in (body or {}):
        t = str(body["briefing_time"]).strip()
        _os.environ["PROACTIVE_BRIEFING_TIME"] = t
        changes["PROACTIVE_BRIEFING_TIME"] = t
    if changes:
        _write_env(changes)
    return JSONResponse({
        "enabled": _os.environ.get("PROACTIVE_ENABLED", "true").lower() == "true",
        "briefing_time": _os.environ.get("PROACTIVE_BRIEFING_TIME", ""),
    })


@router.post("/tracking")
async def tracking(body: dict) -> JSONResponse:
    try:
        return JSONResponse(await _robot.set_tracking(bool(body.get("enabled", True))))
    except (httpx.HTTPError, OSError) as exc:
        return _unavailable(exc)


@router.post("/aim")
async def aim(body: dict) -> JSONResponse:
    """U161: manual head/torso aiming from the console joystick."""
    try:
        return JSONResponse(await _robot.aim(
            yaw=body.get("yaw", 0.0),
            pitch=body.get("pitch", 0.0),
            body_yaw=body.get("body_yaw"),
        ))
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
