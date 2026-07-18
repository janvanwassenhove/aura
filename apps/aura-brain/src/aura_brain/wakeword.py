"""U128: local wake-word detection.

Detecting "Richie" by transcribing every audio window over the network
(gpt-4o-mini-transcribe → fuzzy match) is slow and unreliable — Whisper drops
the name on short/noisy clips, and it costs a full round-trip per window.

This runs a lightweight wake-word model LOCALLY (openWakeWord — ONNX on the
CPU) on the captured audio, so:
  * wake is instant and offline (no network hop just to hear the name),
  * speech-to-text only runs AFTER the wake fires, on the real command,
  * (Realtime, U129) the expensive session is opened only after the wake.

Graceful fallback: if the package or a model isn't available, ``build_detector``
returns None and the voice loop keeps its existing transcribe-then-fuzzy path.
Nothing here ever raises into the loop.
"""

from __future__ import annotations

import io
import logging
import os
import wave
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class WakeWordDetector(Protocol):
    def detect(self, wav_bytes: bytes) -> bool: ...


def _wav_to_int16_16k(wav_bytes: bytes) -> np.ndarray | None:
    """Decode WAV → mono int16 @ 16 kHz (what openWakeWord expects)."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError, OSError):
        return None
    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if rate != 16_000 and rate > 0 and audio.size:
        # Cheap linear resample — fine for wake-word features.
        idx = np.linspace(0, audio.size - 1, int(audio.size * 16_000 / rate))
        audio = np.interp(idx, np.arange(audio.size), audio).astype(np.int16)
    return audio


class OpenWakeWordDetector:
    """openWakeWord-backed detector. Loads one model (a built-in name or a
    custom .onnx/.tflite path), returns True when any frame scores over the
    threshold."""

    def __init__(self, model: str, threshold: float = 0.5) -> None:
        from openwakeword.model import Model  # lazy — optional dependency

        self._threshold = threshold
        # A filesystem path → custom model; otherwise a built-in keyword name.
        if os.path.exists(model):
            self._model = Model(wakeword_models=[model])
        else:
            self._model = Model(wakeword_models=[model])
        self._label = model

    def detect(self, wav_bytes: bytes) -> bool:
        audio = _wav_to_int16_16k(wav_bytes)
        if audio is None or audio.size == 0:
            return False
        try:
            self._model.reset()  # per-utterance, independent windows
            best = 0.0
            # openWakeWord wants ~80 ms frames (1280 samples @ 16 kHz).
            for start in range(0, audio.size - 1280 + 1, 1280):
                scores = self._model.predict(audio[start:start + 1280])
                best = max(best, max(scores.values()) if scores else 0.0)
                if best >= self._threshold:
                    return True
            return best >= self._threshold
        except Exception as exc:  # noqa: BLE001 — never break the voice loop
            logger.debug("wake-word inference failed: %s", exc)
            return False


def build_detector() -> WakeWordDetector | None:
    """Return a local detector, or None to keep the transcribe-then-fuzzy path.

    WAKE_ENGINE=openwakeword enables it; WAKE_MODEL picks the model (a built-in
    keyword like 'hey_jarvis' or a path to a custom 'Richie' .onnx). Any import
    or load failure → None (fallback), logged once."""
    if os.environ.get("WAKE_ENGINE", "stt").lower() != "openwakeword":
        return None
    model = os.environ.get("WAKE_MODEL", "hey_jarvis")
    threshold = float(os.environ.get("WAKE_THRESHOLD", "0.5"))
    try:
        detector = OpenWakeWordDetector(model, threshold)
        logger.info("local wake-word active (model=%s, threshold=%.2f)", model, threshold)
        return detector
    except Exception as exc:  # noqa: BLE001 — missing package/model → fallback
        logger.warning(
            "WAKE_ENGINE=openwakeword but the detector could not load (%s) — "
            "falling back to STT wake detection.", exc)
        return None
