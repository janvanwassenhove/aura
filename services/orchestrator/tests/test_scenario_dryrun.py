"""U205: dry-run the SHIPPED test presentation through the runner.

Proves the actual scenario file drives correctly end to end (in logic): every
beat fires on the right trigger, in a plausible presentation order, with fakes
standing in for the robot and the LLM.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from orchestrator.scenario_runner import ScenarioRunner
from shared_schemas.presentation import Scenario

SCENARIO = Path(__file__).resolve().parents[3] / "docs" / "demo" / "robot-junior-dev.scenario.yaml"


def _load() -> Scenario:
    return Scenario.model_validate(yaml.safe_load(SCENARIO.read_text(encoding="utf-8")))


def test_the_shipped_scenario_is_valid_and_has_every_beat_type() -> None:
    sc = _load()
    modes = {b.mode for b in sc.beats}
    kinds = {b.trigger_kind for b in sc.beats}
    assert modes == {"speak", "improvise", "chime_in", "silent"}
    assert kinds == {"slide", "keyword", "manual"}


async def test_a_full_run_of_the_test_presentation() -> None:
    said: list[str] = []
    gestured: list[str] = []

    async def speak(t): said.append(t)
    async def gesture(g): gestured.append(g)
    async def generate(topic, guardrails, engine): return f"[{topic[:20]}…]"

    r = ScenarioRunner(_load(), speak=speak, generate=generate, gesture=gesture)

    # Slide 1 → the robot introduces itself (verbatim).
    assert [b.id for b in await r.on_slide(1)] == ["intro"]
    assert said[0].startswith("Hallo allemaal")

    # Jan says "Java" → the kids beat chimes in, once.
    assert [b.id for b in await r.on_speech("...niemand leert nog Java...")] == ["kids-java"]
    assert await r.on_speech("Java again") == []

    # Slide 4 → the thesis is improvised.
    assert [b.id for b in await r.on_slide(4)] == ["thesis"]
    assert gestured == ["wave", "nod"]    # intro waved, thesis nods

    # Jan says "agents" → the agent-factory beat chimes in.
    assert [b.id for b in await r.on_speech("my agents code in parallel")] == ["agent-factory"]

    # Slide 6 → the robot stays SILENT (fires, says nothing).
    before = len(said)
    assert [b.id for b in await r.on_slide(6)] == ["the-question"]
    assert len(said) == before           # silence

    # The closing is hand-advanced.
    assert (await r.next()).id == "closing"
    assert said[-1].startswith("Dus:")

    # Everything fired exactly once.
    assert sorted(r.status()["fired"]) == [
        "agent-factory", "closing", "intro", "kids-java", "the-question", "thesis"]
