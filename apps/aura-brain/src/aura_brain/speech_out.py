"""U364: where his voice comes out — the robot's speaker, or this laptop.

Asked for as: "can we add option that audio can go via laptop (so default
robot, but we can also choose to go via audio of laptop?".

The console has had a "Laptop audio" switch since U209 and it reads the line
with the BROWSER's speech synthesis. That is a Windows voice, not his: it loses
the character's own voice and speed (U349), and it cannot do a line that
changes persona halfway, because by the time the browser sees it the line is
text again.

The brain already synthesizes the real audio before it ever reaches the robot.
So this is a question about where that audio is PLAYED, not about producing it
twice. `deliver()` is the one place that decides, because there are five call
sites that speak and a decision copied five times is a decision that will drift.

The hand-over is deliberately small: the audio is held here under an id, an
event says it is ready, the console fetches it once, and it is gone. Holding
every line of a talk would be a leak, and serving one twice would let a
reconnecting console replay the last thing he said into a quiet room.
"""

from __future__ import annotations

import base64
import logging
import os
import struct
import uuid
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

ROBOT = "robot"
LAPTOP = "laptop"

#: PCM s16le mono @ 24 kHz — what `voice.synthesize_b64` returns, always.
SAMPLE_RATE = 24000
CHANNELS = 1
BITS = 16

#: How many unfetched utterances to hold. Small on purpose: this is a hand-over
#: between two processes on one machine, not a store. A console that is closed
#: or asleep simply misses them, which is the correct outcome.
KEEP = 8

_waiting: "OrderedDict[str, bytes]" = OrderedDict()


def output() -> str:
    """Where speech should be played. Read live, so the toggle applies at once.

    Anything unrecognised is the robot. A typo in an env var must never be the
    reason a room hears nothing.
    """
    choice = os.environ.get("AUDIO_OUTPUT", ROBOT).strip().lower()
    return LAPTOP if choice == LAPTOP else ROBOT


