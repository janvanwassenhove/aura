"""U250: the assistant brings a skill up by itself.

Everything needed was already there — U107 could propose a rewrite, U247 gave
it real evidence, U249 made the trigger weigh failure over popularity. The
missing piece was that nobody ever looked: the proposal waited behind a button,
so a skill could die at the same step every day without a word.

These tests are about the DECIDING — is this worth interrupting the owner for —
which has to hold up without a model, a clock or a console anywhere near it.
"""

from __future__ import annotations

import time

from orchestrator import skill_review
from orchestrator.skill_review import Review, reason_to_review, repeated_topic
from orchestrator.skills import SkillStore

# ---------------------------------------------------------------------------
# Rewrite: failure outranks volume
# ---------------------------------------------------------------------------


def _m(name="chrome", *, blocked=0, recent=0, new=0, missing=None) -> dict:
    return {"name": name, "blocked": blocked, "recent": recent,
            "new_since_optimized": new, "missing": missing or {}}


def test_a_skill_that_keeps_failing_is_raised() -> None:
    r = reason_to_review(_m(blocked=2, recent=3, missing={"browser": 2}))
    assert r is not None and r.kind == "rewrite"
    assert "stopped 2 of the last 3" in r.reason
    assert "browser" in r.reason, "the owner is told WHAT was missing"


def test_one_failure_is_not_a_pattern() -> None:
    assert reason_to_review(_m(blocked=1, recent=5)) is None


def test_a_heavily_used_skill_is_still_raised_eventually() -> None:
    assert reason_to_review(_m(new=8)) is not None
    assert reason_to_review(_m(new=7)) is None


def test_failing_outranks_popular() -> None:
    """The exact situation on the owner's machine: a Spotify skill used nine
    times and working, a Chrome skill used twice and blocked both times. The
    old trigger raised the first and said nothing about the second."""
    failing = reason_to_review(_m("chrome", blocked=2, recent=2))
    popular = reason_to_review(_m("spotify", new=9))
    assert failing.urgency > popular.urgency


def test_a_healthy_quiet_skill_is_left_alone() -> None:
    assert reason_to_review(_m(new=1, recent=1)) is None


# ---------------------------------------------------------------------------
# New: something asked repeatedly that nothing covers
# ---------------------------------------------------------------------------


def _unmatched(*requests: str) -> list[dict]:
    return [{"ts": time.time(), "request": r} for r in requests]


def test_a_repeated_subject_becomes_a_proposal() -> None:
    r = repeated_topic(_unmatched(
        "kan je online opzoeken wanneer het wk hockey start",
        "zoek het wk hockey programma op",
        "wanneer speelt belgie op het wk hockey",
    ))
    assert r is not None and r.kind == "new"
    assert r.name == "hockey"
    assert "3 times" in r.reason
    assert len(r.examples) == 3, "the draft is written from the owner's own words"


def test_one_odd_question_is_not_a_habit() -> None:
    assert repeated_topic(_unmatched("wat is de hoofdstad van peru")) is None


def test_unrelated_requests_do_not_become_a_topic() -> None:
    assert repeated_topic(_unmatched(
        "wat is de hoofdstad van peru",
        "hoe laat is het",
        "vertel een mop",
    )) is None


def test_grammar_words_never_become_the_topic() -> None:
    """Without a stop list the "pattern" it finds is just Dutch."""
    r = repeated_topic(_unmatched(
        "kan je even de hockey uitslag geven",
        "kan je even de hockey stand geven",
        "kan je even de hockey kalender geven",
    ))
    assert r is not None
    assert r.name == "hockey", f"got {r.name!r}"


# ---------------------------------------------------------------------------
# pick(): one at a time, and not the same one every five minutes
# ---------------------------------------------------------------------------


def _store(tmp_path, **skills) -> SkillStore:
    for name, triggers in (skills or {"chrome": "chrome"}).items():
        (tmp_path / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: d\ntriggers: {triggers}\n---\nbody\n",
            encoding="utf-8")
    return SkillStore(str(tmp_path))


def test_pick_returns_nothing_when_all_is_well(tmp_path) -> None:
    store = _store(tmp_path, chrome="chrome")
    store.record_observation("chrome", {"request": "open chrome", "unavailable": []})
    assert skill_review.pick(store) is None


def test_pick_returns_the_most_urgent_one(tmp_path) -> None:
    store = _store(tmp_path, chrome="chrome", spotify="spotify")
    for _ in range(9):
        store.record_observation("spotify", {"request": "speel iets", "unavailable": []})
    for _ in range(2):
        store.record_observation("chrome", {"request": "zoek iets", "unavailable": ["browser"]})

    pick = skill_review.pick(store)
    assert pick is not None and pick.name == "chrome", "the broken one, not the busy one"


def test_the_same_subject_is_not_raised_twice_in_a_day(tmp_path) -> None:
    """A tick runs every five minutes. Without this, one signal becomes twelve
    interruptions an hour and the owner learns to ignore it."""
    store = _store(tmp_path, chrome="chrome")
    for _ in range(2):
        store.record_observation("chrome", {"request": "zoek iets", "unavailable": ["browser"]})

    now = time.time()
    first = skill_review.pick(store, now=now)
    assert first is not None
    seen = {f"{first.kind}:{first.name}": now}

    assert skill_review.pick(store, now=now + 300, last_raised=seen) is None
    assert skill_review.pick(store, now=now + 90_000, last_raised=seen) is not None


def test_only_one_thing_is_ever_raised(tmp_path) -> None:
    store = _store(tmp_path, chrome="chrome", spotify="spotify")
    for _ in range(3):
        store.record_observation("chrome", {"request": "a", "unavailable": ["browser"]})
        store.record_observation("spotify", {"request": "b", "unavailable": ["music"]})
    assert isinstance(skill_review.pick(store), Review), "one, not a backlog"


# ---------------------------------------------------------------------------
# The unmatched log itself
# ---------------------------------------------------------------------------


def test_unmatched_requests_are_recorded_and_capped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.skills._MAX_OBS", 4)
    store = _store(tmp_path)
    for i in range(10):
        store.record_unmatched({"request": f"iets {i}"})
    entries = store.unmatched()
    assert len(entries) == 4
    assert entries[-1]["request"] == "iets 9"


def test_the_unmatched_log_cannot_shadow_a_skill(tmp_path) -> None:
    """It shares the metrics directory, so its name must be one no skill can
    have — _NAME_RE forbids a leading underscore."""
    import re

    from orchestrator.skills import _NAME_RE

    assert not re.match(_NAME_RE, SkillStore._UNMATCHED)


def test_the_topic_is_the_same_on_every_run() -> None:
    """_topic_words returns a SET, and set iteration order for strings varies
    between processes. Feeding that to a Counter made most_common() pick a
    different winner per run whenever two words tied — a proposal generator
    that suggests "hockey" today and "geven" tomorrow for identical input."""
    import subprocess
    import sys

    code = (
        "from orchestrator.skill_review import repeated_topic;"
        "print(repeated_topic(["
        "{'ts':1,'request':'kan je even de hockey uitslag geven'},"
        "{'ts':1,'request':'kan je even de hockey stand geven'},"
        "{'ts':1,'request':'kan je even de hockey kalender geven'}]).name)"
    )
    seen = {
        subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, check=True).stdout.strip()
        for _ in range(5)
    }
    assert seen == {"hockey"}, f"unstable across runs: {seen}"
