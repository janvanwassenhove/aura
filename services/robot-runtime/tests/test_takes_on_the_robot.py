"""U410: a talk's lines are on the robot before their cue.

Asked (translated): *"can we add preloading to decrease delay/latency of e.g.
wifi hotspot?"* U409 took the TTS service out of the cue; what was left was
the line itself — a whole utterance of PCM, some 300 kB for five seconds,
posted to the robot when the beat fired. On a phone's hotspot that transfer is
the delay. Now the brain sends each recorded line ahead, the robot keeps it,
and the cue names it.
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter
from robot_runtime.takes import TakeStore

KEY = "0123456789abcdef0123456789abcdef"
PCM = b"\x00\x01" * 24000


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOT_TAKES_DIR", str(tmp_path / "takes"))
    return TakeStore()


# ── the store ───────────────────────────────────────────────────────────────

def test_a_take_is_kept_and_found_again(store) -> None:
    assert not store.has(KEY)
    store.put(KEY, PCM)
    assert store.has(KEY) and store.get(KEY) == PCM
    assert TakeStore().get(KEY) == PCM, "and survives the runtime restarting"


@pytest.mark.parametrize("bad", ["../../etc/passwd", "ABC", "", "x" * 32, "0" * 65])
def test_a_key_is_a_key_and_never_a_path(store, bad) -> None:
    with pytest.raises(ValueError):
        store.put(bad, PCM)
    assert store.get(bad) is None


def test_it_keeps_the_most_recently_used(store, monkeypatch) -> None:
    monkeypatch.setattr(TakeStore, "KEEP", 3)
    keys = [f"{i:032x}" for i in range(5)]
    for k in keys:
        store.put(k, PCM)
    assert [store.has(k) for k in keys] == [False, False, True, True, True]


# ── the routes ──────────────────────────────────────────────────────────────

@pytest.fixture()
async def robot(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOT_TAKES_DIR", str(tmp_path / "takes"))
    from robot_runtime.engine.behavior import BehaviorEngine
    from shared_events.bus import AsyncEventBus

    adapter = FakeRobotAdapter()
    await adapter.connect()
    bus = AsyncEventBus()
    await bus.start()
    routes.adapter = adapter
    routes.engine = BehaviorEngine(adapter, bus, session_id="t")
    app = FastAPI()
    app.include_router(routes.router)
    yield TestClient(app), adapter
    routes.adapter = routes.engine = None
    await bus.stop()


def _b64(data: bytes = PCM) -> str:
    return base64.b64encode(data).decode()


async def test_a_line_sent_ahead_is_played_by_its_name(robot) -> None:
    client, adapter = robot
    assert client.post("/robot/takes", json={"key": KEY, "audio_b64": _b64()}).status_code == 200
    r = client.post("/robot/speak", json={"text": "Goedemorgen.", "take": KEY})
    assert r.status_code == 200
    assert adapter._played_audio[-1] == PCM, "the take, played"


async def test_a_take_he_does_not_have_is_said_not_swallowed(robot) -> None:
    """U269: a speak that plays nothing must never answer ok."""
    client, adapter = robot
    r = client.post("/robot/speak", json={"text": "Goedemorgen.", "take": KEY})
    assert r.status_code == 409 and r.json()["take"] == KEY
    assert adapter._played_audio == []


async def test_the_brain_can_ask_which_lines_he_already_has(robot) -> None:
    client, _ = robot
    other = "f" * 32
    client.post("/robot/takes", json={"key": KEY, "audio_b64": _b64()})
    r = client.post("/robot/takes/held", json={"keys": [KEY, other]})
    assert r.status_code == 200 and r.json()["held"] == [KEY]


async def test_a_bad_take_is_refused(robot) -> None:
    client, _ = robot
    assert client.post("/robot/takes", json={"key": "../x", "audio_b64": _b64()}).status_code == 422
    assert client.post("/robot/takes", json={"key": KEY}).status_code == 422
    assert client.post("/robot/takes", json={"key": KEY, "audio_b64": "%%%"}).status_code == 422


async def test_moving_along_with_a_take_needs_no_audio_either(robot) -> None:
    client, adapter = robot
    client.post("/robot/takes", json={"key": KEY, "audio_b64": _b64()})
    r = client.post("/robot/speak/along", json={"take": KEY})
    assert r.status_code == 200
    assert adapter.talked_along == [pytest.approx(len(PCM) / 2 / 24000)]
    assert client.post("/robot/speak/along", json={"take": "e" * 32}).status_code == 409
