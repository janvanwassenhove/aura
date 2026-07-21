"""Voice input (U36e): the console microphone talks to the robot.

POST /voice/turn (multipart audio) →
  1. speech → text (OpenAI transcription; the brain holds the key),
  2. the transcript is published as TranscriptUpdated (console user turn),
  3. one pipeline turn — the reply is published as ResponseDrafted, which the
     embodiment handler speaks out loud on the robot with a gesture.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/voice", tags=["voice"])

_pipeline: Any = None
_bus: Any = None
_session_id: str = "default"
_robot: Any = None  # for the listening acknowledgment nod (U36g)


_voice_loop: Any = None


def init(pipeline: Any, bus: Any, session_id: str, robot: Any = None,
         voice_loop: Any = None) -> None:
    global _pipeline, _bus, _session_id, _robot, _voice_loop
    _pipeline, _bus, _session_id, _robot = pipeline, bus, session_id, robot
    _voice_loop = voice_loop


def set_voice_loop(loop: Any) -> None:
    """U184: the loop is built after voice_api.init(), so it lands here."""
    global _voice_loop
    _voice_loop = loop


@router.post("/panic")
async def panic_stop() -> JSONResponse:
    """U184: STOP — cut speech, end the conversation session, mic off.

    Ambient noise can push a Realtime session into a loop where it answers
    its own echo. One call ends it; turning the mic back on is deliberate.
    Works even when the voice loop is not running: the robot is silenced and
    the mic is switched off regardless."""
    import os

    result = {"stopped": True, "speech": False, "session": False, "voice_mode": "off"}
    if _voice_loop is not None:
        result = await _voice_loop.panic()
    else:
        os.environ["VOICE_MODE"] = "off"
        if _robot is not None:
            try:
                await _robot.stop_audio()
                result["speech"] = True
            except Exception:  # noqa: BLE001 — a panic stop never fails
                pass
    return JSONResponse(result)


@router.post("/listen")
async def listen_turn(body: dict | None = None) -> JSONResponse:
    """Talk to the robot via ITS OWN microphone: record on the Pi → transcribe
    → one pipeline turn (reply spoken back on the robot)."""
    if _pipeline is None or _robot is None:
        return JSONResponse({"error": "voice not initialised"}, status_code=503)
    from aura_brain import voice

    duration = float((body or {}).get("duration_s", 5.0))
    try:
        wav, _peak = await _robot.listen(duration_s=duration)
    except Exception as exc:  # noqa: BLE001 — robot offline / mic disabled
        return JSONResponse(
            {"error": f"could not record from the robot mic: {type(exc).__name__}"},
            status_code=503,
        )
    transcript = await voice.transcribe(wav, filename="robot.wav")
    if not transcript or not transcript.strip():
        return JSONResponse(
            {"error": "I didn't catch that — is the robot's mic enabled and were "
                      "you speaking? (Needs OPENAI_API_KEY.)"},
            status_code=422,
        )
    transcript = transcript.strip()

    from shared_schemas.events.audio import TranscriptUpdated

    await _bus.publish(TranscriptUpdated(
        session_id=_session_id, transcript=transcript, is_final=True,
    ))
    reply = await _pipeline.orchestrate(transcript, _session_id)
    return JSONResponse({"transcript": transcript, "reply": reply})


@router.post("/turn")
async def voice_turn(audio: UploadFile) -> JSONResponse:
    if _pipeline is None:
        return JSONResponse({"error": "voice not initialised"}, status_code=503)
    from aura_brain import voice

    data = await audio.read()
    if not data:
        return JSONResponse({"error": "empty audio"}, status_code=422)

    # U36g: human listening behavior — a small acknowledging nod while the
    # brain works on what you said. Fire-and-forget; never blocks the turn.
    if _robot is not None:
        import asyncio

        from shared_schemas.robot.models import MotionCommand

        asyncio.ensure_future(_robot.execute_motion(MotionCommand(
            motion_id="nod", speed=0.6, amplitude=0.3, direction=None,
        )))

    transcript = await voice.transcribe(data, filename=audio.filename or "audio.webm")
    if not transcript or not transcript.strip():
        return JSONResponse(
            {"error": "could not understand the audio — is a microphone connected "
                      "and OPENAI_API_KEY set?"},
            status_code=422,
        )
    transcript = transcript.strip()

    from shared_schemas.events.audio import TranscriptUpdated

    await _bus.publish(TranscriptUpdated(
        session_id=_session_id, transcript=transcript, is_final=True,
    ))
    reply = await _pipeline.orchestrate(transcript, _session_id)
    return JSONResponse({"transcript": transcript, "reply": reply})