def wav_from_pcm(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM in a WAV header.

    Served as WAV so the console can hand the URL to an `<audio>` element;
    raw PCM would mean decoding it by hand in the browser for no reason.
    """
    byte_rate = rate * CHANNELS * BITS // 8
    block_align = CHANNELS * BITS // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, CHANNELS, rate,
                                    byte_rate, block_align, BITS)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def take(utterance_id: str) -> bytes | None:
    """The WAV for one utterance, once. Returns None if it was already served
    or has aged out."""
    return _waiting.pop(utterance_id, None)


def pending() -> int:
    return len(_waiting)


def forget_all() -> None:
    _waiting.clear()


def _hold(pcm: bytes) -> str:
    utterance_id = uuid.uuid4().hex
    _waiting[utterance_id] = wav_from_pcm(pcm)
    while len(_waiting) > KEEP:
        _waiting.popitem(last=False)      # drop the oldest unfetched line
    return utterance_id


async def deliver(robot: Any, bus: Any, text: str, audio_b64: str | None,
                  subtitle: dict | None = None) -> bool:
    """Play one line. Returns whether it was actually handed anywhere.

    Never pretends: a line with no audio reports False rather than looking
    like a successful utterance (U269's rule).

    U400: `subtitle` ({"text", "persona", "beat_id"}) announces a talk's line
    as it starts — before the robot is handed it (its `speak` returns only
    once it has finished playing), or tied to the laptop's line id, which the
    playing window reports starting.
    """
    if output() == LAPTOP:
        return await _offer(bus, text, audio_b64, subtitle)
    if robot is None:
        return False
    if subtitle is not None:
        await _announce(bus, subtitle, _seconds(audio_b64), "")
    await robot.speak(text, audio_b64=audio_b64)
    return True


def _seconds(audio_b64: str | None) -> float:
    """How long a PCM line plays: 24 kHz, 16-bit, mono."""
    try:
        return len(base64.b64decode(audio_b64 or "")) / (SAMPLE_RATE * CHANNELS * BITS // 8)
    except Exception:  # noqa: BLE001 — a length is never worth a failed line
        return 0.0


async def _announce(bus: Any, subtitle: dict, seconds: float, utterance_id: str) -> None:
    if bus is None:
        return
    from shared_schemas.events.system import PresentationSubtitle  # noqa: PLC0415

    try:
        await bus.publish(PresentationSubtitle(
            session_id="presentation", text=str(subtitle.get("text", "")),
            duration_s=round(seconds, 3), persona=str(subtitle.get("persona", "")),
            beat_id=str(subtitle.get("beat_id", "")), utterance_id=utterance_id))
    except Exception as exc:  # noqa: BLE001 — a subtitle never costs the line
        logger.debug("subtitle not announced: %s", exc)


async def deliver_segment(robot: Any, bus: Any, audio_b64: str | None) -> bool:
    """Play one streamed piece of a reply. Returns whether it was handed anywhere.

    U385: the live and realtime engines speak in ~1.4 s segments as the
    provider produces them, over `/robot/speak/segment`. U364 left that path
    alone and wrote the exception down; it was what the owner heard from the
    robot with the laptop chosen. On the laptop each segment is its own
    hand-over, and the console plays them in the order they were offered.
    """
    if output() == LAPTOP:
        return await _offer(bus, "", audio_b64)
    if robot is None:
        return False
    await robot.speak_segment(audio_b64)
    return True


async def stop(robot: Any, bus: Any) -> None:
    """Silence him wherever he is speaking.

    U385: every Stop used to reach the robot's speaker only. The laptop is told
    first, and unfetched lines are dropped, because the robot call is the one
    that can fail — an offline robot must never leave the laptop talking. The
    robot's error still propagates, so callers that report whether the robot
    stopped keep reporting it honestly.
    """
    forget_all()
    if bus is not None:
        from shared_schemas.events.audio import SpeechAudioStopped  # noqa: PLC0415

        try:
            await bus.publish(SpeechAudioStopped(session_id="default"))
        except Exception as exc:  # noqa: BLE001 — a stop never fails on the bus
            logger.warning("could not tell the laptop to stop: %s", exc)
    if robot is not None:
        await robot.stop_audio()


async def _offer(bus: Any, text: str, audio_b64: str | None,
                 subtitle: dict | None = None) -> bool:
    """Hold one piece of audio for the console and tell it so."""
    if not audio_b64:
        return False
    try:
        pcm = base64.b64decode(audio_b64)
    except Exception as exc:  # noqa: BLE001 — bad audio is not a crash
        logger.warning("speech audio could not be decoded: %s", exc)
        return False
    if bus is None:
        # The event is the whole delivery: without it nothing will ever ask
        # for the audio, so holding it and returning True would be a
        # successful-looking utterance that no room can hear (ADR-009).
        logger.warning("speech cannot reach the laptop: no event bus")
        return False
    from shared_schemas.events.audio import SpeechAudioReady  # noqa: PLC0415

    utterance_id = _hold(pcm)
    if subtitle is not None:
        # U400: before the line is offered, so it is known before it can play.
        await _announce(bus, subtitle, len(pcm) / (SAMPLE_RATE * CHANNELS * BITS // 8),
                        utterance_id)
    await bus.publish(SpeechAudioReady(
        session_id="default", utterance_id=utterance_id, text=text))
    logger.info("speech routed to the laptop (%d bytes)", len(pcm))
    return True


# ------------------------------------------------------------------
# The hand-over: one GET, one line, gone.
# ------------------------------------------------------------------

from fastapi import APIRouter  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402

router = APIRouter(tags=["speech"])

_bus: Any = None


def bind_bus(bus: Any) -> None:
    """The bus a playing window's start is told on (U400)."""
    global _bus
    _bus = bus


@router.post("/speech/{utterance_id}/started")
async def speech_started(utterance_id: str, body: dict | None = None) -> JSONResponse:
    """U400: the window playing a line says it has started — the moment the
    projector's subtitle for it may start, which only that window knows."""
    try:
        seconds = float((body or {}).get("duration_s") or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds != seconds or seconds < 0:      # NaN from an <audio> that cannot tell
        seconds = 0.0
    if _bus is not None:
        from shared_schemas.events.audio import SpeechLineStarted  # noqa: PLC0415

        await _bus.publish(SpeechLineStarted(
            session_id="default", utterance_id=utterance_id, duration_s=seconds))
    return JSONResponse({"ok": True})


@router.get("/speech/{utterance_id}.wav")
async def speech_wav(utterance_id: str) -> Response:
    """Serve one synthesized line to the console, once.

    404 once it has been taken or has aged out, which is the honest answer:
    the console asking twice means something replayed, and a room hearing the
    last sentence again is worse than hearing nothing.
    """
    wav = take(utterance_id)
    if wav is None:
        return JSONResponse(
            {"error": "that line is no longer waiting to be played"},
            status_code=404)
    return Response(content=wav, media_type="audio/wav",
                    headers={"Cache-Control": "no-store"})


@router.get("/speech/output")
async def speech_output() -> JSONResponse:
    """Where speech is going right now, and what is waiting."""
    return JSONResponse({"output": output(), "pending": pending()})
