"""U250: the maintenance tick raises a skill proposal, and never saves one.

The deciding is tested in orchestrator/test_skill_review. This is the doing:
does a tick actually raise it, is it a question rather than a change, and does
it stay quiet the rest of the time.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")

from aura_brain.skill_proposals import SkillProposer
from orchestrator.skills import SkillStore


class FakeBus:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)


def _store(tmp_path) -> SkillStore:
    (tmp_path / "chrome.md").write_text(
        "---\nname: chrome\ndescription: browse\ntriggers: chrome\n---\n"
        "1. launch_app('chrome')\n2. use_computer to type the URL\n",
        encoding="utf-8")
    return SkillStore(str(tmp_path))


def _blocked(store: SkillStore, n: int = 2) -> None:
    for _ in range(n):
        store.record_observation("chrome", {
            "request": "zoek het op in chrome", "tools": ["open_browser_url"],
            "unavailable": ["browser"]})


# ---------------------------------------------------------------------------


async def test_a_skill_that_keeps_failing_gets_raised(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    _blocked(store)
    bus = FakeBus()

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"changed": true, "rationale": "use the URL tool",'
                           ' "body": "1. open_browser_url with the search URL"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    raised = await SkillProposer(store, bus).review()

    assert raised is not None and raised["kind"] == "rewrite"
    assert raised["skill"] == "chrome"
    assert "browser" in raised["reason"], "the owner is told what was missing"
    assert bus.events and bus.events[0].event_type == "SkillProposalRaised"


async def test_the_proposal_is_a_question_not_a_change(tmp_path, monkeypatch) -> None:
    """The invariant since U59: nothing writes a skill but the owner."""
    store = _store(tmp_path)
    _blocked(store)
    before = store.get("chrome").body

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"changed": true, "rationale": "r", "body": "REWRITTEN"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    await SkillProposer(store, FakeBus()).review()

    assert store.get("chrome").body == before, "the skill on disk is untouched"


async def test_a_healthy_stack_raises_nothing(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    store.record_observation("chrome", {"request": "open chrome", "unavailable": []})
    bus = FakeBus()
    called = {"n": 0}

    async def fake_chat(messages, model=None, **kw):
        called["n"] += 1
        return {"content": "{}"}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    assert await SkillProposer(store, bus).review() is None
    assert bus.events == []
    assert called["n"] == 0, "a quiet tick must not cost a model call"


async def test_it_does_not_repeat_itself(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    _blocked(store)

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"changed": true, "rationale": "r", "body": "B"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    proposer = SkillProposer(store, FakeBus())
    assert await proposer.review() is not None
    assert await proposer.review() is None, "not again five minutes later"


async def test_nothing_to_change_is_not_an_interruption(tmp_path, monkeypatch) -> None:
    """"Already fine" is a real answer. Raising it would train the owner to
    dismiss these on sight — but it HAS consumed the evidence, so the counter
    resets or the same skill queues up on every tick."""
    store = _store(tmp_path)
    _blocked(store)

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"changed": false, "rationale": "already fine", "body": "x"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    bus = FakeBus()
    assert await SkillProposer(store, bus).review() is None
    assert bus.events == []
    assert store.metrics("chrome")["new_since_optimized"] == 0


async def test_a_repeated_uncovered_subject_drafts_a_new_skill(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    for r in ("wanneer start het wk hockey",
              "zoek het wk hockey programma",
              "hoe laat speelt belgie hockey"):
        store.record_unmatched({"request": r})

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"worth_adding": true, "name": "sport-uitslagen",'
                           ' "description": "Zoek sportuitslagen op",'
                           ' "triggers": ["hockey", "uitslag"],'
                           ' "body": "1. open_browser_url met de zoek-URL",'
                           ' "rationale": "keeps coming up"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    bus = FakeBus()
    raised = await SkillProposer(store, bus).review()

    assert raised is not None and raised["kind"] == "new"
    assert raised["skill"] == "sport-uitslagen"
    assert raised["triggers"] == ["hockey", "uitslag"]
    assert store.get("sport-uitslagen") is None, "proposed, not created"


async def test_worth_adding_false_stays_quiet(tmp_path, monkeypatch) -> None:
    """Most repeated phrasings are conversation, not a procedure. A loop that
    produces a skill every time would bury the owner — the same failure as
    never asking at all."""
    store = _store(tmp_path)
    for r in ("vertel eens iets over hockey", "hou jij van hockey",
              "wat vind je van hockey"):
        store.record_unmatched({"request": r})

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"worth_adding": false, "rationale": "just chat"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    bus = FakeBus()
    assert await SkillProposer(store, bus).review() is None
    assert bus.events == []


async def test_a_broken_model_never_breaks_the_tick(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    _blocked(store)

    async def boom(messages, model=None, **kw):
        raise RuntimeError("no api key")
    monkeypatch.setattr("orchestrator.llm.openai_chat", boom)

    assert await SkillProposer(store, FakeBus()).review() is None


async def test_the_tick_reports_it_as_something_to_decide(tmp_path, monkeypatch) -> None:
    """Not as a fault. A procedure that could be better is not a broken
    system, and a warning light that is always on is not a warning light."""
    from aura_brain.maintenance import MaintenanceLoop

    store = _store(tmp_path)
    _blocked(store)

    async def fake_chat(messages, model=None, **kw):
        return {"content": '{"changed": true, "rationale": "r", "body": "B"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    class FakeRobot:
        async def status(self):
            return {"connected": True}

        async def build(self):
            return {}

    bus = FakeBus()
    loop = MaintenanceLoop(bus, FakeRobot(), knowledge_encrypted=lambda: True,
                           skill_proposer=SkillProposer(store, bus))
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    report = await loop.tick()

    assert any("skill proposal" in a for a in report["actions"])
    assert report["healthy"] is True, "a proposal is not a fault"


@pytest.mark.parametrize("flag", ["false", "FALSE"])
async def test_it_can_be_switched_off(tmp_path, monkeypatch, flag) -> None:
    monkeypatch.setenv("SKILL_PROPOSALS", flag)
    assert os.environ["SKILL_PROPOSALS"].lower() == "false"
