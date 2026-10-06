"""U407: through the laptop, the robot moves as the laptop speaks for him.

Asked for as: *"in present mode -> when the robot has to say anything
(following the scenario) -> ensure while talking antenna's are moving and head
moving up & down while looking to audience (as if actually talking)"*.

With the laptop as his speaker (U364) the robot was told nothing at all: the
room heard him from the PA while he stood on the table, perfectly still. A
talk's line is now handed to the robot as well — to move along with, never to
play — at the moment the window playing it says it has started (U400's start),
because that is the moment the room starts hearing it.

His own speaker needs nothing from here: he moves with what he plays himself
(robot-runtime's half of this unit).
"""

from __future__ import annotations

import base64

import httpx
import pytest
from aura_brain import presentation_api, speech_out, voice
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.events.audio import SpeechAudioReady, SpeechLineStarted

SECONDS = 1.5
PCM = b"\x00\x01" * int(24000 * SECONDS)       # 24 kHz, 16-bit mono


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


class _Robot:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.along: list[str] = []
        self.fail: Exception | None = None

    async def speak(self, text, audio_b64=None):
        self.spoken.append(text)
        return True

    async def talk_along(self, audio_b64: str) -> dict:
        if self.fail is not None:
            raise self.fail
        self.along.append(audio_b64)
        return {"moving": True, "seconds": SECONDS}

    async def execute_motion(self, cmd):
        return True


class _Beat:
    persona = ""
    voice = ""
    speed = 0.0
    id = "hello"


@pytest.fixture()
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    bus = _Bus()
    robot = _Robot()
    presentation_api.init(robot, bus)
    presentation_api._runner = None
    presentation_api._kept = None
    presentation_api._voice_note = ""

    async def tts(text, voice_id=None, speed=1.0, instructions=""):
        return base64.b64encode(PCM).decode()
    monkeypatch.setattr(voice, "synthesize_b64", tts)
    speech_out.forget_all()
    speech_out.bind_bus(bus)
    app = FastAPI()
    app.include_router(speech_out.router)
    yield robot, bus, monkeypatch, TestClient(app)
    speech_out.forget_all()
    speech_out.bind_bus(None)


def _offered(bus: _Bus) -> str:
    return [e for e in bus.published if isinstance(e, SpeechAudioReady)][-1].utterance_id


def _started(client: TestClient, utterance_id: str):
    return client.post(f"/speech/{utterance_id}/started", json={"duration_s": SECONDS})


async def test_on_the_laptop_he_moves_along_when_the_line_starts(rig) -> None:
    robot, bus, _, client = rig
    await presentation_api._speak("Goedemorgen, Devoxx.", _Beat())
    line = _offered(bus)
    heard = speech_out._waiting[line][44:]          # the WAV the laptop will play
    assert robot.along == [], "not before the room can hear it"

    r = _started(client, line)
    assert r.status_code == 200
    assert [base64.b64decode(a) for a in robot.along] == [heard], "the line the room hears"
    assert robot.spoken == [], "to move along with, never to play: the laptop is his speaker"
    assert r.json()["robot"] == "moving along"


async def test_once_per_line(rig) -> None:
    robot, bus, _, client = rig
    await presentation_api._speak("Een zin.", _Beat())
    line = _offered(bus)
    _started(client, line)
    _started(client, line)
    assert len(robot.along) == 1


async def test_on_his_own_speaker_he_is_not_told_twice(rig) -> None:
    """He plays it himself, and moves with what he plays."""
    robot, _, monkeypatch, _ = rig
    monkeypatch.setenv("AUDIO_OUTPUT", "robot")
    await presentation_api._speak("Een zin op de robot.", _Beat())
    assert robot.spoken == ["Een zin op de robot."]
    assert robot.along == []


async def test_a_robot_older_than_the_app_costs_the_room_nothing(rig) -> None:
    robot, bus, _, client = rig
    robot.fail = httpx.HTTPStatusError(
        "404", request=httpx.Request("POST", "http://robot/robot/speak/along"),
        response=httpx.Response(404))
    await presentation_api._speak("Een zin.", _Beat())
    r = _started(client, _offered(bus))
    assert r.status_code == 200
    assert [e for e in bus.published if isinstance(e, SpeechLineStarted)], \
        "the subtitle still starts"
    assert "older" in r.json()["robot"], "and it says why he stood still"


async def test_a_robot_that_cannot_says_why(rig) -> None:
    robot, bus, _, client = rig
    robot.fail = RuntimeError("the robot answered 409: asleep")
    await presentation_api._speak("Een zin.", _Beat())
    r = _started(client, _offered(bus))
    assert r.status_code == 200
    assert "asleep" in r.json()["robot"]


async def test_stop_forgets_the_line(rig) -> None:
    robot, bus, _, client = rig
    await presentation_api._speak("Een zin.", _Beat())
    line = _offered(bus)
    speech_out.forget_all()
    _started(client, line)
    assert robot.along == []


async def test_this_unit_is_about_a_talk(rig) -> None:
    """An ordinary reply on the laptop is not part of what was asked."""
    robot, bus, _, client = rig
    await speech_out.deliver(robot, bus, "gewoon een antwoord", base64.b64encode(PCM).decode())
    _started(client, _offered(bus))
    assert robot.along == []


# ── the brain's client, against the real runtime on the fake robot ───────────

@pytest.fixture()
async def robot_client(monkeypatch):
    monkeypatch.setenv("ROBOT_ADAPTER", "fake")
    from aura_brain.robot_client import RobotClient
    from robot_runtime.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://robot") as http:
            yield RobotClient(client=http)


async def test_the_client_hands_the_robot_a_line_to_move_along_with(robot_client) -> None:
    await robot_client.connect()
    result = await robot_client.talk_along(base64.b64encode(PCM).decode())
    assert result["moving"] is True
    assert result["seconds"] == pytest.approx(SECONDS, abs=0.01)
