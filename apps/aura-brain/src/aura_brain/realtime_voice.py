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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

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

    # U144: GA Realtime path. The old `beta.realtime` shape is disabled
    # server-side (close 4000 invalid_request_error.beta_api_shape_disabled).
    return AsyncOpenAI().realtime.connect(model=model)


# U143: candidate Realtime models, newest-GA first. probe() walks these to find
# one the account actually serves, so the owner never guesses a model name.
_MODEL_CANDIDATES = (
    "gpt-realtime",
    "gpt-4o-realtime-preview",
    "gpt-4o-mini-realtime-preview",
)


def _default_realtime_model() -> str:
    return os.environ.get("REALTIME_MODEL") or _MODEL_CANDIDATES[0]


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
    text: str = "",
    instructions: str = "",
    voice: str = "alloy",
    conn_factory: ConnFactory | None = None,
    meter: CostMeter | None = None,
    on_segment: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, bytes]:
    """One turn → (reply transcript, PCM16 audio out). If ``text`` is given the
    turn is driven by that exact text (our STT command — reliable, and much
    faster than uploading audio); otherwise the captured PCM audio is sent.

    U153: if ``on_segment`` is given, it's awaited with each ~REALTIME_SEGMENT_MS
    slice of audio AS IT ARRIVES — so playback can start on the first segment
    instead of waiting for the whole reply (the 6 s buffering the traces showed).
    ``on_segment`` must return quickly (enqueue, don't block) or it stalls the
    receive loop. Raises on any failure (incl. TIMEOUT) so the caller can fall
    back to the pipeline — a stalled connection must never freeze the loop."""
    import asyncio

    timeout = float(os.environ.get("REALTIME_TURN_TIMEOUT_S", "15"))
    try:
        return await asyncio.wait_for(
            _run_realtime_turn_inner(pcm_in, text, instructions, voice,
                                     conn_factory, meter, on_segment),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise RuntimeError(f"realtime turn timed out after {timeout:.0f}s") from exc


async def _run_realtime_turn_inner(
    pcm_in: bytes,
    text: str,
    instructions: str,
    voice: str,
    conn_factory: ConnFactory | None,
    meter: CostMeter | None,
    on_segment: Callable[[bytes], Awaitable[None]] | None = None,
) -> tuple[str, bytes]:
    model = _default_realtime_model()
    factory = conn_factory or _default_conn_factory
    meter = meter or METER

    audio_out = bytearray()
    transcript_parts: list[str] = []
    usage: dict | None = None
    # U153: stream playback in coarse segments (24 kHz PCM16 → 48000 bytes/s).
    seg = bytearray()
    seg_bytes = int(24_000 * 2 * float(os.environ.get("REALTIME_SEGMENT_MS", "1400")) / 1000)

    async with factory(model) as conn:
        # U144: GA session shape (type:realtime + audio output).
        await conn.session.update(session={
            "type": "realtime",
            "output_modalities": ["audio"],
            "instructions": instructions or "You are a friendly robot assistant. "
            "Reply in the language the user speaks (Dutch, English, French or German).",
            "audio": {
                "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": voice},
            },
        })
        # U146: prefer the exact STT text — the fixed-window capture degrades
        # the audio (a wake word + trailing silence), which made Realtime greet
        # generically instead of answering. Sending the transcript we already
        # have is reliable and faster (no big audio upload / flush). Fall back
        # to the raw audio only when no text is available.
        if text:
            content = [{"type": "input_text", "text": text}]
        else:
            content = [{"type": "input_audio", "audio": base64.b64encode(pcm_in).decode()}]
        await conn.conversation.item.create(item={
            "type": "message", "role": "user", "content": content})
        await conn.response.create()

        async for event in conn:
            etype = getattr(event, "type", "")
            # GA names first, older names kept as a fallback.
            if etype in ("response.output_audio.delta", "response.audio.delta"):
                chunk = base64.b64decode(getattr(event, "delta", "") or "")
                audio_out += chunk
                if on_segment is not None:
                    seg += chunk
                    if len(seg) >= seg_bytes:
                        await on_segment(bytes(seg))  # enqueue a segment to play
                        seg = bytearray()
            elif etype in ("response.output_audio_transcript.delta",
                           "response.audio_transcript.delta",
                           "response.output_text.delta", "response.text.delta"):
                transcript_parts.append(getattr(event, "delta", "") or "")
            elif etype == "response.done":
                resp = getattr(event, "response", None)
                usage = _usage_dict(getattr(resp, "usage", None))
                break
            elif etype == "error":
                raise RuntimeError(f"realtime error: {getattr(event, 'error', '')}")

    if on_segment is not None and seg:
        await on_segment(bytes(seg))  # flush the tail
    meter.add(usage)
    return "".join(transcript_parts).strip(), bytes(audio_out)


async def probe(conn_factory: ConnFactory | None = None) -> dict:
    """U142/U143: does this account support Realtime, and WITH WHICH MODEL? A
    tiny TEXT-only round-trip against each candidate model; returns the first
    that works (with its name so the owner can pin REALTIME_MODEL), else the
    most informative failure. Never raises."""

    if not os.environ.get("OPENAI_API_KEY"):
        return {"ok": False, "model": _default_realtime_model(), "reason": "no OPENAI_API_KEY set"}
    factory = conn_factory or _default_conn_factory

    # Try the configured model first, then the GA/preview candidates.
    pinned = os.environ.get("REALTIME_MODEL")
    candidates = ([pinned] if pinned else []) + [
        m for m in _MODEL_CANDIDATES if m != pinned]

    last = {"ok": False, "model": candidates[0], "reason": "no candidates"}
    for model in candidates:
        result = await _probe_model(model, factory)
        if result["ok"]:
            result["hint"] = (
                f"Realtime works with '{model}'. "
                + ("" if pinned == model else f"Set REALTIME_MODEL={model} to pin it."))
            return result
        last = result
        # A hard "no access / bad key / quota" won't change per model — stop early.
        if any(w in result["reason"].lower() for w in ("rejected", "quota", "rate-limited")):
            break
    last.setdefault("hint", "Realtime is not usable on this key — see the reason above.")
    last["tried"] = candidates
    return last


async def _probe_model(model: str, factory: ConnFactory) -> dict:
    import asyncio

    async def _run() -> dict:
        got_text = False
        async with factory(model) as conn:
            await conn.session.update(session={
                "type": "realtime", "output_modalities": ["text"]})
            await conn.conversation.item.create(item={
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Say the word ready."}],
            })
            await conn.response.create()
            async for event in conn:
                etype = getattr(event, "type", "")
                if etype in ("response.output_text.delta", "response.text.delta"):
                    got_text = True
                elif etype == "response.done":
                    break
                elif etype == "error":
                    err = getattr(event, "error", "")
                    return {"ok": False, "model": model, "reason": f"api error: {err}"}
        return {"ok": got_text, "model": model,
                "reason": "connected and responded" if got_text else "connected but no response"}

    try:
        return await asyncio.wait_for(_run(), timeout=float(os.environ.get("REALTIME_TURN_TIMEOUT_S", "15")))
    except TimeoutError:
        return {"ok": False, "model": model, "reason": "timed out — model likely not accessible on this key"}
    except Exception as exc:  # noqa: BLE001
        # U144: surface the RAW server close reason (e.g. a websocket close code
        # + reason) so we never guess. The bare exception str often hides it.
        raw = getattr(exc, "reason", None) or str(exc)
        code = getattr(exc, "code", None)
        detail = f"{raw}" + (f" (close {code})" if code else "")
        return {"ok": False, "model": model, "reason": f"{type(exc).__name__}: {detail}"}


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
