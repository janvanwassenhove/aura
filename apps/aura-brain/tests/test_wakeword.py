"""U128: local wake-word — WAV decoding, factory fallback, loop gating."""

from __future__ import annotations

import io
import os
import wave

os.environ.setdefault("LLM_PROVIDER", "echo")

import numpy as np
from aura_brain import wakeword


def _wav(samples: np.ndarray, rate: int = 16_000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return buf.getvalue()


def test_wav_decode_mono_16k() -> None:
    sig = (np.sin(np.linspace(0, 50, 16_000)) * 1000)
    audio = wakeword._wav_to_int16_16k(_wav(sig))
    assert audio is not None and audio.dtype == np.int16 and audio.size == 16_000


def test_wav_decode_resamples_and_downmixes() -> None:
    stereo = np.zeros(8_000 * 2, dtype=np.int16)  # 8000 stereo frames @ 8 kHz = 1 s
    audio = wakeword._wav_to_int16_16k(_wav(stereo, rate=8_000, channels=2))
    assert audio is not None
    assert abs(audio.size - 16_000) < 5  # 1 s downmixed + upsampled 8k→16k


def test_wav_decode_bad_bytes_returns_none() -> None:
    assert wakeword._wav_to_int16_16k(b"not a wav") is None


def test_build_detector_default_is_none() -> None:
    # WAKE_ENGINE defaults to 'stt' → no local detector (keeps STT-fuzzy path).
    assert wakeword.build_detector() is None


def test_build_detector_missing_package_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("WAKE_ENGINE", "openwakeword")
    monkeypatch.setenv("WAKE_MODEL", "definitely-not-installed")
    # openwakeword isn't a test dependency → load fails → graceful None.
    assert wakeword.build_detector() is None
