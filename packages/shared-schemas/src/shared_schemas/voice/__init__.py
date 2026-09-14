"""Voice package exports."""

from shared_schemas.voice.providers import STTProvider, TTSProvider
from shared_schemas.voice.voices import SPEED_MAX, SPEED_MIN, TTS_VOICES

__all__ = ["STTProvider", "TTSProvider", "TTS_VOICES", "SPEED_MIN", "SPEED_MAX"]
