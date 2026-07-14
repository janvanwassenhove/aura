"""U36: map reply content to a robot gesture — the 'emotion' of the answer.

Deliberately simple keyword/punctuation heuristics (no extra LLM call, no
latency): greetings wave, questions tilt, excitement gestures, everything
else gets an affirming nod.
"""

from __future__ import annotations

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
