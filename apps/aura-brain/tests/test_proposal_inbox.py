"""U251: a raised proposal has to survive until the owner looks.

U250 published it on the event bus, which reaches a console that happens to be
open. The maintenance tick runs every five minutes all day; the owner opens the
app for ten minutes in the evening. Every proposal raised in between existed for
the milliseconds it took to cross the bus.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain import proposal_inbox


@pytest.fixture(autouse=True)
def _clean_inbox():
    proposal_inbox._reset_for_tests()
    yield
    proposal_inbox._reset_for_tests()


def _p(kind="rewrite", skill="chrome", **extra) -> dict:
    return {"kind": kind, "skill": skill, "reason": "blocked 2×",
            "rationale": "r", "current_body": "old", "proposed_body": "new", **extra}


def test_a_proposal_waits_to_be_answered() -> None:
    filed = proposal_inbox.file(_p())
    assert filed["id"]
    assert [p["skill"] for p in proposal_inbox.open_proposals()] == ["chrome"]


def test_answering_takes_it_off_the_list() -> None:
    filed = proposal_inbox.file(_p())
    assert proposal_inbox.resolve(filed["id"]) is True
    assert proposal_inbox.open_proposals() == []


def test_answering_twice_is_not_an_error_the_second_time() -> None:
    filed = proposal_inbox.file(_p())
    proposal_inbox.resolve(filed["id"])
    assert proposal_inbox.resolve(filed["id"]) is False


def test_the_same_question_is_never_asked_twice(monkeypatch) -> None:
    """A tick every five minutes must not stack five cards about one skill."""
    first = proposal_inbox.file(_p())
    again = proposal_inbox.file(_p(proposed_body="a better draft"))
    assert len(proposal_inbox.open_proposals()) == 1
    assert again["id"] == first["id"], "same card, newer draft"
    assert proposal_inbox.open_proposals()[0]["proposed_body"] == "a better draft"


def test_a_rewrite_and_a_new_skill_are_different_questions() -> None:
    proposal_inbox.file(_p("rewrite", "chrome"))
    proposal_inbox.file(_p("new", "chrome"))
    assert len(proposal_inbox.open_proposals()) == 2


def test_waiting_for_answers_what_the_proposer_asks() -> None:
    assert proposal_inbox.waiting_for("rewrite", "chrome") is False
    proposal_inbox.file(_p())
    assert proposal_inbox.waiting_for("rewrite", "chrome") is True
    assert proposal_inbox.waiting_for("new", "chrome") is False


def test_the_list_stays_a_handful() -> None:
    """More than a few open questions is a backlog, and a backlog gets
    ignored wholesale."""
    for i in range(12):
        proposal_inbox.file(_p(skill=f"skill-{i}"))
    open_now = proposal_inbox.open_proposals()
    assert len(open_now) == 5
    assert open_now[-1]["skill"] == "skill-11", "the newest survive"


# ---------------------------------------------------------------------------
# Through the API, which is what the console actually uses.
# ---------------------------------------------------------------------------


def test_the_console_can_fetch_and_answer() -> None:
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    filed = proposal_inbox.file(_p("new", "sport-uitslagen",
                                   description="Zoek uitslagen op",
                                   triggers=["hockey"]))
    app = create_app()
    with TestClient(app) as client:
        listed = client.get("/skills/proposals")
        assert listed.status_code == 200
        body = listed.json()["proposals"]
        assert len(body) == 1
        assert body[0]["kind"] == "new"
        assert body[0]["triggers"] == ["hockey"]

        assert client.delete(f"/skills/proposals/{filed['id']}").status_code == 200
        assert client.get("/skills/proposals").json()["proposals"] == []


def test_answering_something_that_is_gone_is_a_404() -> None:
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        assert client.delete("/skills/proposals/p999").status_code == 404


def test_proposals_is_not_read_as_a_skill_name() -> None:
    """/skills/{name} would swallow it — the same trap /suggestions had."""
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        assert "proposals" in client.get("/skills/proposals").json()


# ---------------------------------------------------------------------------
# And the proposer stops re-raising what is already waiting.
# ---------------------------------------------------------------------------


async def test_the_proposer_does_not_re_ask_a_pending_question(tmp_path, monkeypatch) -> None:
    from aura_brain.skill_proposals import SkillProposer
    from orchestrator.skills import SkillStore

    (tmp_path / "chrome.md").write_text(
        "---\nname: chrome\ndescription: browse\ntriggers: chrome\n---\nbody\n",
        encoding="utf-8")
    store = SkillStore(str(tmp_path))
    for _ in range(2):
        store.record_observation("chrome", {"request": "zoek", "unavailable": ["browser"]})

    calls = {"n": 0}

    async def fake_chat(messages, model=None, **kw):
        calls["n"] += 1
        return {"content": '{"changed": true, "rationale": "r", "body": "B"}'}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    class FakeBus:
        async def publish(self, event) -> None:
            pass

    first = SkillProposer(store, FakeBus())
    assert await first.review() is not None

    # A restart clears the in-memory cooldown but NOT the inbox — without the
    # inbox check the owner would get a second card for the same thing.
    second = SkillProposer(store, FakeBus())
    assert await second.review() is None
    assert calls["n"] == 1, "and it must not pay for a second draft either"
