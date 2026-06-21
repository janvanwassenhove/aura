"""OpenAI Realtime STT/TTS provider (~300 ms latency)."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from shared_schemas.voice.providers import STTProvider, TTSProvider

logger = logging.getLogger(__name__)

_DEFAULT_STT_MODEL = "whisper-1"
_DEFAULT_TTS_MODEL = "tts-1"
_DEFAULT_TTS_VOICE = "alloy"


class OpenAISTTProvider(STTProvider):
    """Whisper-based STT via OpenAI API."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_STT_MODEL) -> None:
        self._client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model

    async def transcribe(self, audio_bytes: bytes) -> str:
        import io
        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
        )
        return response.text

    async def stream_transcribe(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        # OpenAI does not expose a streaming transcription REST endpoint —
        # buffer all chunks and transcribe in one call.
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)
        transcript = await self.transcribe(b"".join(chunks))
        async def _single() -> AsyncIterator[str]:
            yield transcript
        return _single()


class OpenAITTSProvider(TTSProvider):
    """TTS via OpenAI API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_TTS_MODEL,
        voice: str = _DEFAULT_TTS_VOICE,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        response = await self._client.audio.speech.create(
            model=self._model,
            voice=self._voice,  # type: ignore[arg-type]
            input=text,
            response_format="pcm",
        )
        return response.content

    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]:
        async with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=self._voice,  # type: ignore[arg-type]
            input=text,
            response_format="pcm",
        ) as resp:
            async for chunk in resp.iter_bytes(chunk_size=4096):
                yield chunk
