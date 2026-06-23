"""Null STT/TTS providers — no models, no network.

For text-first / Realtime-first operation (and tests): the conversation runtime
can be mounted without loading local Whisper/Kokoro. STT returns empty text;
TTS returns empty audio. Selected via STT_PROVIDER=null / TTS_PROVIDER=null.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from shared_schemas.voice.providers import STTProvider, TTSProvider


class NullSTTProvider(STTProvider):
    async def transcribe(self, audio_bytes: bytes) -> str:
        return ""

    async def stream_transcribe(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        async for _ in audio_stream:
            pass

        async def _empty() -> AsyncIterator[str]:
            if False:  # pragma: no cover - yields nothing
                yield ""

        return _empty()


class NullTTSProvider(TTSProvider):
    async def synthesize(self, text: str) -> bytes:
        return b""

    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]:
        if False:  # pragma: no cover - yields nothing
            yield b""
