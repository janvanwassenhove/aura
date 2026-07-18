"""U129: wake-gated OpenAI Realtime voice turn + cost meter.

Human, low-latency conversation via the Realtime API (audio in → audio out,
multilingual, server-side VAD). It is opened ONLY after the local wake word
(U128), so we never stream — and pay for — audio 24/7; a turn bills just the
seconds actually spoken. Any failure (no key, connection error, unavailable)
raises so the voice loop falls back to the existing STT→LLM→TTS pipeline.

Design notes
------------
* One turn = one captured PCM window in → transcript + PCM audio out. This fits
  the current windowed capture; continuous full-duplex streaming is a later
  refinement once verified on the Pi.
* The OpenAI connection is obtained through an injectable factory so the whole
  path is unit-testable with a fake connection (no network, no key).
* CostMeter turns the per-turn token usage into a running spend estimate with
  env-configurable rates — so the owner sees real numbers before leaving it on.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Cost meter
# ------------------------------------------------------------------

def _rate(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, default))
    except (TypeError, ValueError):
        return default


@dataclass
class CostMeter:
    """Running spend estimate for Realtime turns. Rates are USD per 1M tokens,
    overridable via env (verify current pricing before relying on it)."""

    text_in: int = 0
    text_out: int = 0
    audio_in: int = 0
    audio_out: int = 0
    turns: int = 0
    _rates: dict = field(default_factory=lambda: {
        "text_in": _rate("REALTIME_TEXT_IN_PER_M", 0.60),
        "text_out": _rate("REALTIME_TEXT_OUT_PER_M", 2.40),
        "audio_in": _rate("REALTIME_AUDIO_IN_PER_M", 10.00),
        "audio_out": _rate("REALTIME_AUDIO_OUT_PER_M", 20.00),
    })

    def add(self, usage: dict | None) -> None:
        if not usage:
            return
        self.turns += 1
        itd = usage.get("input_token_details", {}) or {}
        otd = usage.get("output_token_details", {}) or {}
        self.audio_in += int(itd.get("audio_tokens", 0) or 0)
        self.audio_out += int(otd.get("audio_tokens", 0) or 0)
        self.text_in += int(itd.get("text_tokens", 0) or 0)
        self.text_out += int(otd.get("text_tokens", 0) or 0)

    def spent_usd(self) -> float:
        return round(
            self.text_in / 1e6 * self._rates["text_in"]
            + self.text_out / 1e6 * self._rates["text_out"]
            + self.audio_in / 1e6 * self._rates["audio_in"]
            + self.audio_out / 1e6 * self._rates["audio_out"],
            4,
        )

    def summary(self) -> dict:
        return {
            "turns": self.turns,
            "audio_in_tokens": self.audio_in,
            "audio_out_tokens": self.audio_out,
            "text_in_tokens": self.text_in,
            "text_out_tokens": self.text_out,
            "estimated_usd": self.spent_usd(),
        }


# One meter per brain process — surfaced to the console (U129 UI).
METER = CostMeter()


# ------------------------------------------------------------------
# Realtime turn
# ------------------------------------------------------------------

ConnFactory = Callable[[str], Any]  # model -> async context manager


def _default_conn_factory(model: str):
    from openai import AsyncOpenAI

    return AsyncOpenAI().beta.realtime.connect(model=model)


def wav_to_pcm24k(wav_bytes: bytes) -> bytes | None:
    """Decode a WAV window → raw PCM16 mono @ 24 kHz (Realtime input format)."""
    import io
    import wave

    import numpy as np

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            rate, channels = wf.getframerate(), wf.getnchannels()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    except (wave.Error, EOFError, OSError):
        return None
    if audio.size == 0:
        return None
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if rate != 24_000:
        idx = np.linspace(0, audio.size - 1, int(audio.size * 24_000 / rate))
        audio = np.interp(idx, np.arange(audio.size), audio).astype(np.int16)
    return audio.tobytes()


def realtime_enabled() -> bool:
    return (
        os.environ.get("VOICE_ENGINE", "pipeline").lower() == "realtime"
        and bool(os.environ.get("OPENAI_API_KEY"))
    )


async def run_realtime_turn(
    pcm_in: bytes,
    *,
    instructions: str = "",
    voice: str = "alloy",
    conn_factory: ConnFactory | None = None,
    meter: CostMeter | None = None,
) -> tuple[str, bytes]:
    """One turn: PCM16 audio in → (transcript, PCM16 audio out). Raises on any
    failure (incl. TIMEOUT) so the caller can fall back to the classic
    pipeline — a stalled Realtime connection must never freeze the voice loop."""
    import asyncio

    timeout = float(os.environ.get("REALTIME_TURN_TIMEOUT_S", "15"))
    try:
        return await asyncio.wait_for(
            _run_realtime_turn_inner(pcm_in, instructions, voice, conn_factory, meter),
            timeout=timeout,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"realtime turn timed out after {timeout:.0f}s") from exc


async def _run_realtime_turn_inner(
    pcm_in: bytes,
    instructions: str,
    voice: str,
    conn_factory: ConnFactory | None,
    meter: CostMeter | None,
) -> tuple[str, bytes]:
    model = os.environ.get("REALTIME_MODEL", "gpt-4o-mini-realtime-preview")
    factory = conn_factory or _default_conn_factory
    meter = meter or METER

    audio_out = bytearray()
    transcript_parts: list[str] = []
    usage: dict | None = None

    async with factory(model) as conn:
        await conn.session.update(session={
            "modalities": ["audio", "text"],
            "instructions": instructions or "You are a friendly robot assistant. "
            "Reply in the language the user speaks (Dutch, English, French or German).",
            "voice": voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
        })
        await conn.input_audio_buffer.append(audio=base64.b64encode(pcm_in).decode())
        await conn.input_audio_buffer.commit()
        await conn.response.create()

        async for event in conn:
            etype = getattr(event, "type", "")
            if etype == "response.audio.delta":
                audio_out += base64.b64decode(getattr(event, "delta", "") or "")
            elif etype in ("response.audio_transcript.delta", "response.text.delta"):
                transcript_parts.append(getattr(event, "delta", "") or "")
            elif etype == "response.done":
                resp = getattr(event, "response", None)
                usage = _usage_dict(getattr(resp, "usage", None))
                break
            elif etype == "error":
                raise RuntimeError(f"realtime error: {getattr(event, 'error', '')}")

    meter.add(usage)
    return "".join(transcript_parts).strip(), bytes(audio_out)


def _usage_dict(usage: Any) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    # SDK object → dict (best-effort across versions).
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(usage, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return None
