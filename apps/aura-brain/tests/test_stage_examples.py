"""U394: the two example scenarios do on the robot what their comments promise.

Asked for as (translated): *"check that these are activated correctly, and give
an example contract (e.g. for a keynote and a conference talk)"*.

Each example is loaded through the real presentation API — the path the
Present panel takes — and walked slide by slide, forwards, backwards and by
jumping, with a robot that keeps only the LAST thing it was told about
wandering and follow-me. That is what the room sees, so that is what is
checked: after every step, the state he is actually in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[3] / "docs" / "demo"


class _Robot:
    """Remembers what he was last told — the state he is in."""

    def __init__(self) -> None:
        self.wander: bool | None = None
        self.follow_me: bool | None = None

    async def set_wander(self, enabled, emotions=False):
        self.wander = enabled
        return {"enabled": enabled, "active": enabled, "sound_direction": True}

    async def set_tracking(self, enabled):
        self.follow_me = enabled
        return enabled

    def __getattr__(self, _name):
        async def _nothing(*a, **k):
            return {}
        return _nothing


@pytest.fixture
def stage(monkeypatch, tmp_path):
    from aura_brain import presentation_api, wander
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    robot = _Robot()
    monkeypatch.setattr(presentation_api, "_robot", robot)

    async def _no_watcher(*_a, **_k):
        return None
    monkeypatch.setattr(presentation_api, "_stop_watcher", _no_watcher)
    monkeypatch.setenv("HEAD_TRACKING", "true")       # the owner: follow-me on
    # the owner: Work does not wander (U397: a behaviour of the mode)
    from orchestrator import mode_policy

    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.reset_cache_for_tests()
    # The console puts the header on Present when a talk starts (U403: the
    # scenario decides only there).
    mode_policy.set_active("presentation")
    wander.forget()
    presentation_api._runner = None
    presentation_api._kept = None
    app = FastAPI()
    app.include_router(presentation_api.router)
    yield TestClient(app), robot, presentation_api
    presentation_api._runner = None
    presentation_api._kept = None
    wander.forget()


async def _walk(stage, name: str, steps) -> list[tuple]:
    client, robot, api = stage
    r = client.post("/presentation/scenario",
                    json={"yaml": (DEMO / name).read_text(encoding="utf-8")})
    assert r.status_code == 200, r.text
    seen = [("loaded", robot.wander, robot.follow_me)]
    for step in steps:
        if isinstance(step, int):
            await api._on_slide(step)
        else:
            await api._runner.on_speech(step)
        seen.append((step, robot.wander, robot.follow_me))
    client.post("/presentation/end")
    seen.append(("ended", robot.wander, robot.follow_me))
    return seen


async def test_the_keynote(stage) -> None:
    seen = await _walk(stage, "keynote.scenario.yaml", [1, 2, 3, 18, 19, 30, 31, 18, 2])
    assert seen == [
        ("loaded", True, True),    # the hall fills: he looks around
        (1, True, True),           # title slide: still looking around
        (2, False, True),          # your first word: he watches you
        (3, False, True),
        (18, False, False),        # the demo: perfectly still
        (19, False, True),         # demo done: watching you again
        (30, True, True),          # questions: turns to whoever asks
        (31, False, True),         # the last line: watching you
        (18, False, False),        # back into the demo, by jumping
        (2, False, True),
        ("ended", False, True),    # your own settings: wander off, follow-me on
    ]


async def test_the_conference_talk(stage) -> None:
    seen = await _walk(stage, "conference-talk.scenario.yaml",
                       [1, 2, "kijk eens rond", 5, 12, 13, "kijk eens rond", 24, 25])
    assert seen == [
        ("loaded", False, True),           # follow-me on, wander off
        (1, True, True),                   # people come in: he looks around
        (2, False, True),                  # first slide of content
        ("kijk eens rond", True, True),    # asked for it: he looks around
        (5, False, True),                  # the slides decide again
        (12, False, False),                # the demo: still
        (13, False, True),
        ("kijk eens rond", True, True),    # works every time (once: false)
        (24, True, True),                  # questions
        (25, False, True),                 # the last line
        ("ended", False, True),
    ]
