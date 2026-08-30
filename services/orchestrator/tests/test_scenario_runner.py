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


async def test_a_dead_speaker_never_eats_beat_done() -> None:
    """U265: found live, with the owner's real 137-slide deck on screen.

    The beat showed as fired, but no beat_done ever went out — because for a
    speak beat the speaker call was unguarded, and a robot whose audio path is
    down raises. The subtitle event is derived from beat_done, and subtitles
    are exactly what saves the talk when the audio fails: losing them at that
    moment is losing both channels at once.
    """
    from shared_schemas.presentation.models import Beat, Scenario

    async def broken_speak(_text: str) -> None:
        raise RuntimeError("robot audio is down")

    async def generate(_t, _g, _e) -> str:
        return "never used"

    events: list[dict] = []

    async def on_event(e: dict) -> None:
        events.append(e)

    runner = ScenarioRunner(
        Scenario(title="t", beats=[
            Beat(id="intro", trigger="slide:1", mode="speak", text="Hallo zaal"),
        ]),
        speak=broken_speak, generate=generate, on_event=on_event,
    )
    await runner.on_slide(1)

    done = [e for e in events if e.get("type") == "beat_done"]
    assert done, "beat_done must still be emitted when the speaker fails"
    assert done[0]["spoken"] == "Hallo zaal", "the subtitle text must survive"
