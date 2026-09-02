"""U291: a persona must not delete the language rule.

Reported twice. The second time as "is weer in andere talen aan het spinnen",
with a screenshot of a Dutch conversation answered in Portuguese and Spanish —
after U287 pinned the pipeline's transcription language and U289 pinned the
realtime session's. Both fixes were live in the running process. The reply
language was never the transcription's job.

`build_instructions` read:

    parts = [character_prompt] if character_prompt else [_FALLBACK]

and _FALLBACK held the ONLY sentence about language. So the moment the owner
selected a real persona — Sentinel, in the screenshot — that sentence was
dropped with the fallback it lived in, and the speech model had no language
instruction at all. A persona prompt says who he is, not which language he
speaks; making them exclusive was the bug.
"""

from __future__ import annotations

from aura_brain.voice_context import build_instructions

PERSONA = "You are Sentinel: terse, factual, always scanning."


def test_a_persona_no_longer_replaces_the_language_rule() -> None:
    out = build_instructions(PERSONA, "", "nl")
    assert PERSONA in out, "the persona is still who he is"
    assert "Dutch" in out, "and he is still told which language to answer in"


def test_the_rule_names_the_language_rather_than_listing_four() -> None:
    assert "Dutch" in build_instructions("", "", "nl")
    assert "French" in build_instructions("", "", "fr")


def test_it_tells_him_a_transcript_can_be_wrong() -> None:
    """The whole failure mode: a mis-detected transcript dragged the reply
    into another language. He is told to distrust that, not the speaker."""
    out = build_instructions(PERSONA, "", "nl")
    assert "mis-detect" in out or "mis-hearing" in out
    assert "Never switch" in out


def test_an_unknown_language_still_gets_a_rule() -> None:
    """A household on `multi` has no single answer, but "do not drift" still
    applies — that is what went wrong in the first place."""
    out = build_instructions(PERSONA, "", "")
    assert "Language" in out
    assert "Never switch language" in out


def test_the_person_note_still_comes_last() -> None:
    """U245's ordering: recency helps for who is in the room."""
    out = build_instructions(PERSONA, "Jan, the owner.", "nl")
    assert out.index("## Language") < out.index("## Who you are talking to")


def test_no_persona_and_no_language_still_produces_instructions() -> None:
    out = build_instructions("", "", "")
    assert out.strip(), "a session must never open with empty instructions"
