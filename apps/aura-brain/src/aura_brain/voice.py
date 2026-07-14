"""Brain-side TTS (U36b): text → PCM for the robot's speaker.

The brain synthesizes (it holds the API key); the robot only plays bytes.
Uses the conversation-runtime OpenAI TTS provider (PCM s16le mono @ 24 kHz).
Returns None when no key is configured — callers degrade to text-only.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_tts: Any = None  # cached provider


async def synthesize_b64(text: str) -> str | None:
    """Return base64 PCM (s16le mono 24 kHz) for ``text``, or None if TTS is
    unavailable (no key / provider error)."""
    global _tts
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        if _tts is None:
            from conversation_runtime.providers.openai_provider import OpenAITTSProvider

            _tts = OpenAITTSProvider(
                model=os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"),
                voice=os.environ.get("TTS_VOICE", "alloy"),
            )
        pcm = await _tts.synthesize(text)
        return base64.b64encode(pcm).decode()
    except Exception as exc:  # noqa: BLE001 — voice is best-effort, never fatal
        logger.warning("TTS synthesis failed: %s", exc)
        return None


async def transcribe(data: bytes, filename: str = "audio.webm") -> str | None:
    """Speech → text via OpenAI (U36e voice input). None when unavailable."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        import io

        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        result = await client.audio.transcriptions.create(
            model=os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe"),
            file=(filename, io.BytesIO(data)),
        )
        return result.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("transcription failed: %s", exc)
        return None
