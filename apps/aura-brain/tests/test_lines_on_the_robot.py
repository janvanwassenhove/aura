"""U410: a talk's lines are on the robot before their cue.

Asked (translated): *"can we add preloading to decrease delay/latency of e.g.
wifi hotspot? other improvements?"* U409 took the TTS service out of the cue.
What was left was the line itself: a whole utterance of PCM, some 300 kB for
five seconds, posted to the robot as the beat fired — on a phone's hotspot, the
delay. Now each recorded line is sent to the robot ahead, in the background,
one at a time and only if he does not have it already; the cue names it.

A robot older than this does not know a take by name, and would answer a speak
with no audio by playing nothing and saying ok (U269). So a name is only sent
to a robot that has shown it keeps takes; any other gets the audio, as before.
"""

from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
from aura_brain import presentation_api, speech_out, voice
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.events.audio import SpeechAudioReady

TALK = {
    "title": "Devoxx",
    "beats": [
        {"id": "hello", "trigger": "manual", "mode": "speak", "text": "Goedemorgen, Devoxx."},
        {"id": "gag", "trigger": "manual", "mode": "speak", "text": "Oh, I know this one."},
        {"id": "riff", "trigger": "manual", "mode": "improvise", "topic": "the weather"},
    ],
}


def _status(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        str(code), request=httpx.Request("POST", "http://robot/x"),
        response=httpx.Response(code))


class _Robot:
    """A robot that keeps takes — or, `older`, one that has never heard of them."""

    def __init__(self, older: bool = False) -> None:
        self.older = older
        self.held: dict[str, str] = {}
        self.uploads: list[str] = []
        self.spoken: list[dict] = []
        self.along: list[dict] = []

    async def held_takes(self, keys):
        if self.older:
            raise _status(404)
        return [k for k in keys if k in self.held]

    async def store_take(self, key, audio_b64):
        if self.older:
            raise _status(404)
        self.uploads.append(key)
        self.held[key] = audio_b64
        return {"key": key}

    async def speak(self, text, audio_b64=None, take=None):
        if take is not None:
            if take not in self.held:
                raise _status(409)
            self.spoken.append({"text": text, "take": take, "audio": None})
            return True
        self.spoken.append({"text": text, "take": None, "audio": audio_b64})
        return True

    async def talk_along(self, audio_b64=None, take=None):
        if take is not None and take not in self.held:
            raise _status(409)
        self.along.append({"take": take, "audio": audio_b64})
        return {"moving": True}

    async def execute_motion(self, cmd):
        return True


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


class _NoSlides:
    def __init__(self, on_slide=None) -> None: ...
    def start(self) -> None: ...
    async def stop(self) -> None: ...
    state = None


@pytest.fixture()
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    monkeypatch.setenv("TTS_MODEL", "gpt-4o-mini-tts")
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    from aura_brain import robot_takes, slides_watcher

    monkeypatch.setattr(slides_watcher, "SlidesWatcher", _NoSlides)

    async def improvised(topic, guardrails, engine, persona=""):
        return f"Over {topic}: zonnig."
    monkeypatch.setattr(presentation_api, "_generate", improvised)

    takes = {"n": 0}

    async def tts(text, voice_id=None, speed=1.0, instructions=""):
        takes["n"] += 1
        return base64.b64encode(bytes([takes["n"] % 251]) * 4800).decode()
    monkeypatch.setattr(voice, "synthesize_b64", tts)

    bus = _Bus()
    made: dict = {}

    def start(robot: _Robot):
        presentation_api.init(robot, bus)
        presentation_api._runner = None
        presentation_api._kept = None
        presentation_api._voice_note = ""
        robot_takes.reset()
        made["robot"] = robot
        return robot

    speech_out.forget_all()
    speech_out.bind_bus(bus)
    yield start, bus
    presentation_api._runner = None
    presentation_api._kept = None
    robot_takes.reset()
    speech_out.forget_all()
    speech_out.bind_bus(None)


