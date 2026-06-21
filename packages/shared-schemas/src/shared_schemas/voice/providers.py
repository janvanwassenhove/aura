"""STT and TTS provider abstract base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class STTProvider(ABC):
    """Speech-to-text provider contract.

    Implementations: OpenAIRealtimeSTT, LocalWhisperSTT.
    """

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe a complete audio buffer (16kHz 16-bit mono PCM).

        Returns the transcription as a string. Returns empty string for silence.
        """

    @abstractmethod
    async def stream_transcribe(
        self, audio_stream: AsyncIterator[bytes]
    ) -> AsyncIterator[str]:
        """Stream audio chunks and yield partial/final transcriptions."""


class TTSProvider(ABC):
    """Text-to-speech provider contract.

    Implementations: OpenAIRealtimeTTS, KokoroTTS, PiperTTS.
    """

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesise text to WAV bytes."""

    @abstractmethod
    async def stream_synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Stream WAV audio chunks for the given text."""
