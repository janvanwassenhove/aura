"""U349: several voices inside one spoken line.

A beat carries a `persona`, and that persona's voice speaks the whole beat.
Inside the text, `[persona:some_id]` hands the line to somebody else from that
point on and `[persona]` (or `[/persona]`) hands it back — so a single line can
be a small exchange between two characters rather than one uninterrupted voice.

This layer is deliberately ignorant of WHO those personas are: characters live
in the brain, with their own voice, speed and prompt. Here a persona is just an
id carried alongside a piece of text. That split is what lets the parsing be a
pure function with no filesystem, no store and no network in it.

Two rules the design turns on:

  - **A marker is never spoken.** A marker that survives into a segment is a
    line that reads "bracket persona colon kids" out loud in front of an
    audience.
  - **A marker that is nearly right is an error, not prose.** `[persona:]` does
    not match the marker grammar, so without a second, looser pattern it would
    quietly fall through as text and be read out. `persona_marker_problem`
    exists to catch that at authoring time, on the presenter's screen, where a
    typo is still cheap.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# What a persona id may look like — the brain stores characters as
# `<id>.json`, so the id is a filename stem, not a sentence.
PERSONA_ID = re.compile(r"^[A-Za-z0-9_.\-]+$")

# Anything that OPENS like a persona marker. Deliberately sloppy: its whole job
# is to notice the near-misses that the strict pattern below rejects, so they
# can be reported instead of spoken. It still requires the bracket to begin
# with the word itself, so ordinary prose that merely mentions a persona
# ("[de persona van de robot]") is left alone.
_LOOSE = re.compile(r"\[\s*/?\s*persona\b[^\]]*\]", re.IGNORECASE)

# ...and the ones that are actually well formed.
_MARKER = re.compile(
    r"\[\s*(?P<close>/?)\s*persona\s*(?::\s*(?P<id>[A-Za-z0-9_.\-]+)\s*)?\]",
    re.IGNORECASE,
)


class VoiceSegment(BaseModel):
    """One stretch of a line, and who says it.

    `persona` empty means "whoever the beat was already using" — which is
    itself allowed to be empty, meaning the presentation's own voice.
    """

    text: str = ""
    persona: str = ""


def persona_marker_problem(text: str) -> str:
    """Describe the first malformed persona marker in *text*, or "" if fine.

    The sentence is written to be shown to the presenter as-is (the scenario
    API turns validation errors into one readable line), so it says what to
    type rather than what the parser expected.
    """
    for raw in _LOOSE.findall(text or ""):
        match = _MARKER.fullmatch(raw)
        if match is None:
            return (f"{raw} is not a persona marker — write [persona:some_id] "
                    f"to switch voice, [persona] to switch back")
        if match.group("close") and match.group("id"):
            return (f"{raw} closes a persona, so it takes no id — "
                    f"write [persona] or [/persona]")
    return ""


def split_persona_segments(text: str, default_persona: str = "") -> list[VoiceSegment]:
    """Cut *text* into consecutive segments, one per persona in play.

    Neighbouring segments of the same persona are merged: two markers in a row
    naming one persona should be one TTS call and one uninterrupted delivery,
    not an audible seam in the middle of a sentence.
    """
    text = text or ""
    segments: list[VoiceSegment] = []

    def push(chunk: str, persona: str) -> None:
        chunk = chunk.strip()
        if not chunk:
            return
        if segments and segments[-1].persona == persona:
            segments[-1] = VoiceSegment(
                text=f"{segments[-1].text} {chunk}", persona=persona)
            return
        segments.append(VoiceSegment(text=chunk, persona=persona))

    current = default_persona
    pos = 0
    for match in _MARKER.finditer(text):
        push(text[pos:match.start()], current)
        # A closing marker — and an id-less `[persona]`, which people write for
        # the same reason — returns the line to the beat's own persona.
        current = (default_persona
                   if match.group("close") or not match.group("id")
                   else match.group("id"))
        pos = match.end()
    push(text[pos:], current)
    return segments


def personas_used(text: str, default_persona: str = "") -> list[str]:
    """Every distinct persona a line calls for, in the order it first speaks.

    The console uses this to check a scenario's markers against the characters
    that actually exist, while the presenter is still at a desk.
    """
    seen: list[str] = []
    for segment in split_persona_segments(text, default_persona):
        if segment.persona and segment.persona not in seen:
            seen.append(segment.persona)
    return seen
