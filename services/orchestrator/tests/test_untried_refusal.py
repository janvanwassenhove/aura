"""U381: "I can't" is an answer only after he tried.

Reported with a screenshot (translated): *"can you ask chatgpt to generate an
image about richie mini with a canoe on the river"* → *"I don't have that
possibility, but I can help with something else!"* — and the goal, stated right
after (translated): *"he should go looking for ways to do it — check whether
ChatGPT is installed, or ask whether there is an account (logged in to
Chrome?)."*

U380 made the rule that forbids this survive every rewrite of the skill. But a
rule in a skill is a request to the model; the turn that failed had the skill
bound, every tool it needed offered, and called none of them. So the pipeline
now checks it the way U248 checks an announced action: a refusal in a turn
where nothing ran, while a skill for exactly this request is loaded, is pushed
back once with the instruction to investigate first.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator.approval_manager import ApprovalManager
from orchestrator.builtin_skills import (
    BUILTIN_SKILLS,
    NEVER_UNTRIED_REFUSAL,
    seed_builtin_skills,
)
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.skills import SkillStore
from orchestrator.untried import looks_like_a_refusal
from shared_events.bus import AsyncEventBus

# The literal exchange from the screenshot.
ASKED = "can you ask chatgpt to generate image about richie mini with a canoe on the river"
REFUSED = "Die mogelijkheid heb ik niet, maar ik kan wel iets anders helpen!"


# ── what counts as a refusal ───────────────────────────────────────────────

def test_the_reported_reply_is_a_refusal() -> None:
    assert looks_like_a_refusal(REFUSED)


@pytest.mark.parametrize("reply", [
    "Dat kan ik niet.",
    "Helaas kan ik geen afbeeldingen genereren.",
    "Dat lukt me niet, sorry.",
    "Ik heb geen toegang tot ChatGPT.",
    "ChatGPT is niet beschikbaar op dit systeem.",
    "Daar heb ik geen mogelijkheid toe.",
    "I can't do that.",
    "I cannot generate images.",
    "I don't have the ability to use ChatGPT.",
    "I'm not able to access ChatGPT.",
    "Sorry, I'm unable to help with that.",
    "That isn't something I can do.",
])
def test_refusals_are_recognised(reply: str) -> None:
    assert looks_like_a_refusal(reply), reply


@pytest.mark.parametrize("reply", [
    "Het antwoord is 42.",
    "Ik heb ChatGPT geopend en je vraag gesteld.",
    "Heb je een ChatGPT-account? Log dan in op chatgpt.com in Chrome, dan probeer ik het opnieuw.",
    "Zal ik ChatGPT voor je openen?",
    "Do you have a ChatGPT account?",
    "Done — the image is in the ChatGPT window.",
    "",
])
def test_everything_else_is_left_alone(reply: str) -> None:
    assert not looks_like_a_refusal(reply), reply


# ── the pipeline pushes back once ──────────────────────────────────────────

@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _pipeline(bus, skills_dir=None) -> OrchestratorPipeline:
    p = OrchestratorPipeline(bus, IntentRouter(mode="work"),
                             ApprovalManager(bus, session_id="t"),
                             ContextBuilder(), PersonaManager())
    if skills_dir is not None:
        store = SkillStore(str(skills_dir))
        seed_builtin_skills(store)
        p.set_skill_store(store)
    return p


def _replies(*texts):
    """A model that returns these replies in order, never calling a tool, and
    keeps every system message and every tool list it was shown."""
    seen = {"n": 0, "system": [], "tools": []}

    async def _llm(messages, tools, timing, session_id, model=None):
        i = min(seen["n"], len(texts) - 1)
        seen["n"] += 1
        seen["system"].extend(m.get("content") or "" for m in messages
                              if m.get("role") == "system")
        seen["tools"].append(tools)
        return {"content": texts[i], "tool_calls": None, "cancelled": False}
    _llm.seen = seen
    return _llm


async def test_the_reported_turn_is_pushed_back(bus, tmp_path, monkeypatch) -> None:
    pipeline = _pipeline(bus, tmp_path)
    llm = _replies(REFUSED, "Ik kijk eerst of ChatGPT hier geïnstalleerd is.")
    monkeypatch.setattr(pipeline, "_llm", llm)

    reply = await pipeline.orchestrate(ASKED, "s1")

    assert llm.seen["tools"][0], "the tools were offered — that is the point"
    assert llm.seen["n"] == 2, "an untried refusal must not end the turn"
    assert reply != REFUSED


async def test_the_pushback_names_the_skill_and_how_to_investigate(bus, tmp_path,
                                                                   monkeypatch) -> None:
    pipeline = _pipeline(bus, tmp_path)
    llm = _replies(REFUSED, "ok")
    monkeypatch.setattr(pipeline, "_llm", llm)
    await pipeline.orchestrate(ASKED, "s1")

    nudge = [s for s in llm.seen["system"] if "have not tried" in s]
    assert nudge, "the pushback must reach the model"
    assert "desktop-ai-assistants" in nudge[0], "it must say which skill covers this"
    for how in ("find_app", "list_windows", "list_browser_tabs"):
        assert how in nudge[0], how
    assert "ONE concrete question" in nudge[0], "asking is the fallback, not refusing"


async def test_it_pushes_back_only_once(bus, tmp_path, monkeypatch) -> None:
    pipeline = _pipeline(bus, tmp_path)
    llm = _replies(REFUSED, REFUSED, REFUSED)
    monkeypatch.setattr(pipeline, "_llm", llm)

    reply = await pipeline.orchestrate(ASKED, "s1")

    assert llm.seen["n"] == 2, "exactly one extra round — never a loop"
    assert reply == REFUSED


async def test_without_a_skill_for_it_a_refusal_stands(bus, monkeypatch) -> None:
    """No skill says it can be done — then "I can't" may well be the truth,
    and nagging would teach him to promise instead."""
    pipeline = _pipeline(bus)
    llm = _replies(REFUSED)
    monkeypatch.setattr(pipeline, "_llm", llm)
    await pipeline.orchestrate(ASKED, "s1")
    assert llm.seen["n"] == 1


async def test_a_refusal_after_a_real_tool_result_stands(bus, tmp_path, monkeypatch) -> None:
    """When a tool DID run and said no, the refusal is grounded — that is the
    one case the rule allows."""
    pipeline = _pipeline(bus, tmp_path)
    calls = {"n": 0}

    async def _llm(messages, tools, timing, session_id, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "cancelled": False,
                    "tool_calls": [{"id": "c1", "name": "find_app",
                                    "arguments": '{"name": "chatgpt"}'}]}
        return {"content": "ChatGPT is niet beschikbaar op dit systeem.",
                "tool_calls": None, "cancelled": False}

    async def _round(tool_calls, session_id, timing, restrict=None):
        return ([], [{"role": "tool", "content": "No installed app matches 'chatgpt'."}],
                ["find_app"])

    monkeypatch.setattr(pipeline, "_llm", _llm)
    monkeypatch.setattr(pipeline, "_run_tool_round", _round)
    await pipeline.orchestrate(ASKED, "s1")
    assert calls["n"] == 2, "no pushback: a real result said so"


# ── the skill itself investigates before it gives up ───────────────────────

def _ai_body() -> str:
    return next(s for s in BUILTIN_SKILLS if s.name == "desktop-ai-assistants").body


def test_the_skill_looks_before_it_decides() -> None:
    body = _ai_body()
    assert NEVER_UNTRIED_REFUSAL in body
    for tool in ("find_app", "list_windows", "list_browser_tabs"):
        assert tool in body, f"the skill must investigate with {tool}"


def test_the_skill_has_a_route_for_every_situation() -> None:
    """Installed → the app. Not installed → the website, in the browser the
    owner is logged in to. Asking goes through the keyboard, not the mouse."""
    body = _ai_body()
    assert "open_app" in body
    assert "open_browser_url" in body and "chatgpt.com" in body
    assert "type_into" in body and "send_keys" in body


def test_the_skill_asks_instead_of_refusing() -> None:
    body = _ai_body()
    assert "ONE concrete question" in body
    assert "logged in" in body


def test_the_skill_no_longer_hands_the_owner_a_settings_page() -> None:
    """"Point at Capabilities" is how the optimizer's rewrite ended the turn."""
    assert "point at Capabilities" not in _ai_body()


def test_an_image_is_not_claimed_as_seen() -> None:
    body = _ai_body().lower()
    assert "image" in body and "stays in" in body
