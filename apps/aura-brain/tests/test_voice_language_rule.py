"""U291/U292: he must know which language to speak — and nothing more.

U291 fixed a real bug: `build_instructions` chose between the persona prompt
and a fallback, and the ONLY sentence about language lived in that fallback,
so picking a persona (Sentinel) deleted it and the speech model answered Dutch
in Portuguese.

U292 fixed the fix. The rule I wrote explained that "speech-to-text sometimes
mis-detects a short or noisy utterance; when that happens the transcript is
wrong, not the speaker", and offered a closing line to use when he could not
make something out. That was written for a model READING a transcript. This
one HEARS. Told that a transcript existed and could be wrong, it concluded
there was a transcription step it could redo, and narrated it — twenty-odd
times in a row:

    "Laat me even naar het fragment luisteren."
    "Momentje, ik haal de transcriptie op."
    "Sorry, ik ga nu echt de transcriptie uitvoeren."

before producing my scripted apology almost verbatim. Reported as "hij blijft
continue praten, zonder duidelijke reden".

So these tests pin both halves: the language rule always survives a persona,
and it never describes machinery he cannot reach or hands him a line to stall
with.
"""

from __future__ import annotations

from aura_brain.voice_context import build_instructions

PERSONA = "You are Sentinel: terse, factual, always scanning."


# --------------------------------------------------------------------------- #
# U291: a persona must not delete the language rule
# --------------------------------------------------------------------------- #

def test_a_persona_no_longer_replaces_the_language_rule() -> None:
    out = build_instructions(PERSONA, "", "nl")
    assert PERSONA in out, "the persona is still who he is"
    assert "Dutch" in out, "and he is still told which language to speak"


def test_the_rule_names_the_language() -> None:
    assert "Speak Dutch." in build_instructions("", "", "nl")
    assert "Speak French." in build_instructions("", "", "fr")


def test_an_unknown_language_still_forbids_drifting() -> None:
    """A household on `multi` has no single answer, but "do not drift" is
    exactly what went wrong and still applies."""
    out = build_instructions(PERSONA, "", "")
    assert "never switch" in out.lower()


def test_the_person_note_still_comes_last() -> None:
    """U245's ordering: recency helps for who is in the room."""
    out = build_instructions(PERSONA, "Jan, the owner.", "nl")
    assert out.index("## Language") < out.index("## Who you are talking to")


def test_no_persona_and_no_language_still_produces_instructions() -> None:
    assert build_instructions("", "", "").strip(), "a session must never open empty"


# --------------------------------------------------------------------------- #
# U292: never describe machinery he cannot reach
# --------------------------------------------------------------------------- #

def test_it_never_mentions_transcripts_or_hearing_machinery() -> None:
    """The exact words that sent him looking for a transcription step."""
    for language in ("nl", "fr", ""):
        out = build_instructions(PERSONA, "Jan, the owner.", language).lower()
        for word in ("transcript", "speech-to-text", "mis-detect", "mis-hearing",
                     "listen again", "audio"):
            assert word not in out, f"{word!r} describes machinery he cannot reach"


def test_it_hands_him_no_sentence_to_stall_with() -> None:
    """He produced my scripted apology almost verbatim, twenty-odd times. A
    line offered is a line used."""
    out = build_instructions(PERSONA, "", "nl").lower()
    assert "say so" not in out
    assert "ask them to repeat" not in out


def test_it_forbids_narrating_instead_of_answering() -> None:
    """The failure was announcing work rather than doing it."""
    out = build_instructions(PERSONA, "", "nl").lower()
    assert "never announce" in out
    assert "narrate" in out


def test_the_rule_stays_short() -> None:
    """Every extra sentence about how he works is another thing to act out."""
    out = build_instructions("", "", "nl")
    rule = out.split("## Language and delivery", 1)[1]
    assert len(rule) < 400, "a delivery rule is not a manual"
