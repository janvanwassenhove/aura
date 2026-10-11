"""U413: in Quiet an answer is an answer — not the start of a conversation.

Reported with Quiet on: *"aura in quiet mode, but still talking / asking"*.
Every reply in the screenshot ended by asking something back: *"Vertel me meer
als je wilt!"*, *"Laat me weten welke het is!"*, *"Heb je een favoriete genre
of een boek dat je recent hebt gelezen en dat je leuk vond?"*

The voice loop was the door (see the brain's `test_quiet_listening.py`): each
question he asked opened a window, and the room walked through it. But the
questions were his. Nothing told the model that Quiet was on at all — the
prompt was the same one as in a lively kitchen, so he made conversation. Now
the turn says so, and outside Quiet it does not.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import mode_policy
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus


@pytest.fixture()
def policy(monkeypatch, tmp_path):
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.reset_cache_for_tests()
    yield
    mode_policy.set_quiet(False)
    mode_policy.reset_cache_for_tests()


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


async def _system_prompt(bus, monkeypatch) -> str:
    pipeline = OrchestratorPipeline(bus, IntentRouter(mode="work"),
                                    ApprovalManager(bus, session_id="t"),
                                    ContextBuilder(), PersonaManager())
    seen: list[str] = []

    async def _llm(messages, tools, timing, session_id, model=None):
        seen.extend(m.get("content") or "" for m in messages if m.get("role") == "system")
        return {"content": "Half zes.", "tool_calls": None, "cancelled": False}
    monkeypatch.setattr(pipeline, "_llm", _llm)
    await pipeline.orchestrate("hoe laat is het?", "s1")
    return "\n".join(seen)


async def test_in_quiet_he_is_told_to_answer_and_stop(bus, policy, monkeypatch) -> None:
    mode_policy.set_quiet(True)
    prompt = await _system_prompt(bus, monkeypatch)
    assert mode_policy.QUIET_NOTE in prompt
    note = mode_policy.QUIET_NOTE.lower()
    assert "do not ask" in note, "the question back is what kept the room talking"
    assert "stop" in note


async def test_outside_quiet_he_may_make_conversation(bus, policy, monkeypatch) -> None:
    mode_policy.set_quiet(False)
    prompt = await _system_prompt(bus, monkeypatch)
    assert mode_policy.QUIET_NOTE not in prompt
