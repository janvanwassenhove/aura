"""What the Realtime speech path is told about the room — U245.

The turn pipeline assembles a system prompt per turn: persona, live context,
skills, and — via the judgment layer — a note saying who is standing there and
the handful of facts the assistant is allowed to know about them.

The Realtime path does not call the pipeline. It opens a socket to the speech
model and hands it ``instructions``, and those instructions were the character
prompt and nothing else. So the owner was greeted by name (the greeting runs
through the pipeline) and then, thirty seconds later, told by the same robot
that it had no memory of who anyone is. Both answers were honest; they came
from two different places, one of which knew nothing.

This module is the join. It is deliberately a pure function on strings: what
goes into a speech session is exactly what the tests can read back.
"""

from __future__ import annotations

_FALLBACK = (
    "You are a friendly robot assistant. Keep spoken replies concise."
)

# U291: the language rule is its own block now, and it is ALWAYS added.
#
# It used to live inside _FALLBACK, and _FALLBACK was only used when the
# persona had no prompt of its own — so the moment the owner picked a real
# persona (Sentinel, Host, …), the one instruction about language vanished
# with it. The speech model was then free to answer a mis-heard Dutch sentence
# in Spanish or Portuguese, which is exactly what it did. Reported twice, the
# second time as "is weer in andere talen aan het spinnen".
_LANGUAGES = {"en": "English", "nl": "Dutch", "fr": "French", "de": "German",
              "es": "Spanish", "it": "Italian", "pt": "Portuguese"}


def _language_rule(language: str) -> str:
    """What to say about language — named when we know it, guided when not."""
    name = _LANGUAGES.get((language or "").strip().lower()[:2])
    if name:
        return (
            f"## Language\n"
            f"ALWAYS reply in {name}, whatever language the transcript appears "
            f"to be in. Speech-to-text sometimes mis-detects a short or noisy "
            f"utterance; when that happens the transcript is wrong, not the "
            f"speaker. Never switch languages on your own. If you genuinely "
            f"could not make out what was said, say so in {name} and ask them "
            f"to repeat."
        )
    return (
        "## Language\n"
        "Reply in the language the user is speaking. Never switch language on "
        "your own; if a transcript looks like a different language than the "
        "conversation so far, treat it as a mis-hearing and stay in the "
        "language you were using."
    )


def build_instructions(character_prompt: str, person_note: str,
                       language: str = "") -> str:
    """Instructions for a realtime turn or session.

    Character voice first — it is the longer, more stable block, and the model
    reads it as who it is. The person note goes last, where recency helps, and
    is labelled so the model treats it as fact about the room rather than as
    something the user claimed.

    Either half may be empty. With neither, a plain fallback keeps a session
    from opening with no instructions at all.
    """
    parts = [character_prompt.strip()] if character_prompt.strip() else [_FALLBACK]
    # U291: never an either/or with the persona — a character prompt says who
    # he is, not which language he speaks.
    parts.append(_language_rule(language))
    note = person_note.strip()
    if note:
        parts.append(
            "## Who you are talking to\n"
            f"{note}\n"
            "This is what you already know about them from earlier — it is "
            "yours, not something they just told you. Use it naturally; do not "
            "recite it, and never claim you cannot remember anything about "
            "them."
        )
    return "\n\n".join(parts)
