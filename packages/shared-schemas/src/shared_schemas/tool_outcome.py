"""A tool answered, and the thing still did not happen — U247.

Two capabilities in this system routinely return a successful HTTP 200 with a
paragraph of prose explaining that they could not do the job: the music
connector without a Spotify token, and ``use_computer`` without its backend
installed. The prose is good — the model reads it and behaves honestly — but
the model is the ONLY reader. To the event log, to the skill observations and
to the self-optimizing loop, those calls look exactly like successes.

So the loop that is supposed to learn from failure never sees one. A skill can
die at the same step twenty times and its usage evidence records twenty uses,
all apparently fine.

This is the machine-readable half. The prose stays exactly as it is — it is
what makes the assistant's reply honest — and gets a token in front of it that
anything above the tool can classify on. One place defines the token, one
function reads it, and the whole point is that it is greppable rather than
guessed at from wording that will be reworded.
"""

from __future__ import annotations

# Deliberately shouty and deliberately not a normal word: it must survive a
# model paraphrasing the sentence around it, and never match ordinary prose.
UNAVAILABLE = "CAPABILITY_UNAVAILABLE"


def mark_unavailable(capability: str, message: str) -> str:
    """Prefix a tool result that explains why nothing happened.

    ``capability`` is the thing that was missing (``use_computer``, ``music``),
    not the tool that was called — several tools can fail on one absent
    capability, and it is the capability the owner has to go and fix.
    """
    return f"{UNAVAILABLE}:{capability} {message}"


def unavailable_capability(result: str) -> str | None:
    """The capability named by a marked result, or None for a normal one."""
    if not result:
        return None
    idx = result.find(UNAVAILABLE + ":")
    if idx < 0:
        return None
    rest = result[idx + len(UNAVAILABLE) + 1:]
    name = rest.split(None, 1)[0] if rest.split(None, 1) else ""
    return name.strip(".,:;") or None


def unavailable_capabilities(results) -> list[str]:
    """Every capability that came back unavailable in a round of tool results.

    Accepts the OpenAI-shaped ``{"role": "tool", "content": ...}`` messages the
    pipeline already builds, or plain strings.
    """
    found: list[str] = []
    for item in results or []:
        text = item.get("content", "") if isinstance(item, dict) else str(item)
        name = unavailable_capability(text)
        if name:
            found.append(name)
    return found
