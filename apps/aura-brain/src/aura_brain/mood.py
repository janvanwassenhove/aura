"""U111: emotion & mimicry — read the tone of a reply, express it with the body.

Richie's head and antennas convey mood while he speaks: perky when pleased,
drooped when apologetic, tilted when curious, leaning in when attentive. This
module maps a reply's text to one of a few moods with a cheap keyword/punctuation
heuristic (no extra LLM call — speech latency matters), and names the matching
robot motion. The poses themselves live in the robot adapter (motion_id
``mood_<name>``); unknown ids there degrade to a gentle nod, so this is safe
even before the poses are tuned on hardware.
"""

from __future__ import annotations

import re

# Mood → robot motion_id (poses defined in the reachy adapter).
MOODS = ("excited", "happy", "apologetic", "curious", "attentive", "neutral")

# Substring cues, checked in priority order. Kept short and bilingual (NL/EN)
# because Richie is used in both; extend freely.
_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("apologetic", (
        "sorry", "excuse", "excuus", "spijt", "helaas", "jammer", "mislukt",
        "mislukking", "kon niet", "kan niet", "lukte niet", "fout", "foutmelding",
        "error", "failed", "mis", "slecht nieuws", "afraid", "unfortunately",
    )),
    ("excited", (
        "wauw", "wow", "geweldig", "fantastisch", "amazing", "awesome",
        "yes!", "jippie", "hoera", "eindelijk", "can't wait", "zo cool",
    )),
    ("happy", (
        "gelukt", "top", "super", "mooi", "leuk", "prima", "perfect", "great",
        "done", "success", "klaar", "voila", "voilà", "gefeliciteerd", "proficiat",
        ":)", ":-)", "😄", "😊", "🎉",
    )),
    ("attentive", (
        "even kijken", "even zoeken", "moment", "laat me", "let me", "ik kijk",
        "ik zoek", "checking", "one sec", "ogenblik", "seconde",
    )),
]


def detect_mood(text: str) -> str:
    """Classify the emotional tone of a reply into one of MOODS."""
    t = (text or "").lower().strip()
    if not t:
        return "neutral"
    cues = dict(_CUES)
    # Apologetic always wins — "sorry" outranks any upbeat punctuation.
    if any(c in t for c in cues["apologetic"]):
        return "apologetic"
    # Strong emphasis (double bang) reads as excited even over happy keywords.
    if t.count("!") >= 2:
        return "excited"
    for mood in ("excited", "happy", "attentive"):
        if any(c in t for c in cues[mood]):
            return mood
    # Punctuation fallbacks: single exclamation → happy; a question → curious.
    if t.endswith("!"):
        return "happy"
    if t.endswith("?") or re.search(r"\bbenieuwd\b|\bwonder\b|\binteress", t):
        return "curious"
    return "neutral"


def mood_motion(mood: str) -> str | None:
    """Robot motion_id for a mood, or None when there's nothing to express."""
    if mood in ("neutral", "") or mood not in MOODS:
        return None
    return f"mood_{mood}"
