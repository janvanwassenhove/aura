"""U59: skills — parse, match, CRUD, prompt injection into the agentic loop."""

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
from orchestrator.skills import Skill, SkillStore, _parse
from shared_events.bus import AsyncEventBus

SKILL_MD = """---
name: presenting-with-jan
description: How Jan wants presentations to run
triggers: presentation, slides
personas: work, presentation
person: jan
enabled: true
---
1. Open the deck first.
2. Wait for Jan's nod before advancing.
"""


def test_parse_roundtrip() -> None:
    skill = _parse(SKILL_MD, "fallback")
    assert skill.name == "presenting-with-jan"
    assert skill.triggers == ["presentation", "slides"]
    assert skill.personas == ["work", "presentation"]
    assert skill.person == "jan"
    assert "Wait for Jan's nod" in skill.body
    reparsed = _parse(skill.to_markdown(), "x")
    assert reparsed == skill


def test_matching_rules() -> None:
    skill = _parse(SKILL_MD, "x")
    assert skill.matches("start the presentation", "work", "jan") is True
    assert skill.matches("start the presentation", "work", "someone-else") is False
    assert skill.matches("start the presentation", "home", "jan") is False  # persona
    assert skill.matches("play some music", "work", "jan") is False  # no trigger
    skill.enabled = False
    assert skill.matches("start the presentation", "work", "jan") is False


def test_store_crud_and_reload(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    assert store.all() == []
    store.save(Skill(name="tidy-desk", description="tidy", body="Do X."))
    assert [s.name for s in store.all()] == ["tidy-desk"]
    # External edit is picked up (file-backed, lazy reload).
    (tmp_path / "external.md").write_text("---\nname: external\n---\nBody.",
                                          encoding="utf-8")
    store._loaded_at = 0.0
    assert {s.name for s in store.all()} == {"tidy-desk", "external"}
    assert store.delete("tidy-desk") is True
    assert store.delete("tidy-desk") is False
    with pytest.raises(ValueError):
        store.save(Skill(name="Bad Name!", body="x"))


def test_prompt_block_injects_relevant_full_and_others_by_name(tmp_path) -> None:
    store = SkillStore(str(tmp_path))
    store.save(Skill(name="deploy-flow", description="how we deploy",
                     triggers=["deploy"], body="Always run tests before deploy."))
    store.save(Skill(name="coffee-order", description="jan's coffee",
                     triggers=["coffee"], body="Flat white, oat."))
    block = store.prompt_block("please deploy the app", "work", None)
    assert "Always run tests before deploy." in block  # relevant → full body
    assert "coffee-order" in block                      # other → mentioned
    assert "Flat white" not in block                    # ...but not its body


async def test_skill_lands_in_the_agent_system_prompt(tmp_path, monkeypatch) -> None:
    store = SkillStore(str(tmp_path))
    store.save(Skill(name="deploy-flow", description="how we deploy",
                     triggers=["deploy"], body="OWNER-RULE: tests before deploy."))

    captured: list[str] = []

    async def fake_llm(messages, tools=None, **kw):
        captured.append(messages[0]["content"])
        return {"content": "ok", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)

    bus = AsyncEventBus()
    await bus.start()
    pipeline = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )
    pipeline.set_skill_store(store)
    await pipeline.orchestrate("deploy the new version", "s1")
    await bus.stop()

    assert "OWNER-RULE: tests before deploy." in captured[0]
    assert "AUTOMATION LADDER" in captured[0]  # U58 note also present
