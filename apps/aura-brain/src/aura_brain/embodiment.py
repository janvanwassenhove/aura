"""U36: map reply content to a robot gesture — the 'emotion' of the answer.

Deliberately simple keyword/punctuation heuristics (no extra LLM call, no
latency): greetings wave, questions tilt, excitement gestures, everything
else gets an affirming nod.

U51: the persona's GestureProfile (shared-personas) shapes HOW embodied a reply
is per mode — silent_desk stays fully still and mute, work keeps a restrained
nod, presentation/demo gesture expressively. ``embodiment_plan`` combines the
content-based gesture with the active persona's profile.
"""

from __future__ import annotations

from typing import Any

_GREETING_WORDS = (
    "hello", "hi ", "hi!", "hey", "welcome", "good morning", "good afternoon",
    "good evening", "goodbye", "bye", "see you",
    "hallo", "dag ", "goedemorgen", "goedemiddag", "goedenavond", "tot ziens",
)
_EXCITED_WORDS = (
    "great", "awesome", "amazing", "fantastic", "congrat", "well done", "wow",
    "geweldig", "super", "fantastisch", "proficiat", "goed gedaan",
)
_SAD_WORDS = (
    "sorry", "unfortunately", "afraid", "sadly", "can't", "cannot", "failed",
    "helaas", "jammer", "spijt",
)


def gesture_for(text: str) -> str:
    """Pick a motion_id for a spoken reply."""
    t = text.lower()
    if any(w in t for w in _GREETING_WORDS):
        return "wave"
    if any(w in t for w in _EXCITED_WORDS) or text.count("!") >= 2:
        return "gesture"
    if any(w in t for w in _SAD_WORDS):
        return "tilt"
    if t.rstrip().endswith("?"):
        return "tilt"
    return "nod"


def embodiment_plan(text: str, persona_config: Any | None) -> tuple[bool, str | None, float]:
    """(speak, motion_id | None, amplitude) for a reply under the active persona.

    - ``voice_style == "silent"`` (silent_desk) → don't speak.
    - The persona's ``gesture_profile.motion_ids`` acts as an allow-list: a
      content gesture outside it falls back to the persona's signature motion
      (work only nods; presentation gestures big). Empty list / amplitude 0 →
      no gesture at all.
    - No persona config (robot-only setups, tests) → speak with default nod.
    """
    if persona_config is None:
        return True, gesture_for(text), 0.5
    speak = getattr(persona_config, "voice_style", "") != "silent"
    profile = getattr(persona_config, "gesture_profile", None)
    if profile is None or profile.amplitude <= 0.0 or not profile.motion_ids:
        return speak, None, 0.0
    gesture = gesture_for(text)
    if gesture not in profile.motion_ids:
        gesture = profile.motion_ids[0]
    return speak, gesture, float(profile.amplitude)
