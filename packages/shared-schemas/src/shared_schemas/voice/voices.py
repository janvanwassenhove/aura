"""The TTS voices this app may use.

U360: this list lived only in `aura_brain.voice`, so nothing that validated a
scenario could check a voice name — a beat saying `voice: onix` was accepted
and silently ignored. It sits here now because the schema layer is what reads
a scenario, and a second copy of a list like this drifts the first time one of
them is edited.

gpt-4o-mini-tts. Kept as a tuple so it cannot be appended to by accident.
"""

from __future__ import annotations

TTS_VOICES: tuple[str, ...] = (
    "alloy", "ash", "ballad", "coral", "echo", "fable",
    "onyx", "nova", "sage", "shimmer", "verse",
)

#: What the provider accepts. Outside this it refuses the request outright.
SPEED_MIN = 0.25
SPEED_MAX = 4.0
