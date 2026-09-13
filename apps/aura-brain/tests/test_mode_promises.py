"""U335: every mode keeps the promises its own row makes.

Asked after U334: "kan je verifieren voor alle modi (family, work, present) dat
alles correct wordt afgedwongen". Half of it was, and the half that was not is
the half the owner can edit.

**The capability half is enforced**, and is covered in
`services/orchestrator/tests/test_mode_policy.py`: `allowed_tools()` decides
what the model is even offered, a blocked tool that is called anyway is refused
with `mode_mismatch`, and `requires_approval()` stops every tool of a group set
to *asks* (pipeline.py, the two calls around the tool loop). Presentation drops
MCP tools entirely.

**The behaviour half was not.** The Modes screen shows, per mode:

    home          speaks first: yes                 memory writing: on
    work          speaks first: only for reminders  memory writing: on
    presentation  speaks first: never — cues only   memory writing: off

and outside `mode_policy` nothing ever read those values: `behaviour()`,
`speaks_first()` and `memory_writing` had exactly one caller each — the route
that SETS them. So work briefed out loud, and a presentation quietly learned
about whoever was in the room.

The enforcement reads the ROW, not a copy of it, so the dropdowns in the Modes
editor actually do something.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from orchestrator import mode_policy


@pytest.fixture(autouse=True)
def _isolated_policy(tmp_path, monkeypatch):
    """A throwaway policy file: never the owner's real one."""
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "mode-policy.json"))
    mode_policy._cache = None
    mode_policy._cache_path = None
    before = mode_policy.active()
    yield
    mode_policy.set_active(before)
    mode_policy._cache = None
    mode_policy._cache_path = None


# ── speaking first ─────────────────────────────────────────────────────────

def test_at_home_he_may_start_a_conversation() -> None:
    mode_policy.set_active("home")
    assert mode_policy.may_speak_unprompted() is True
    assert mode_policy.may_speak_unprompted("reminder") is True


def test_at_work_only_a_reminder_gets_to_interrupt() -> None:
    """"only for reminders" — a daily briefing is not a reminder."""
    mode_policy.set_active("work")
    assert mode_policy.may_speak_unprompted("reminder") is True
    assert mode_policy.may_speak_unprompted("briefing") is False
    assert mode_policy.may_speak_unprompted() is False


def test_on_stage_nothing_of_his_own_accord() -> None:
    mode_policy.set_active("presentation")
    assert mode_policy.may_speak_unprompted("reminder") is False
    assert mode_policy.may_speak_unprompted() is False


def test_quiet_still_wins_over_the_friendliest_mode() -> None:
    mode_policy.set_active("home")
    mode_policy.set_quiet(True)
    try:
        assert mode_policy.may_speak_unprompted("reminder") is False
    finally:
        mode_policy.set_quiet(False)


def test_the_rule_follows_the_row_the_owner_edits() -> None:
    """The dropdown in the Modes editor has to mean something: change the row
    for home to the strictest value and home goes quiet."""
    mode_policy.set_active("home")
    mode_policy.set_behaviour("home", {"speaks_first": "never — cues only"})
    assert mode_policy.may_speak_unprompted() is False
    mode_policy.set_behaviour("home", {"speaks_first": "only for reminders"})
    assert mode_policy.may_speak_unprompted("reminder") is True
    assert mode_policy.may_speak_unprompted("briefing") is False


# ── writing memory ─────────────────────────────────────────────────────────

def test_home_and_work_learn_about_people() -> None:
    for mode in ("home", "work"):
        mode_policy.set_active(mode)
        assert mode_policy.may_write_memory() is True, mode


def test_a_presentation_learns_nothing_about_the_room() -> None:
    """An audience did not consent to being remembered."""
    mode_policy.set_active("presentation")
    assert mode_policy.may_write_memory() is False


def test_that_rule_follows_its_row_too() -> None:
    mode_policy.set_active("work")
    mode_policy.set_behaviour("work", {"memory_writing": "off"})
    assert mode_policy.may_write_memory() is False


# ── the callers actually ask ───────────────────────────────────────────────

async def test_the_proactive_loop_obeys_the_mode() -> None:
    from aura_brain.proactive import ProactiveEngine

    class _Bus:
        def __init__(self) -> None:
            self.events = []

        async def publish(self, event) -> None:
            self.events.append(event)

    mode_policy.set_active("work")
    bus = _Bus()
    voice = ProactiveEngine(bus, session_id="t")

    assert await voice.announce("De dagelijkse briefing.") is False
    assert bus.events == [], "a briefing spoke in work mode"

    await voice.on_reminder(type("E", (), {"message": "tandarts om tien uur"})())
    assert len(bus.events) == 1, "a reminder must still get through at work"


async def test_passive_learning_stops_on_stage(monkeypatch) -> None:
    from aura_brain.person_memory import PersonMemory

    mode_policy.set_active("presentation")
    async def _never_called(*a, **k):
        raise AssertionError("distilling should not happen in this test")

    mem = PersonMemory(store=None, chat_fn=_never_called)
    await mem.record("someone", "hello there", "hi back")
    assert not mem._buffers.get("someone"), "an audience was being remembered"

    mode_policy.set_active("home")
    await mem.record("someone", "hello there", "hi back")
    assert mem._buffers.get("someone"), "at home he should still learn"
