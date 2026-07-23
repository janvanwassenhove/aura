"""U206: driving a co-presenter scenario through the brain API."""

from __future__ import annotations

import pytest
from aura_brain import presentation_api
from fastapi import FastAPI
from fastapi.testclient import TestClient

SCENARIO_YAML = """
title: Demo
pptx: demo.pptx
beats:
  - id: intro
    trigger: slide:1
    mode: speak
    text: "Hallo, ik ben de robot."
    gesture: wave
  - id: chime
    trigger: keyword:agents
    mode: chime_in
    topic: "de agent-vloot"
  - id: outro
    trigger: manual
    mode: speak
    text: "Tot slot."
"""


class _FakeRobot:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.motions: list[str] = []

    async def speak(self, text, audio_b64=None):
        self.said.append(text)
        return True

    async def execute_motion(self, cmd):
        self.motions.append(getattr(cmd, "motion_id", "?"))


class _FakeBus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


@pytest.fixture()
def client(monkeypatch):
    robot, bus = _FakeRobot(), _FakeBus()
    presentation_api.init(robot, bus)
    presentation_api._runner = None
    # Deterministic 'improvise' so tests don't call a real LLM.
    async def fake_generate(topic, guardrails, engine):
        return f"[improv: {topic}]"
    monkeypatch.setattr(presentation_api, "_generate", fake_generate)

    app = FastAPI()
    app.include_router(presentation_api.router)
    yield TestClient(app), robot, bus
    presentation_api._runner = None


def test_status_is_inactive_before_loading(client) -> None:
    c, _, _ = client
    assert c.get("/presentation/status").json() == {"active": False}


def test_load_reports_beats_and_armed_keywords(client) -> None:
    c, _, _ = client
    r = c.post("/presentation/scenario", json={"yaml": SCENARIO_YAML})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Demo"
    assert body["armed_keywords"] == ["agents"]
    assert c.get("/presentation/status").json()["active"] is True


def test_bad_yaml_is_422_and_leaves_no_session(client) -> None:
    c, _, _ = client
    assert c.post("/presentation/scenario", json={"yaml": "beats: [{id: x, mode: speak}]"}).status_code == 422
    assert c.get("/presentation/status").json() == {"active": False}


def test_next_fires_manual_beats_then_reports_done(client) -> None:
    c, robot, _ = client
    c.post("/presentation/scenario", json={"yaml": SCENARIO_YAML})
    r = c.post("/presentation/next").json()
    assert r["fired"] == "outro"
    assert robot.said == ["Tot slot."]
    assert c.post("/presentation/next").json()["done"] is True


def test_speech_fires_a_keyword_beat_and_publishes_a_subtitle(client) -> None:
    c, robot, bus = client
    c.post("/presentation/scenario", json={"yaml": SCENARIO_YAML})
    r = c.post("/presentation/speech", json={"text": "our agents run in parallel"}).json()
    assert r["fired"] == ["chime"]
    assert robot.said == ["[improv: de agent-vloot]"]
    # A PresentationBeatFired subtitle reached the bus for the presenter view.
    beat_events = [e for e in bus.published if e.event_type == "PresentationBeatFired"]
    assert beat_events and beat_events[-1].spoken == "[improv: de agent-vloot]"


def test_next_and_speech_before_load_are_409(client) -> None:
    c, _, _ = client
    assert c.post("/presentation/next").status_code == 409
    assert c.post("/presentation/speech", json={"text": "hi"}).status_code == 409


def test_clear_ends_the_session(client) -> None:
    c, _, _ = client
    c.post("/presentation/scenario", json={"yaml": SCENARIO_YAML})
    assert c.delete("/presentation/scenario").json() == {"active": False}
    assert c.get("/presentation/status").json() == {"active": False}


# ------------------------------------------------------------------
# U207: saved scenarios through the API
# ------------------------------------------------------------------

def test_scenario_save_list_load_delete(client, tmp_path, monkeypatch) -> None:
    c, _, _ = client
    monkeypatch.setenv("SCENARIOS_DIR", str(tmp_path))

    assert c.get("/presentation/scenarios").json() == {"scenarios": []}

    r = c.put("/presentation/scenarios/demo", json={"yaml": SCENARIO_YAML})
    assert r.status_code == 200 and r.json()["name"] == "demo"

    listing = c.get("/presentation/scenarios").json()["scenarios"]
    assert listing[0]["name"] == "demo" and listing[0]["title"] == "Demo"

    got = c.get("/presentation/scenarios/demo").json()
    assert "agents" in got["yaml"]

    assert c.delete("/presentation/scenarios/demo").json() == {"deleted": True}
    assert c.get("/presentation/scenarios/demo").status_code == 404


def test_saving_an_invalid_scenario_is_422(client, tmp_path, monkeypatch) -> None:
    c, _, _ = client
    monkeypatch.setenv("SCENARIOS_DIR", str(tmp_path))
    r = c.put("/presentation/scenarios/bad", json={"yaml": "beats: [{id: x, mode: speak}]"})
    assert r.status_code == 422


# ------------------------------------------------------------------
# U208: a pipeline-engine beat can use tools (live data)
# ------------------------------------------------------------------

async def test_pipeline_beat_routes_through_the_agentic_loop_silently() -> None:
    """`engine: pipeline` runs the tool loop; announce=False keeps the pipeline
    from auto-speaking, so the runner speaks the result exactly once."""
    calls: list[dict] = []

    class _FakePipeline:
        async def orchestrate(self, text, session_id, announce=True):
            calls.append({"text": text, "announce": announce})
            return "Vandaag heb je drie meetings."

    from aura_brain import presentation_api as pa
    pa.init(_FakeRobot(), _FakeBus(), pipeline=_FakePipeline())

    out = await pa._generate("mijn agenda vandaag", "één zin", "pipeline")
    assert out == "Vandaag heb je drie meetings."
    assert calls and calls[0]["announce"] is False    # never double-speaks
    assert "mijn agenda vandaag" in calls[0]["text"]


async def test_non_pipeline_beat_uses_the_plain_llm(monkeypatch) -> None:
    """Default engine → a single LLM completion, no tools, no pipeline call."""
    from aura_brain import presentation_api as pa

    called = {"pipeline": False}

    class _Pipe:
        async def orchestrate(self, *a, **k):
            called["pipeline"] = True
            return "should not be used"

    pa.init(_FakeRobot(), _FakeBus(), pipeline=_Pipe())

    async def fake_chat(messages, tools=None, model=None):
        return {"content": "Een vlotte zin.", "tool_calls": None}
    monkeypatch.setattr("orchestrator.llm.openai_chat", fake_chat)

    out = await pa._generate("de toekomst", "", "")
    assert out == "Een vlotte zin."
    assert called["pipeline"] is False
