"""Local Whisper STT + Kokoro/Piper TTS providers (offline fallback)."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

from shared_schemas.voice.providers import STTProvider, TTSProvider

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="local-voice")


class LocalWhisperSTTProvider(STTProvider):
    """Uses the `faster-whisper` or `openai-whisper` library for offline STT."""

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None  # lazy load

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        except ImportError:
            import whisper
            self._model = whisper.load_model(self._model_size)
        return self._model

    def _transcribe_sync(self, audio_bytes: bytes) -> str:
        import tempfile
        model = self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            # faster-whisper
            segments, _ = model.transcribe(tmp_path)
            return " ".join(s.text for s in segments).strip()
        except TypeError:
            # openai-whisper fallback
            result = model.transcribe(tmp_path)
            return result["text"].strip()
        finally:
            os.unlink(tmp_path)

    async def transcribe(self, audio_bytes: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self._transcribe_sync, audio_bytes)

    async def stream_transcribe(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)
        transcript = await self.transcribe(b"".join(chunks))
        async def _single() -> AsyncIterator[str]:
            yield transcript
        return _single()


class KokoroTTSProvider(TTSProvider):
    """Kokoro-based local TTS provider."""

    def __init__(self) -> None:
        self._pipeline = None  # lazy load

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        from kokoro import KPipeline
        self._pipeline = KPipeline(lang_code="a")
        return self._pipeline

    def _synthesize_sync(self, text: str) -> bytes:
        pipeline = self._load_pipeline()
        import io

        import numpy as np
        import soundfile as sf
        generator = pipeline(text, voice="af_heart", speed=1.0)
        audio_chunks = []
        for _, _, audio in generator:
            audio_chunks.append(audio)
        if not audio_chunks:
            return b""
        combined = np.concatenate(audio_chunks)
        buf = io.BytesIO()
        sf.write(buf, combined, 24000, format="WAV")
        return buf.getvalue()

    async def synthesize(self, text: str) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self._synthesize_sync, text)

    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]:
        audio = await self.synthesize(text)
        chunk_size = 4096
        for i in range(0, len(audio), chunk_size):
            yield audio[i : i + chunk_size]
