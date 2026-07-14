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


# U65: available TTS voices (gpt-4o-mini-tts). The default is set globally
# via TTS_VOICE (Settings) and can differ per persona via TTS_VOICE_<MODE>.
TTS_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable",
              "onyx", "nova", "sage", "shimmer", "verse")

_tts_cache: dict[str, object] = {}


def resolve_voice(persona: str | None = None) -> str:
    """The voice for this reply: persona override -> global pref -> alloy."""
    if persona:
        per = os.environ.get(f"TTS_VOICE_{persona.upper()}", "").strip().lower()
        if per in TTS_VOICES:
            return per
    voice = os.environ.get("TTS_VOICE", "alloy").strip().lower()
    return voice if voice in TTS_VOICES else "alloy"


async def synthesize_b64(text: str, voice: str | None = None) -> str | None:
    """Return base64 PCM (s16le mono 24 kHz) for ``text``, or None if TTS is
    unavailable (no key / provider error). ``voice`` defaults to the global
    preference (read live, so the Settings dropdown applies immediately)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    voice = (voice or resolve_voice()).lower()
    if voice not in TTS_VOICES:
        voice = "alloy"
    try:
        provider = _tts_cache.get(voice)
        if provider is None:
            from conversation_runtime.providers.openai_provider import OpenAITTSProvider

            provider = OpenAITTSProvider(
                model=os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"),
                voice=voice,
            )
            _tts_cache[voice] = provider
        pcm = await provider.synthesize(text)
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
        kwargs: dict = {
            "model": os.environ.get("STT_MODEL", "gpt-4o-mini-transcribe"),
            "file": (filename, io.BytesIO(data)),
        }
        lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").lower()
        if lang in ("en", "nl", "fr"):  # bias STT toward the configured language
            kwargs["language"] = lang
        result = await client.audio.transcriptions.create(**kwargs)
        return result.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("transcription failed: %s", exc)
        return None
