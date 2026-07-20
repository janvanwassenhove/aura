"""U129: wake-gated Realtime turn + cost meter (fake connection, no network)."""

from __future__ import annotations

import base64
import io
import os
import wave

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
import pytest
from aura_brain import realtime_voice
from aura_brain.realtime_voice import CostMeter, run_realtime_turn, wav_to_pcm24k


def _wav(rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes((np.zeros(rate // 2)).astype(np.int16).tobytes())
    return buf.getvalue()


# ------------------------------------------------------------------
# Cost meter
# ------------------------------------------------------------------

def test_cost_meter_accumulates_and_prices() -> None:
    m = CostMeter()
    m.add({"input_token_details": {"audio_tokens": 1_000_000, "text_tokens": 0},
           "output_token_details": {"audio_tokens": 0, "text_tokens": 0}})
    # 1M audio-in tokens at the default $10/M → ~$10.
    assert m.turns == 1
    assert m.spent_usd() == pytest.approx(10.0, abs=0.01)
    assert m.summary()["audio_in_tokens"] == 1_000_000


def test_cost_meter_ignores_empty_usage() -> None:
    m = CostMeter()
    m.add(None)
    assert m.turns == 0 and m.spent_usd() == 0.0


# ------------------------------------------------------------------
# WAV → 24k PCM
# ------------------------------------------------------------------

def test_wav_to_pcm24k_resamples() -> None:
    pcm = wav_to_pcm24k(_wav(16_000))
    assert pcm is not None
    # 0.5 s @ 24 kHz mono int16 → ~12000 samples * 2 bytes.
    assert abs(len(pcm) - 24_000) < 40
    assert wav_to_pcm24k(b"junk") is None


# ------------------------------------------------------------------
# Realtime turn against a fake connection
# ------------------------------------------------------------------

class _Ev:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeConn:
    """Minimal stand-in for the OpenAI Realtime async connection."""

    def __init__(self, events):
        self._events = events
        import types as _t
        self.session = _t.SimpleNamespace(update=self._noop)
        self.input_audio_buffer = _t.SimpleNamespace(append=self._noop, commit=self._noop)
        self.conversation = _t.SimpleNamespace(item=_t.SimpleNamespace(create=self._noop))
        self.response = _t.SimpleNamespace(create=self._noop)

    async def _noop(self, *a, **k): ...
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    async def __aiter__(self):
        for e in self._events:
            yield e


async def test_run_realtime_turn_collects_audio_and_usage() -> None:
    audio = base64.b64encode(b"\x01\x02" * 100).decode()
    events = [
        _Ev("response.audio_transcript.delta", delta="Hallo "),
        _Ev("response.audio_transcript.delta", delta="Jan"),
        _Ev("response.audio.delta", delta=audio),
        _Ev("response.done", response=type("R", (), {"usage": {
            "input_token_details": {"audio_tokens": 500},
            "output_token_details": {"audio_tokens": 800},
        }})()),
    ]
    meter = CostMeter()
    text, out = await run_realtime_turn(
        b"\x00" * 100, conn_factory=lambda model: _FakeConn(events), meter=meter)
    assert text == "Hallo Jan"
    assert out == b"\x01\x02" * 100
    assert meter.turns == 1 and meter.audio_out == 800


async def test_run_realtime_turn_streams_segments(monkeypatch) -> None:
    # U153: with a small segment size, audio deltas are flushed to on_segment
    # as they arrive (streaming playback) and the tail is flushed at the end.
    monkeypatch.setenv("REALTIME_SEGMENT_MS", "1")  # 1 ms @ 24 kHz*2B ≈ 48 bytes
    chunk = base64.b64encode(b"\x01\x02" * 50).decode()  # 100 bytes ≥ threshold
    events = [
        _Ev("response.audio.delta", delta=chunk),
        _Ev("response.audio.delta", delta=base64.b64encode(b"\x03" * 10).decode()),
        _Ev("response.done", response=type("R", (), {"usage": {}})()),
    ]
    segments: list[bytes] = []

    async def _on_segment(seg: bytes) -> None:
        segments.append(seg)

    _, out = await run_realtime_turn(
        b"\x00" * 10, conn_factory=lambda m: _FakeConn(events), on_segment=_on_segment)
    # First delta (100 B) flushed as a full segment; the 10 B tail flushed after.
    assert len(segments) == 2
    assert segments[0] == b"\x01\x02" * 50
    assert segments[1] == b"\x03" * 10
    assert out == b"\x01\x02" * 50 + b"\x03" * 10  # full buffer still returned


async def test_run_realtime_turn_raises_on_error_event() -> None:
    events = [_Ev("error", error="boom")]
    with pytest.raises(RuntimeError):
        await run_realtime_turn(b"\x00" * 10, conn_factory=lambda m: _FakeConn(events))


def test_realtime_enabled_gates_on_engine_and_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VOICE_ENGINE", "realtime")
    assert realtime_voice.realtime_enabled() is False  # no key
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert realtime_voice.realtime_enabled() is True
    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    assert realtime_voice.realtime_enabled() is False  # default engine


# ------------------------------------------------------------------
# U142: Realtime access self-check
# ------------------------------------------------------------------

class _ProbeConn(_FakeConn):
    def __init__(self, events):
        super().__init__(events)
        import types as _t
        self.conversation = _t.SimpleNamespace(item=_t.SimpleNamespace(create=self._noop))


async def test_probe_reports_success(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    events = [_Ev("response.text.delta", delta="ready"), _Ev("response.done")]
    r = await realtime_voice.probe(conn_factory=lambda m: _ProbeConn(events))
    assert r["ok"] is True and "responded" in r["reason"]


async def test_probe_reports_api_error(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    events = [_Ev("error", error="model_not_found")]
    r = await realtime_voice.probe(conn_factory=lambda m: _ProbeConn(events))
    assert r["ok"] is False and "model_not_found" in r["reason"]


async def test_probe_without_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = await realtime_voice.probe()
    assert r["ok"] is False and "OPENAI_API_KEY" in r["reason"]
