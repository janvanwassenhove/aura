"""U61: declarative hooks + scoped subagents."""

from __future__ import annotations

import json
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.hooks import load_hooks, post_hook_notes, pre_hook_block
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus


@pytest.fixture()
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _pipeline(bus) -> OrchestratorPipeline:
    return OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )


# ── hooks engine ─────────────────────────────────────────────────────

HOOKS = json.dumps([
    {"when": "pre", "tool": "run_dev_task", "arg_match": "git push",
     "action": "block", "message": "Run the test suite first."},
    {"when": "post", "tool": "write_file",
     "action": "note", "message": "Run the linter on the changed file."},
])


def test_hooks_parse_and_match(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HOOKS", HOOKS)
    assert len(load_hooks()) == 2
    assert pre_hook_block("run_dev_task", '{"task": "git push origin main"}')
    assert pre_hook_block("run_dev_task", '{"task": "pytest tests/"}') is None
    assert pre_hook_block("send_mail", '{"task": "git push"}') is None
    assert post_hook_notes("write_file", "{}") == ["Run the linter on the changed file."]


def test_malformed_hooks_are_ignored(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_HOOKS", "not json")
    assert load_hooks() == []
    monkeypatch.setenv("AGENT_HOOKS", json.dumps([{"when": "pre"}]))
    assert load_hooks() == []


async def test_pre_hook_blocks_the_call_in_the_loop(bus, monkeypatch) -> None:
    """A blocking hook fires deterministically; the model reads why and adapts."""
    monkeypatch.setenv("AGENT_HOOKS", HOOKS)
    executed = []

    async def scripted_llm(messages, tools=None, **kw):
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{
                "id": "a", "name": "run_dev_task",
                "arguments": json.dumps({"task": "git push origin main"}),
            }]}
        # The hook's message must be visible to the model in the tool result.
        blocked = [m for m in messages if m["role"] == "tool"]
        assert "Run the test suite first" in blocked[0]["content"]
        return {"content": "ok, running tests first", "tool_calls": None}

    class FakeDev:
        async def run(self, **kw):
            executed.append(kw)
            return "pushed"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    pipeline = _pipeline(bus)
    pipeline._dev_agent = FakeDev()

    reply = await pipeline.orchestrate("push my changes", "s1")
    assert reply == "ok, running tests first"
    assert executed == []  # the push never ran — the hook blocked it


# ── subagents ────────────────────────────────────────────────────────

async def test_subagent_runs_scoped_loop_and_returns_result(bus, monkeypatch) -> None:
    calls: list[list | None] = []

    async def scripted_llm(messages, tools=None, **kw):
        system = messages[0]["content"]
        calls.append(sorted(t["function"]["name"] for t in (tools or [])))
        if "SUBAGENT" in system:
            if not any(m["role"] == "tool" for m in messages):
                return {"content": None, "tool_calls": [{
                    "id": "r1", "name": "git_prepare",
                    "arguments": json.dumps({"action": "status"}),
                }]}
            return {"content": "repo is clean", "tool_calls": None}
        # main agent: delegate, then use the result
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{
                "id": "d1", "name": "delegate_subtask",
                "arguments": json.dumps({"goal": "check repo status"}),
            }]}
        assert any("repo is clean" in m["content"] for m in messages if m["role"] == "tool")
        return {"content": "done: repo is clean", "tool_calls": None}

    async def fake_git(action, working_dir=None):
        return "## main — nothing to commit"

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    monkeypatch.setattr(pipeline_mod.laptop_tools, "git_prepare", fake_git)

    reply = await _pipeline(bus).orchestrate("is the repo clean?", "s1")
    assert reply == "done: repo is clean"
    # The subagent's advertised toolset is read-only and NEVER includes
    # writers or further delegation.
    # Subagent toolsets: contain the read tool but none of the main-only tools.
    sub_toolsets = [c for c in calls if c and "git_prepare" in c and "use_computer" not in c]
    assert sub_toolsets, "subagent never advertised its tools"
    for ts in sub_toolsets:
        assert "delegate_subtask" not in ts
        assert "write_file" not in ts
        assert "send_mail" not in ts


async def test_subagent_cannot_call_tools_outside_its_allowlist(bus, monkeypatch) -> None:
    async def scripted_llm(messages, tools=None, **kw):
        system = messages[0]["content"]
        if "SUBAGENT" in system:
            if not any(m["role"] == "tool" for m in messages):
                return {"content": None, "tool_calls": [{  # tries a gated writer
                    "id": "r1", "name": "send_mail",
                    "arguments": json.dumps({"to": "x@y.z", "subject": "s", "body": "b"}),
                }]}
            refused = [m for m in messages if m["role"] == "tool"]
            assert "not available to this subagent" in refused[0]["content"]
            return {"content": "could not send mail (not allowed)", "tool_calls": None}
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [{
                "id": "d1", "name": "delegate_subtask",
                "arguments": json.dumps({"goal": "mail someone"}),
            }]}
        return {"content": "subagent was correctly restricted", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", scripted_llm)
    reply = await _pipeline(bus).orchestrate("delegate mailing", "s1")
    assert reply == "subagent was correctly restricted"
