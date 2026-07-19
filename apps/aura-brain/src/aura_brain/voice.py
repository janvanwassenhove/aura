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


async def synthesize_b64(text: str, voice: str | None = None,
                         speed: float = 1.0) -> str | None:
    """Return base64 PCM (s16le mono 24 kHz) for ``text``, or None if TTS is
    unavailable (no key / provider error). ``voice`` defaults to the global
    preference (read live, so the Settings dropdown applies immediately)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    voice = (voice or resolve_voice()).lower()
    if voice not in TTS_VOICES:
        voice = "alloy"
    try:
        cache_key = f"{voice}@{speed:.2f}"
        provider = _tts_cache.get(cache_key)
        if provider is None:
            from conversation_runtime.providers.openai_provider import OpenAITTSProvider

            provider = OpenAITTSProvider(
                model=os.environ.get("TTS_MODEL", "gpt-4o-mini-tts"),
                voice=voice, speed=speed,
            )
            _tts_cache[cache_key] = provider
        pcm = await provider.synthesize(text)
        return base64.b64encode(pcm).decode()
    except Exception as exc:  # noqa: BLE001 — voice is best-effort, never fatal
        logger.warning("TTS synthesis failed: %s", exc)
        return None


# U135: Whisper reports the language as a full English name ("dutch") or an
# ISO code depending on model/version — accept both spellings.
_LANG_ALIASES = {
    "nl": {"nl", "dutch", "flemish"},
    "en": {"en", "english"},
    "fr": {"fr", "french"},
    "de": {"de", "german"},
    "es": {"es", "spanish"},
    "it": {"it", "italian"},
}


def _allowed_languages() -> set[str]:
    """Household languages. Anything else is treated as a hallucination."""
    raw = os.environ.get("VOICE_LANGUAGES", "nl,en,fr,de")
    return {c.strip().lower() for c in raw.split(",") if c.strip()}


def _reject_reason(result) -> str | None:
    """Why this verbose_json transcript should be discarded, or None to keep."""
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        return "empty"

    detected = str(getattr(result, "language", "") or "").strip().lower()
    if detected:
        allowed = _allowed_languages()
        codes = {code for code, names in _LANG_ALIASES.items() if detected in names}
        code = next(iter(codes), detected)
        if code not in allowed:
            return f"language {detected!r} not in {sorted(allowed)}"

    # Classic Whisper hallucination signature: it "hears" speech in silence.
    segments = getattr(result, "segments", None) or []
    probs, logps = [], []
    for seg in segments:
        ns = getattr(seg, "no_speech_prob", None)
        lp = getattr(seg, "avg_logprob", None)
        if ns is None and isinstance(seg, dict):
            ns, lp = seg.get("no_speech_prob"), seg.get("avg_logprob")
        if ns is not None:
            probs.append(float(ns))
        if lp is not None:
            logps.append(float(lp))
    if probs:
        max_ns = float(os.environ.get("STT_MAX_NO_SPEECH", "0.6"))
        if sum(probs) / len(probs) > max_ns:
            return f"no_speech_prob {sum(probs) / len(probs):.2f}"
    if logps:
        min_lp = float(os.environ.get("STT_MIN_LOGPROB", "-1.0"))
        if sum(logps) / len(logps) < min_lp:
            return f"avg_logprob {sum(logps) / len(logps):.2f}"
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
        # U130: multilingual (NL/EN/FR/DE) + code-switching. Forcing a single
        # `language` breaks mixing Dutch and English in one sentence, so only
        # pin it when the owner explicitly picked ONE language; otherwise let
        # the model auto-detect (empty/"auto"/"multi" → no language pin).
        lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").lower()
        if lang in ("en", "nl", "fr", "de", "es", "it"):
            kwargs["language"] = lang
        # U145: the U135 hallucination gate is now OPT-IN. It swapped the auto
        # path to whisper-1 (for its verbose_json no-speech/language signals),
        # but whisper-1 is markedly worse than gpt-4o-mini-transcribe and
        # returned EMPTY transcripts on real robot-mic audio — so Richie never
        # heard a command. Keep the good model by default; only use the
        # verbose_json gate when STT_HALLUCINATION_GATE=true. The wake-word
        # requirement + echo/music guards are the primary defence against the
        # foreign-language loop.
        elif os.environ.get("STT_HALLUCINATION_GATE", "false").lower() == "true":
            kwargs["model"] = os.environ.get("STT_AUTO_MODEL", "whisper-1")
            kwargs["response_format"] = "verbose_json"
        # U87/U89: prime STT with the wake word/name as bare VOCABULARY tokens
        # (not a sentence — a sentence gets echoed back verbatim on unclear
        # audio, which the LLM then answers, U89). A short word list only
        # biases spelling of the name.
        name = os.environ.get("ASSISTANT_NAME", "AURA")
        wake = os.environ.get("WAKE_WORD", name)
        kwargs["prompt"] = f"{wake} {name}"
        result = await client.audio.transcriptions.create(**kwargs)
        # U135: hallucination gate — only for the auto path, where we asked for
        # verbose_json and therefore have the detection signals.
        if kwargs.get("response_format") == "verbose_json":
            reason = _reject_reason(result)
            if reason:
                logger.info("STT discarded (%s): %r", reason, (result.text or "")[:60])
                return None
        text = (result.text or "").strip()
        # Guard: if STT just echoed our priming words (unclear audio), discard.
        stripped = text.lower().strip(" .,!?").replace(wake.lower(), "").replace(name.lower(), "").strip()
        if not stripped:
            return wake  # treat as bare wake word → the loop re-listens for the command
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("transcription failed: %s", exc)
        return None
