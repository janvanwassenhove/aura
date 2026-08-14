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
    "You are a friendly robot assistant. Reply in the language the user speaks "
    "(Dutch, English, French or German). Keep spoken replies concise."
)


def build_instructions(character_prompt: str, person_note: str) -> str:
    """Instructions for a realtime turn or session.

    Character voice first — it is the longer, more stable block, and the model
    reads it as who it is. The person note goes last, where recency helps, and
    is labelled so the model treats it as fact about the room rather than as
    something the user claimed.

    Either half may be empty. With neither, a plain fallback keeps a session
    from opening with no instructions at all.
    """
    parts = [character_prompt.strip()] if character_prompt.strip() else [_FALLBACK]
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