async def _load() -> None:
    r = await presentation_api.load_scenario({"scenario": TALK})
    assert r.status_code == 200, r.body


async def _settled() -> dict:
    """Recorded, and sent to the robot as far as it is going to be."""
    for _ in range(400):
        rec = presentation_api._status_payload().get("recordings") or {}
        if rec and not rec.get("rendering") and not rec.get("sending"):
            return rec
        await asyncio.sleep(0.01)
    raise AssertionError(f"still busy: {rec}")


async def _fire(beat_id: str) -> None:
    for _ in range(len(TALK["beats"]) + 1):
        out = await presentation_api.next_beat()
        if json.loads(out.body)["fired"] == beat_id:
            return
    raise AssertionError(f"{beat_id} never fired")


# ── ahead of the cue ────────────────────────────────────────────────────────

async def test_each_recorded_line_is_sent_to_the_robot_ahead(rig) -> None:
    start, _ = rig
    robot = start(_Robot())
    await _load()
    rec = await _settled()
    assert len(robot.uploads) == 2, "the two written lines, once each; not the improvised one"
    assert rec["on_robot"] == 2 and rec["robot"] == "holds"


async def test_at_the_cue_only_its_name_travels(rig) -> None:
    start, _ = rig
    robot = start(_Robot())
    await _load()
    await _settled()
    await _fire("hello")
    assert robot.spoken[-1]["take"] in robot.held
    assert robot.spoken[-1]["audio"] is None


async def test_what_he_already_has_is_not_sent_again(rig) -> None:
    """A restart of the brain between rehearsal and talk: he still has them."""
    start, _ = rig
    from aura_brain import robot_takes

    robot = start(_Robot())
    await _load()
    await _settled()
    robot_takes.reset()                               # what a brain restart forgets
    presentation_api._runner = None
    await _load()
    await _settled()
    assert len(robot.uploads) == 2


async def test_a_line_he_lost_is_sent_whole_in_the_same_cue(rig) -> None:
    start, _ = rig
    robot = start(_Robot())
    await _load()
    await _settled()
    robot.held.clear()                                # his runtime lost them
    await _fire("hello")
    assert robot.spoken[-1]["audio"], "the room still hears it"
    for _ in range(100):
        if len(robot.uploads) == 3:
            break
        await asyncio.sleep(0.01)
    assert len(robot.uploads) == 3, "and he gets it again for next time"


async def test_an_older_robot_gets_the_audio_as_before(rig) -> None:
    start, _ = rig
    robot = start(_Robot(older=True))
    await _load()
    rec = await _settled()
    await _fire("hello")
    assert robot.spoken[-1]["audio"] and robot.spoken[-1]["take"] is None
    assert rec["robot"] == "older" and rec["on_robot"] == 0


async def test_a_new_take_is_sent_ahead_too(rig) -> None:
    start, _ = rig
    robot = start(_Robot())
    await _load()
    await _settled()
    before = set(robot.uploads)
    await presentation_api.rerecord({"beat_id": "gag"})
    await _settled()
    new = set(robot.uploads) - before
    assert len(new) == 1
    await _fire("gag")
    assert robot.spoken[-1]["take"] in new


async def test_an_improvised_line_still_carries_its_audio(rig) -> None:
    start, _ = rig
    robot = start(_Robot())
    await _load()
    await _settled()
    await _fire("riff")
    assert robot.spoken[-1]["audio"] and robot.spoken[-1]["take"] is None


async def test_on_the_laptop_he_moves_along_by_name(rig, monkeypatch) -> None:
    start, bus = rig
    robot = start(_Robot())
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    await _load()
    await _settled()
    await _fire("hello")
    line = [e for e in bus.published if isinstance(e, SpeechAudioReady)][-1].utterance_id
    app = FastAPI()
    app.include_router(speech_out.router)
    TestClient(app).post(f"/speech/{line}/started", json={"duration_s": 0.2})
    assert robot.along[-1]["take"] in robot.held and robot.along[-1]["audio"] is None
