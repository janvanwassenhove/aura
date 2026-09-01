"""U287: he must hear Dutch as Dutch, and ignore the television.

Reported as two things that turn out to share a cause:

  * "robot vangt soms maar half op wat in het Nederlands gezegd wordt en
    springt dan naar een andere taal zoals Duits of zelfs Aziatische talen"
  * "soms wordt er op de achtergrond onnozel gedaan of speelt televisie, hij
    zou daar niet mogen op reageren"

Speech-to-text re-guessed the language on EVERY clip, because `auto` meant "no
language pin". A short or half-caught utterance is exactly where that guess
goes wrong — "hallo" is equally Dutch and German — and room noise comes back
as whatever the model finds most likely, including scripts nobody in the house
writes in.
"""

from __future__ import annotations

import pytest
from aura_brain.voice import _language_of, _stt_language, _wrong_script


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("STT_LANGUAGE", "ASSISTANT_LANGUAGE", "LANGUAGE_FALLBACK", "LANG", "LC_ALL"):
        monkeypatch.delenv(var, raising=False)
    # Locale must not leak in from the machine running the suite.
    monkeypatch.setattr("locale.getlocale", lambda *a: (None, None))


def test_an_explicit_language_wins(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "fr")
    assert _stt_language() == "nl"


def test_auto_resolves_to_the_language_of_this_machine(monkeypatch) -> None:
    """"auto" used to mean "no idea, re-detect every clip". It now means
    "the language of this household"."""
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    monkeypatch.setattr("locale.getlocale", lambda *a: ("Dutch_Belgium", "cp1252"))
    assert _stt_language() == "nl"


def test_the_locale_beats_the_reply_fallback(monkeypatch) -> None:
    """The owner's own machine: a Dutch Belgian install with the reply
    fallback left on French. Pinning the microphone to French would have made
    the exact complaint worse — the two settings answer different questions."""
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "fr")
    monkeypatch.setattr("locale.getlocale", lambda *a: ("Dutch_Belgium", "cp1252"))
    assert _stt_language() == "nl"


def test_the_fallback_is_used_when_the_machine_says_nothing(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "auto")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "fr")
    assert _stt_language() == "fr"


def test_multi_is_the_only_way_back_to_free_detection(monkeypatch) -> None:
    """Households that genuinely mix languages inside one sentence (U130) opt
    out explicitly, rather than everyone paying for it by default."""
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "multi")
    monkeypatch.setenv("LANGUAGE_FALLBACK", "nl")
    assert _stt_language() == ""


def test_stt_language_overrides_everything(monkeypatch) -> None:
    monkeypatch.setenv("STT_LANGUAGE", "de")
    monkeypatch.setenv("ASSISTANT_LANGUAGE", "nl")
    assert _stt_language() == "de"


def test_posix_and_windows_locale_names_both_parse() -> None:
    assert _language_of("nl_BE.UTF-8") == "nl"
    assert _language_of("Dutch_Belgium") == "nl"
    assert _language_of("English_United States") == "en"
    assert _language_of(None) == ""


# --------------------------------------------------------------------------- #
# The script gate: what the television produces
# --------------------------------------------------------------------------- #

def test_a_transcript_in_another_script_is_dropped() -> None:
    """Not a transcript — the model inventing words out of noise. Answering it
    is answering nobody."""
    assert _wrong_script("私はロボットです", "nl")
    assert _wrong_script("Привет как дела", "nl")


def test_ordinary_dutch_survives() -> None:
    assert not _wrong_script("hoe laat is het vanavond", "nl")
    assert not _wrong_script("café, één, ijs — accenten horen erbij", "nl")


def test_a_borrowed_word_does_not_cost_the_sentence() -> None:
    """"Mostly", not "any": a Dutch sentence quoting one foreign word is still
    a Dutch sentence."""
    assert not _wrong_script("hij zei こんにちは tegen mij en liep door", "nl")


def test_something_too_short_to_judge_is_left_to_the_other_guards() -> None:
    assert not _wrong_script("ok", "nl")
    assert not _wrong_script("こん", "nl")


def test_nothing_is_dropped_when_no_language_was_pinned() -> None:
    """`multi` means the household mixes languages; the gate must not fire."""
    assert not _wrong_script("私はロボットです", "")
