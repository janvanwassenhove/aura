"""U57: agentic loop — multi-round reasoning, steering, stop, round budget."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest

from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus
from shared_schemas.events.orchestrator import AgentRoundCompleted, AgentRoundStarted


def _pipeline(bus: AsyncEventBus) -> OrchestratorPipeline:
    return OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )


def _tc(tc_id: str, name: str) -> dict:
    return {"id": tc_id, "name": name, "arguments": "{}"}


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


async def test_loop_runs_multiple_rounds_until_final_answer(bus, monkeypatch) -> None:
    """Round 1: list tasks → round 2: read mail (based on results) → round 3: answer."""
    calls = []

    async def scripted_llm(messages, tools=None, **kw):
        calls.append(len([m for m in messages if m["role"] == "tool"]))
        n_tool_msgs = calls[-1]
        if n_tool_msgs == 0:
            return {"content": None, "tool_calls": [_tc("a", "list_tasks")]}
        if n_tool_msgs == 1:
            return {"content": None, "tool_calls": [_tc("b", "get_unread_mail")]}
        return {"content": "final: 1 task, 2 mails", "tool_calls": None}

    async def connector(self, tool_name, arguments):
        return f"[{tool_name} ok]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", connector)

    rounds: list = []

    async def on_start(e):
        rounds.append(("start", e.round_no))

    async def on_done(e):
        rounds.append(("done", e.round_no, e.done, list(e.tool_names)))

    bus.subscribe(AgentRoundStarted, on_start)
    bus.subscribe(AgentRoundCompleted, on_done)

    reply = await _pipeline(bus).orchestrate("plan my afternoon", "s1")
    import asyncio
    await asyncio.sleep(0.05)  # let the async bus drain the round events

    assert reply == "final: 1 task, 2 mails"
    assert len(calls) == 3  # three LLM rounds, tool results fed back each time
    assert ("start", 1) in rounds and ("start", 3) in rounds
    assert ("done", 1, False, ["list_tasks"]) in rounds
    assert ("done", 3, True, []) in rounds


async def test_round_budget_forces_final_answer(bus, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_MAX_ROUNDS", "2")

    async def greedy_llm(messages, tools=None, **kw):
        if tools is not None:  # keeps asking for tools every round
            return {"content": None, "tool_calls": [_tc("x", "list_tasks")]}
        # final tool-less synthesis after the budget note
        assert any("budget is exhausted" in m.get("content", "").lower()
                   for m in messages if m["role"] == "system")
        return {"content": "partial result", "tool_calls": None}

    async def connector(self, tool_name, arguments):
        return "[ok]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", greedy_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", connector)

    reply = await _pipeline(bus).orchestrate("do everything", "s1")
    assert reply == "partial result"


async def test_owner_steering_lands_in_next_round(bus, monkeypatch) -> None:
    seen_guidance = []

    async def scripted_llm(messages, tools=None, **kw):
        seen_guidance.extend(
            m["content"] for m in messages
            if m["role"] == "system" and "Owner guidance" in m.get("content", "")
        )
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [_tc("a", "list_tasks")]}
        return {"content": "adjusted per your guidance", "tool_calls": None}

    async def connector(self, tool_name, arguments):
        # Owner steers WHILE the tool runs — guidance must land next round.
        pipeline.steer("s1", "only look at today, skip next week")
        return "[ok]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", connector)

    pipeline = _pipeline(bus)
    reply = await pipeline.orchestrate("plan my week", "s1")

    assert reply == "adjusted per your guidance"
    assert any("only look at today" in g for g in seen_guidance)


async def test_owner_stop_wraps_up_after_current_round(bus, monkeypatch) -> None:
    llm_rounds = 0

    async def scripted_llm(messages, tools=None, **kw):
        nonlocal llm_rounds
        if tools is not None:
            llm_rounds += 1
            return {"content": None, "tool_calls": [_tc(f"t{llm_rounds}", "list_tasks")]}
        # stop path: tool-less final call with the wrap-up note
        assert any("wrap up" in m.get("content", "") for m in messages if m["role"] == "system")
        return {"content": "stopped early, here's what I have", "tool_calls": None}

    async def connector(self, tool_name, arguments):
        pipeline.request_stop("s1")  # owner presses stop during round 1
        return "[ok]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", connector)

    pipeline = _pipeline(bus)
    reply = await pipeline.orchestrate("massive task", "s1")

    assert reply == "stopped early, here's what I have"
    assert llm_rounds == 1  # no second tool round after the stop


async def test_approval_gate_fires_every_round(bus, monkeypatch) -> None:
    """The gate is per tool call, per round — a 2-round turn with a sensitive
    tool in each round must request approval twice."""
    approvals = []

    async def scripted_llm(messages, tools=None, **kw):
        n = len([m for m in messages if m["role"] == "tool"])
        if n == 0:
            return {"content": None, "tool_calls": [_tc("a", "send_mail")]}
        if n == 1:
            return {"content": None, "tool_calls": [_tc("b", "send_mail")]}
        return {"content": "both sent", "tool_calls": None}

    async def fake_approval(self, tool_name, arguments):
        approvals.append(tool_name)
        return True

    async def connector(self, tool_name, arguments):
        return "[sent]"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(ApprovalManager, "request_approval", fake_approval)
    monkeypatch.setattr(OrchestratorPipeline, "_call_connector", connector)

    reply = await _pipeline(bus).orchestrate("mail Alice and then Bob", "s1")
    assert reply == "both sent"
    assert approvals == ["send_mail", "send_mail"]


def test_strip_speaker_label(monkeypatch) -> None:
    """U88: a leading 'Richie:' label is dropped from replies (spoken aloud)."""
    monkeypatch.setenv("ASSISTANT_NAME", "Richie")
    from orchestrator.pipeline import _strip_speaker_label as strip

    assert strip("Richie: het is 3 uur") == "het is 3 uur"
    assert strip("Ritchie - kijk op de klok") == "kijk op de klok"   # spelling drift
    assert strip("Het is laat, Richie.") == "Het is laat, Richie."   # not a leading label
    assert strip("Jan: hoi") == "Jan: hoi"                            # someone else
    assert strip("Gewoon antwoord") == "Gewoon antwoord"
