"""U400: the subtitles follow his voice.

Reported, in Present (translated): *"it seems like subtitles are not following
fluently with talking, should be in sync"*.

They were not in sync, and with the robot's own speaker they could not be:

* the subtitle came from `beat_done`, which the runner emits after the beat
  has been spoken — and the robot's `speak` returns only once the line has
  finished playing (it blocks for its duration). So the room read each line
  after hearing it, and after the gesture that followed;
* through the laptop it arrived roughly when the voice did, but as one block
  for the whole line, held for an estimate (66 ms a character) rather than for
  as long as he actually spoke.

Now the line is announced with its real duration at the moment it starts:
just before the robot is handed the audio, or — through the laptop — when
the window that plays it says it has started, which reaches the overlay
through the brain because the overlay is another window.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from aura_brain import presentation_api, speech_out, voice
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared_schemas.events.audio import SpeechAudioReady, SpeechLineStarted
from shared_schemas.events.system import PresentationSubtitle

SECONDS = 2.5
PCM = b"\x00\x01" * int(24000 * SECONDS)       # 24 kHz, 16-bit mono


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


class _Robot:
    """Plays for as long as the line lasts, as the real one does."""

    def __init__(self, bus: _Bus) -> None:
        self.bus = bus
        self.seen_before_playing: list = []

    async def speak(self, text, audio_b64=None):
        self.seen_before_playing = list(self.bus.published)
        await asyncio.sleep(0)
        return True

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
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    bus = _Bus()
    robot = _Robot(bus)
    presentation_api.init(robot, bus)
    presentation_api._runner = None
    presentation_api._kept = None
    presentation_api._voice_note = ""

    async def tts(text, voice_id=None, speed=1.0, instructions=""):
        return base64.b64encode(PCM).decode()
    monkeypatch.setattr(voice, "synthesize_b64", tts)
    speech_out.forget_all()
    yield robot, bus, monkeypatch
    speech_out.forget_all()


def _subtitles(bus: _Bus) -> list[PresentationSubtitle]:
    return [e for e in bus.published if isinstance(e, PresentationSubtitle)]


async def test_on_the_robot_the_line_is_announced_before_it_plays(rig) -> None:
    robot, bus, _ = rig
    await presentation_api._speak("Goedemorgen. Ik ben de junior dev.", _Beat())
    assert [type(e) for e in robot.seen_before_playing] == [PresentationSubtitle], \
        "the room must be able to read it while he says it, not after"
    sub = _subtitles(bus)[0]
    assert sub.text == "Goedemorgen. Ik ben de junior dev."
    assert sub.beat_id == "hello"
    assert sub.utterance_id == "", "the robot starts at once: no start to wait for"


async def test_it_carries_how_long_he_actually_speaks(rig) -> None:
    _robot, bus, _ = rig
    await presentation_api._speak("Een zin.", _Beat())
    assert _subtitles(bus)[0].duration_s == pytest.approx(SECONDS, abs=0.01)


async def test_through_the_laptop_it_waits_for_the_window_that_plays_it(rig) -> None:
    _robot, bus, monkeypatch = rig
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    await presentation_api._speak("Een zin via de laptop.", _Beat())
    subs = _subtitles(bus)
    ready = [e for e in bus.published if isinstance(e, SpeechAudioReady)]
    assert len(subs) == 1 and len(ready) == 1
    assert subs[0].utterance_id == ready[0].utterance_id, "tied to the line it subtitles"
    assert bus.published.index(subs[0]) < bus.published.index(ready[0]), \
        "known before anything can start playing it"
    assert subs[0].duration_s == pytest.approx(SECONDS, abs=0.01)


def test_the_player_says_when_it_starts(rig) -> None:
    _robot, bus, _ = rig
    speech_out.bind_bus(bus)
    app = FastAPI()
    app.include_router(speech_out.router)
    r = TestClient(app).post("/speech/abc123/started", json={"duration_s": 2.4})
    assert r.status_code == 200
    started = [e for e in bus.published if isinstance(e, SpeechLineStarted)]
    assert [(e.utterance_id, e.duration_s) for e in started] == [("abc123", 2.4)]


async def test_ordinary_replies_carry_no_subtitle(rig) -> None:
    """Only a talk is subtitled on the projector."""
    robot, bus, _ = rig
    await speech_out.deliver(robot, bus, "gewoon een antwoord",
                             base64.b64encode(PCM).decode())
    assert _subtitles(bus) == []


async def test_the_running_brain_listens_for_the_players_start(monkeypatch, tmp_path) -> None:
    """Through the real lifespan: the route is only worth anything if the brain
    gives it its bus."""
    for k, v in {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "LLM_PROVIDER": "echo", "STT_PROVIDER": "null",
        "KNOWLEDGE_DB_PATH": str(tmp_path / "k.db"),
        "RECOGNITION_DB_PATH": str(tmp_path / "r.db"),
        "MODE_POLICY_PATH": str(tmp_path / "mode.json"),
        "SKILLS_DIR": str(tmp_path / "skills"),
        "CONNECTOR_PREFS_PATH": str(tmp_path / "conn.json"),
        "MCP_SERVERS_PATH": str(tmp_path / "mcp.json"),
        "AURA_ENV_FILE": str(tmp_path / "dev.env"),
        "ROBOT_AUTOFIND": "false", "ROBOT_RUNTIME_URL": "http://127.0.0.1:9",
        "VOICE_MODE": "off",
    }.items():
        monkeypatch.setenv(k, v)
    import aura_brain.main as brain_main

    monkeypatch.setattr(brain_main, "ctx", brain_main.BrainContext())
    speech_out.bind_bus(None)
    app = brain_main.create_app()
    async with app.router.lifespan_context(app):
        assert speech_out._bus is brain_main.ctx.bus
