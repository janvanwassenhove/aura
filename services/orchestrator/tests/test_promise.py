"""U248: "Ik ga nu Chrome openen — even geduld" was the whole answer.

Timestamps from the report: 00:19:16 the owner asks, 00:19:17 the assistant
replies. One second. launch_app is approval-gated (there would have been a
dialog) and use_computer takes ten seconds or more, so nothing ran at all — the
turn ended on an announcement, and the pipeline agreed with it, because a model
reply without tool calls ends the loop whatever it says.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.promise import looks_like_a_promise
from shared_events.bus import AsyncEventBus

# The literal reply from the screenshot.
REPORTED = "Ik ga nu Chrome openen en een zoekopdracht voor je uitvoeren. Even geduld, alsjeblieft!"


# ---------------------------------------------------------------------------
# What counts as a promise
# ---------------------------------------------------------------------------


def test_the_reported_reply_is_a_promise() -> None:
    assert looks_like_a_promise(REPORTED)


@pytest.mark.parametrize("reply", [
    "Ik ga dat nu voor je opzoeken.",
    "Ik zal even kijken.",
    "Momentje!",
    "Even geduld, ik open Spotify.",
    "I'll open Chrome and search for that.",
    "One moment — I'm searching now.",
    "Hang on, I'm launching it.",
])
def test_announcements_are_caught(reply: str) -> None:
    assert looks_like_a_promise(reply), reply


@pytest.mark.parametrize("reply", [
    "Zal ik Chrome voor je openen?",
    "Wil je dat ik dat opzoek?",
    "Would you like me to open Chrome?",
    "Shall I search for that?",
])
def test_an_offer_is_not_a_promise(reply: str) -> None:
    """This is the RIGHT answer when it cannot act. Treating it as a broken
    promise would punish exactly the honesty we are asking for."""
    assert not looks_like_a_promise(reply), reply


@pytest.mark.parametrize("reply", [
    "Ik heb Chrome geopend en gezocht op WK hockey.",
    "Chrome is open, hier zijn de resultaten.",
    "I opened Chrome and searched for that.",
    "Dat kan ik niet: schermbesturing staat uit.",
    "",
])
def test_ordinary_replies_are_left_alone(reply: str) -> None:
    assert not looks_like_a_promise(reply), reply


# ---------------------------------------------------------------------------
# And what the pipeline does about it
# ---------------------------------------------------------------------------


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def pipeline(bus) -> OrchestratorPipeline:
    return OrchestratorPipeline(bus, IntentRouter(mode="work"),
                                ApprovalManager(bus, session_id="t"),
                                ContextBuilder(), PersonaManager())


def _replies(*texts):
    """A model that returns these replies in order, never calling a tool."""
    seen = {"n": 0}

    async def _llm(messages, tools, timing, session_id, model=None):
        i = min(seen["n"], len(texts) - 1)
        seen["n"] += 1
        return {"content": texts[i], "tool_calls": None, "cancelled": False}
    _llm.seen = seen
    return _llm


async def test_a_promise_with_nothing_done_is_pushed_back(pipeline, monkeypatch) -> None:
    llm = _replies(REPORTED, "Dat lukt me niet: ik kan Chrome niet bereiken.")
    monkeypatch.setattr(pipeline, "_llm", llm)

    reply = await pipeline.orchestrate("zoek het op in google in chrome", "s1")

    assert llm.seen["n"] == 2, "the turn must not end on the announcement"
    assert reply == "Dat lukt me niet: ik kan Chrome niet bereiken."


async def test_the_pushback_says_what_to_do_instead(pipeline, monkeypatch) -> None:
    """It is not enough to reject the promise — the second round has to know
    that naming the blocker and asking is the acceptable answer."""
    seen: list[str] = []

    async def _llm(messages, tools, timing, session_id, model=None):
        seen.extend(m.get("content", "") for m in messages if m.get("role") == "system")
        return {"content": REPORTED if len(seen) < 3 else "ok", "tool_calls": None,
                "cancelled": False}
    monkeypatch.setattr(pipeline, "_llm", _llm)
    await pipeline.orchestrate("doe iets", "s1")

    nudge = [s for s in seen if "you have not called a single tool" in s]
    assert nudge, "the nudge must reach the model"
    assert "propose the smallest concrete change" in nudge[0]
    assert "Never describe work you have not done" in nudge[0]


async def test_it_pushes_back_only_once(pipeline, monkeypatch) -> None:
    """A model that keeps promising must not spin the loop. One push, then the
    answer stands — bad, but bounded and visible."""
    llm = _replies(REPORTED, REPORTED, REPORTED)
    monkeypatch.setattr(pipeline, "_llm", llm)

    reply = await pipeline.orchestrate("doe iets", "s1")

    assert llm.seen["n"] == 2, "exactly one extra round"
    assert reply == REPORTED


async def test_an_honest_refusal_is_accepted_immediately(pipeline, monkeypatch) -> None:
    llm = _replies("Dat kan ik niet — schermbesturing staat uit. Zal ik Chrome openen?")
    monkeypatch.setattr(pipeline, "_llm", llm)
    await pipeline.orchestrate("zoek iets op", "s1")
    assert llm.seen["n"] == 1, "saying so plainly is a finished turn"


async def test_a_promise_after_real_work_is_left_alone(pipeline, monkeypatch) -> None:
    """"Ik open hem nu" is fine when a tool DID run this turn — the check is
    about empty turns, not about phrasing."""
    calls = {"n": 0}

    async def _llm(messages, tools, timing, session_id, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "cancelled": False,
                    "tool_calls": [{"id": "c1", "name": "launch_app",
                                    "arguments": '{"name": "chrome"}'}]}
        return {"content": "Ik open hem nu.", "tool_calls": None, "cancelled": False}

    async def _round(tool_calls, session_id, timing, restrict=None):
        return ([], [{"role": "tool", "content": "Launched chrome."}], ["launch_app"])

    monkeypatch.setattr(pipeline, "_llm", _llm)
    monkeypatch.setattr(pipeline, "_run_tool_round", _round)

    await pipeline.orchestrate("open chrome", "s1")
    assert calls["n"] == 2, "no pushback: something actually happened"


# ---------------------------------------------------------------------------
# U261: the model found a new way to promise
# ---------------------------------------------------------------------------


def test_the_phrasing_that_got_through() -> None:
    """Reported: "kan je claude vragen welke projecten ik openstaan heb" ->
    "Ik kan Claude voor je openen en hem de vraag stellen. Laat me dat even
    doen!" - and nothing happened in the Claude app.

    U248 built the guard; this sentence simply was not in its vocabulary. That
    is the standing weakness of a word list, and the reason each escape gets
    written down here rather than argued about.
    """
    assert looks_like_a_promise(
        "Ik kan Claude voor je openen en hem de vraag stellen. "
        "Laat me dat even doen!")


def test_the_other_ways_it_says_it_now() -> None:
    for reply in (
        "Laat me dat even doen!",
        "Ik doe dat nu voor je.",
        "Dat ga ik even voor je opzoeken.",
        "Let me open that for you.",
        "I'll go ahead and check.",
        "Komt eraan!",
        "On it!",
    ):
        assert looks_like_a_promise(reply), reply


def test_handing_the_next_step_back_is_not_a_promise() -> None:
    """"Laat me weten" is the opposite of "laat me doen": it puts the ball in
    the owner's court, which is a perfectly good way to end a turn."""
    assert not looks_like_a_promise("Laat me weten of dat lukt.")
    assert not looks_like_a_promise("Let me know if that works.")


def test_a_promise_still_counts_when_a_let_me_know_follows_it() -> None:
    """Excluding on "laat me weten" at the whole-reply level would have thrown
    away the promise in front of it - which is why that exclusion lives inside
    the pattern instead of in _OFFERS."""
    assert looks_like_a_promise(
        "Ik ga nu Chrome openen. Laat me weten of het lukt.")


def test_reporting_finished_work_is_never_a_promise() -> None:
    assert not looks_like_a_promise("Ik heb Claude geopend en de vraag gesteld.")
    assert not looks_like_a_promise("Het antwoord is 42.")


def test_saying_it_cannot_is_never_a_promise() -> None:
    """Naming a limit is the behaviour U248 wanted; nagging about it would
    teach exactly the wrong lesson."""
    assert not looks_like_a_promise(
        "Ik kan dat niet openen - de app staat niet in je lijst.")
