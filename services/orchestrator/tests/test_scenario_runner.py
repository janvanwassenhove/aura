"""U205: the co-presenter runner — beats fire on the right trigger and mode."""

from __future__ import annotations

from orchestrator.scenario_runner import ScenarioRunner
from shared_schemas.presentation import Beat, Scenario


class _Rig:
    """Records what the robot was asked to say/do."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.gestured: list[str] = []
        self.events: list[dict] = []

    async def speak(self, text: str) -> None:
        self.said.append(text)

    async def gesture(self, name: str) -> None:
        self.gestured.append(name)

    async def generate(self, topic: str, guardrails: str, engine: str) -> str:
        # Stand-in LLM: echoes the topic so the test can see improvise ran.
        return f"[about {topic}]"

    async def on_event(self, ev: dict) -> None:
        self.events.append(ev)

    def runner(self, scenario: Scenario) -> ScenarioRunner:
        return ScenarioRunner(scenario, speak=self.speak, generate=self.generate,
                              gesture=self.gesture, on_event=self.on_event)


async def test_manual_beats_fire_in_order_then_stop() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(beats=[
        Beat(id="a", trigger="manual", mode="speak", text="one"),
        Beat(id="b", trigger="manual", mode="speak", text="two"),
    ]))
    assert (await r.next()).id == "a"
    assert (await r.next()).id == "b"
    assert await r.next() is None                 # exhausted
    assert rig.said == ["one", "two"]


async def test_slide_trigger_fires_its_beat_once() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(beats=[
        Beat(id="s", trigger="slide:4", mode="speak", text="on slide four"),
    ]))
    assert [b.id for b in await r.on_slide(4)] == ["s"]
    assert await r.on_slide(4) == []              # already fired
    assert rig.said == ["on slide four"]
    assert r.current_slide == 4


async def test_improvise_speaks_a_generated_line() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(beats=[
        Beat(id="i", trigger="slide:2", mode="improvise",
             topic="why architecture matters", gesture="nod"),
    ]))
    await r.on_slide(2)
    assert rig.said == ["[about why architecture matters]"]
    assert rig.gestured == ["nod"]


async def test_chime_in_fires_on_keyword_and_only_once() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(beats=[
        Beat(id="c", trigger="keyword:privacy", mode="chime_in",
             topic="data stays local", once=True),
    ]))
    # A sentence NOT containing the word does nothing.
    assert await r.on_speech("let's talk about agents") == []
    # The word arms it — fires once.
    assert [b.id for b in await r.on_speech("and what about privacy?")] == ["c"]
    assert await r.on_speech("privacy again") == []      # once
    assert rig.said == ["[about data stays local]"]


async def test_silent_beat_says_nothing_but_advances() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(beats=[Beat(id="q", trigger="manual", mode="silent")]))
    assert (await r.next()).id == "q"
    assert rig.said == []
    assert "q" in r.status()["fired"]


async def test_a_failing_generator_does_not_kill_the_talk() -> None:
    rig = _Rig()

    async def boom(topic, guardrails, engine):
        raise RuntimeError("LLM down")

    r = ScenarioRunner(
        Scenario(beats=[
            Beat(id="i", trigger="manual", mode="improvise", topic="x"),
            Beat(id="ok", trigger="manual", mode="speak", text="still here"),
        ]),
        speak=rig.speak, generate=boom)
    await r.next()                       # improvise fails silently
    await r.next()                       # next beat still runs
    assert rig.said == ["still here"]


async def test_status_reports_armed_keywords() -> None:
    rig = _Rig()
    r = rig.runner(Scenario(title="T", beats=[
        Beat(id="c", trigger="keyword:agents", mode="chime_in", topic="x"),
    ]))
    assert r.status()["armed_keywords"] == ["agents"]
    await r.on_speech("the agents run in parallel")
    assert r.status()["armed_keywords"] == []      # disarmed after firing
