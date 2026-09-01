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


def explain_voice(
    persona: str | None = None,
    mode: str | None = None,
    character_voice: str | None = None,
) -> tuple[str, str]:
    """(the voice he will use, where that came from).

    U273: three screens each offer a "Voice" and nothing said which one wins.
    Asked as "the default voice in settings, whats difference in between the
    one selected in robot? how are they used? can we make it more clearer".

    They are, in order of who wins:

      1. **the persona's own voice** (Robot → the persona card). Every
         built-in character ships with one — Friendly Assistant is `coral` —
         so in practice this is nearly always the answer, which is exactly why
         the Settings dropdown looked ignored. It was.
      2. **this mode's voice** (Modes → Voice), when the persona leaves its
         own blank.
      3. **the default voice** (Settings → Voice).
      4. `alloy`.

    The mode voice used to be looked up under the PERSONA's name — the env
    family `TTS_VOICE_<X>` is written by Modes keyed on the mode, and read
    here keyed on the persona. Those agree only while a mode still uses the
    persona named after it, so the moment you gave Home the "Friendly
    Assistant" persona, the voice you set in Modes could never be found again.
    Both keys are consulted now, mode first.
    """
    def ok(v: str | None) -> str:
        v = (v or "").strip().lower()
        return v if v in TTS_VOICES else ""

    if (chosen := ok(character_voice)):
        return chosen, "this persona's own voice"
    if mode and (chosen := ok(os.environ.get(f"TTS_VOICE_{mode.upper()}"))):
        return chosen, f"the voice set for {mode} mode"
    if persona and (chosen := ok(os.environ.get(f"TTS_VOICE_{persona.upper()}"))):
        return chosen, f"the voice set for the {persona} persona"
    if (chosen := ok(os.environ.get("TTS_VOICE"))):
        return chosen, "the default voice in Settings"
    return "alloy", "the built-in default"


def resolve_voice(
    persona: str | None = None,
    mode: str | None = None,
    character_voice: str | None = None,
) -> str:
    """The voice for this reply. See `explain_voice` for the order."""
    return explain_voice(persona, mode, character_voice)[0]


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


_LATIN_LANGS = {"en", "nl", "fr", "de", "es", "it", "pt", "da", "sv", "no", "fi"}

# Windows spells a locale "Dutch_Belgium", POSIX spells it "nl_BE.UTF-8".
_LOCALE_NAMES = {
    "dutch": "nl", "flemish": "nl", "english": "en", "french": "fr",
    "german": "de", "spanish": "es", "italian": "it", "portuguese": "pt",
    "danish": "da", "swedish": "sv", "norwegian": "no", "finnish": "fi",
}


def _language_of(tag: str | None) -> str:
    """A locale name, however the platform spells it, as a language code."""
    head = (tag or "").replace("-", "_").split("_")[0].strip().lower()
    return _LOCALE_NAMES.get(head, head)


def _stt_language() -> str:
    """The language to transcribe in, or "" to let the model decide.

    U287. `multi` is the explicit opt-out for households that genuinely mix
    languages inside one sentence; everything else resolves to a real
    language, because "auto" was costing more than it bought.
    """
    explicit = os.environ.get("STT_LANGUAGE", "").strip().lower()
    if explicit == "multi":
        return ""
    if explicit in _LATIN_LANGS:
        return explicit

    lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").strip().lower()
    if lang == "multi":
        return ""
    if lang in _LATIN_LANGS:
        return lang

    # The machine's own locale before LANGUAGE_FALLBACK, because the two answer
    # DIFFERENT questions. LANGUAGE_FALLBACK (U257) means "when a message is
    # too short to tell, REPLY in this"; the locale is a fact about the person
    # sitting at this computer, which is a far better guess at what is being
    # SPOKEN in the room. On the owner's machine those disagreed — a Dutch
    # Belgian install with the fallback left on French — and pinning the
    # microphone to French would have made the very complaint worse.
    try:
        import locale

        names = [locale.getlocale()[0], os.environ.get("LANG"), os.environ.get("LC_ALL")]
        for tag in names:
            code = _language_of(tag)
            if code in _LATIN_LANGS:
                return code
    except Exception:  # noqa: BLE001 — a locale must never break the mic
        pass

    fallback = os.environ.get("LANGUAGE_FALLBACK", "").strip().lower()[:2]
    return fallback if fallback in _LATIN_LANGS else ""


def _wrong_script(text: str, lang: str) -> bool:
    """True when the transcript is written in an alphabet this language is not.

    Counts LETTERS only: digits, punctuation and emoji say nothing about the
    script, and a Dutch sentence quoting one foreign word should not be thrown
    away — so the test is "mostly", not "any".
    """
    if lang not in _LATIN_LANGS:
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 4:
        return False        # too short to judge; other guards handle these
    latin = sum(1 for c in letters if c.isascii() or "\u00c0" <= c <= "\u024f")
    return latin / len(letters) < 0.5


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
        # `language` breaks mixing Dutch and English in one sentence.
        #
        # U287: but leaving it unpinned means the model re-guesses the language
        # on EVERY clip, and a short or half-caught utterance is exactly where
        # it guesses wrong — "hallo" is equally Dutch and German, and noise
        # comes back as anything at all, including Asian scripts. Reported as
        # "robot vangt soms maar half op wat in het Nederlands gezegd wordt en
        # springt dan naar een andere taal zoals Duits of zelfs Aziatische
        # talen".
        #
        # So `auto` now means "the language of this household" rather than "no
        # idea": the reply language if one is set, else the fallback, else the
        # machine's own locale. True code-switchers set ASSISTANT_LANGUAGE to
        # `multi`, which is the only value that leaves detection wide open.
        stt_lang = _stt_language()
        if stt_lang:
            kwargs["language"] = stt_lang
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
        # U287: a Dutch household does not speak in Han, Cyrillic or Arabic
        # script. When STT returns one it is not a transcript, it is the model
        # inventing words out of television, music or room noise — and the
        # reply that follows is answering nobody. Cheap, deterministic, and it
        # needs no second model.
        if stt_lang and _wrong_script(text, stt_lang):
            logger.info("STT discarded (foreign script for %s): %r", stt_lang, text[:60])
            return None
        # Guard: if STT just echoed our priming words (unclear audio), discard.
        stripped = text.lower().strip(" .,!?").replace(wake.lower(), "").replace(name.lower(), "").strip()
        if not stripped:
            return wake  # treat as bare wake word → the loop re-listens for the command
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("transcription failed: %s", exc)
        return None
