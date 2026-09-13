"""U352: the scenario says when the overlay is on the projector.

The overlay is a separate window with its own store, so this crosses an
explicit channel — and it crosses BOTH of them on purpose:

  - `PresentationOverlayChanged` on the bus, because 1.5 s of a robot sitting
    on a slide he was supposed to clear is visible from the back of a room;
  - `overlay_visible` in `/presentation/status`, because an event only reaches
    a subscriber that existed when it was published, and the overlay is a
    window the presenter can open halfway through a talk.
"""

from __future__ import annotations

import pytest
from aura_brain import presentation_api, voice
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.events.system import PresentationOverlayChanged

DEMO_YAML = """
title: Demo
beats:
  - id: intro
    trigger: manual
    mode: speak
    text: "Hallo."
  - id: demo
    trigger: manual
    mode: silent
    overlay: hide
  - id: back
    trigger: manual
    mode: speak
    text: "En ik ben terug."
    overlay: show
"""

QUIET_YAML = """
title: Says nothing about the overlay
beats:
  - id: a
    trigger: manual
    mode: speak
    text: "Hallo."
"""


class _FakeRobot:
    async def speak(self, text, audio_b64=None):
        return True

    async def execute_motion(self, cmd):
        return True


class _FakeBus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


@pytest.fixture()
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    robot, bus = _FakeRobot(), _FakeBus()
    presentation_api.init(robot, bus)
    presentation_api._runner = None

    async def fake_tts(text, *a, **kw):
        return "AAAA"
    monkeypatch.setattr(voice, "synthesize_b64", fake_tts)

    app = FastAPI()
    app.include_router(presentation_api.router)
    yield TestClient(app), bus
    presentation_api._runner = None


def _overlay_events(bus) -> list[bool]:
    return [e.visible for e in bus.published
            if isinstance(e, PresentationOverlayChanged)]


def _load(c, body=DEMO_YAML):
    assert c.post("/presentation/scenario", json={"yaml": body}).status_code == 200


# --------------------------------------------------------------------------- #
# the polled channel — for a window that opens halfway through
# --------------------------------------------------------------------------- #

def test_the_status_says_whether_the_overlay_belongs_on_screen(rig) -> None:
    c, _ = rig
    _load(c)
    assert c.get("/presentation/status").json()["overlay_visible"] is True

    c.post("/presentation/next")                       # intro
    c.post("/presentation/next")                       # demo — clears the screen
    assert c.get("/presentation/status").json()["overlay_visible"] is False

    c.post("/presentation/next")                       # back — and he returns
    assert c.get("/presentation/status").json()["overlay_visible"] is True


def test_a_talk_can_start_with_the_overlay_off(rig) -> None:
    c, _ = rig
    _load(c, """
title: Starts clear
overlay: hidden
beats:
  - id: intro
    trigger: manual
    mode: speak
    text: "Hallo."
    overlay: show
""")
    assert c.get("/presentation/status").json()["overlay_visible"] is False
    c.post("/presentation/next")
    assert c.get("/presentation/status").json()["overlay_visible"] is True


# --------------------------------------------------------------------------- #
# the pushed channel — because 1.5 s is visible from the back of a room
# --------------------------------------------------------------------------- #

def test_moving_the_overlay_is_published_at_once(rig) -> None:
    c, bus = rig
    _load(c)
    for _ in range(3):
        c.post("/presentation/next")

    assert _overlay_events(bus) == [False, True]


def test_the_change_names_the_beat_that_asked_for_it(rig) -> None:
    c, bus = rig
    _load(c)
    c.post("/presentation/next")
    c.post("/presentation/next")

    change = [e for e in bus.published if isinstance(e, PresentationOverlayChanged)][0]
    assert change.beat_id == "demo"


def test_a_scenario_that_says_nothing_publishes_nothing(rig) -> None:
    """The compatibility contract, on the wire: a scenario from before this
    existed must not start emitting overlay traffic."""
    c, bus = rig
    _load(c, QUIET_YAML)
    c.post("/presentation/next")

    assert _overlay_events(bus) == []
    assert c.get("/presentation/status").json()["overlay_visible"] is True


def test_a_new_talk_starts_from_its_own_scenario(rig) -> None:
    c, _ = rig
    _load(c)
    c.post("/presentation/next")
    c.post("/presentation/next")
    assert c.get("/presentation/status").json()["overlay_visible"] is False

    _load(c, QUIET_YAML)                 # a different talk begins
    assert c.get("/presentation/status").json()["overlay_visible"] is True


def test_an_unknown_overlay_word_is_refused_with_a_sentence(rig) -> None:
    """FR-106: nothing in the Present panel may throw, and the presenter gets a
    line they can act on rather than a Pydantic dump."""
    c, _ = rig
    r = c.post("/presentation/scenario", json={"yaml": """
title: Typo
beats:
  - id: demo
    trigger: manual
    mode: silent
    overlay: of
"""})
    assert r.status_code == 422
    body = r.json()["error"]
    assert "demo" in body and "hidden" in body
    assert c.get("/presentation/status").json() == {"active": False}
