"""U364: his voice can come out of the laptop instead of the robot.

Asked for as: "can we add option that audio can go via laptop (so default
robot, but we can also choose to go via audio of laptop?".

The console has had a "Laptop audio" switch since U209, and it reads the line
with the BROWSER's speech synthesis — a Windows voice, not his. It loses the
character (U349 gives each beat its own voice and speed) and it cannot do the
two-voice gag at all, because by then the line is just text again.

The brain already synthesizes the real thing before it ever reaches the robot.
So the choice is about where that audio is PLAYED, not about making it twice.
"""

from __future__ import annotations

import base64
import os
import struct

import pytest
from aura_brain import speech_out


class _Robot:
    def __init__(self) -> None:
        self.heard: list[tuple[str, str | None]] = []

    async def speak(self, text, audio_b64=None):
        self.heard.append((text, audio_b64))
        return True


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Leave no AUDIO_OUTPUT behind.

    `monkeypatch.delenv(raising=False)` on an unset variable records nothing to
    undo, so a test that POSTs `/setup/prefs` — which sets the real
    `os.environ` on purpose, that being how the setting takes effect without a
    restart — leaked `laptop` into every later test in the session. It broke
    `/robot/say` two files along, which is a long way from the cause.
    """
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    speech_out.forget_all()
    yield
    os.environ.pop("AUDIO_OUTPUT", None)
    speech_out.forget_all()


PCM = b"\x01\x02" * 1200          # 2400 bytes of stand-in s16le mono
AUDIO = base64.b64encode(PCM).decode()


# --------------------------------------------------------------------------- #
# the default is unchanged: he speaks, out of his own head
# --------------------------------------------------------------------------- #

async def test_by_default_the_robot_speaks() -> None:
    robot, bus = _Robot(), _Bus()
    assert await speech_out.deliver(robot, bus, "Hallo.", AUDIO) is True
    assert robot.heard == [("Hallo.", AUDIO)]
    assert bus.published == []


async def test_a_nonsense_setting_still_speaks(monkeypatch) -> None:
    """A typo in an env var must never be the reason a room hears nothing."""
    monkeypatch.setenv("AUDIO_OUTPUT", "speakers?")
    robot, bus = _Robot(), _Bus()
    await speech_out.deliver(robot, bus, "Hallo.", AUDIO)
    assert robot.heard, "an unknown value fell through to silence"


# --------------------------------------------------------------------------- #
# laptop: the SAME audio, played somewhere else
# --------------------------------------------------------------------------- #

async def test_the_laptop_gets_the_audio_and_the_robot_stays_quiet(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    assert await speech_out.deliver(robot, bus, "Hallo.", AUDIO) is True

    assert robot.heard == [], "the robot played it as well as the laptop"
    assert len(bus.published) == 1
    event = bus.published[0]
    assert event.text == "Hallo."
    assert event.utterance_id


async def test_the_audio_offered_is_byte_for_byte_his(monkeypatch) -> None:
    """The whole point of this unit over U209's: same voice, same speed, same
    mid-line persona switch — because it is the same bytes."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    await speech_out.deliver(robot, bus, "Hallo.", AUDIO)

    wav = speech_out.take(bus.published[0].utterance_id)
    assert wav is not None
    assert wav.endswith(PCM), "the laptop would play something other than his line"


async def test_it_is_a_playable_wav_not_raw_pcm(monkeypatch) -> None:
    """Served as WAV so the console can hand it to an <audio> element. Raw PCM
    would need decoding by hand in the browser for no reason."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    await speech_out.deliver(robot, bus, "Hallo.", AUDIO)
    wav = speech_out.take(bus.published[0].utterance_id)

    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    channels, rate, bits = struct.unpack("<H", wav[22:24])[0], \
        struct.unpack("<I", wav[24:28])[0], struct.unpack("<H", wav[34:36])[0]
    assert (channels, rate, bits) == (1, 24000, 16), "wrong format: it would play as noise"
    assert struct.unpack("<I", wav[4:8])[0] == len(wav) - 8, "RIFF size is wrong"


async def test_nothing_to_play_is_not_pretended_otherwise(monkeypatch) -> None:
    """No key, no TTS, no audio. Saying it was delivered would be the exact
    lie U269 was about."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    assert await speech_out.deliver(robot, bus, "Hallo.", None) is False
    assert bus.published == []


async def test_an_utterance_is_handed_over_once(monkeypatch) -> None:
    """It is played, not streamed on repeat — and holding every line of a talk
    in memory is how a long session turns into a leak."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    await speech_out.deliver(robot, bus, "Hallo.", AUDIO)
    uid = bus.published[0].utterance_id

    assert speech_out.take(uid) is not None
    assert speech_out.take(uid) is None, "the same utterance was served twice"


async def test_old_utterances_do_not_pile_up(monkeypatch) -> None:
    """A line nobody fetched (console closed, tab asleep) must not live for
    ever. The cap is small on purpose: this is a hand-over, not a store."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    for i in range(speech_out.KEEP + 5):
        await speech_out.deliver(robot, bus, f"line {i}", AUDIO)

    assert speech_out.pending() <= speech_out.KEEP
    oldest = bus.published[0].utterance_id
    assert speech_out.take(oldest) is None, "the first line was still being held"


# --------------------------------------------------------------------------- #
# the setting, over HTTP
# --------------------------------------------------------------------------- #

def _client(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aura_brain import setup_api
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    app = FastAPI()
    app.include_router(setup_api.router)
    app.include_router(speech_out.router)
    return TestClient(app)


def test_the_setting_defaults_to_the_robot(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    assert c.get("/setup/prefs").json()["audio_output"] == "robot"


def test_the_owner_can_send_his_voice_to_the_laptop(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    assert c.post("/setup/prefs", json={"audio_output": "laptop"}).status_code == 200
    assert c.get("/setup/prefs").json()["audio_output"] == "laptop"
    assert speech_out.output() == "laptop"


def test_a_destination_that_is_not_one_is_refused(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    r = c.post("/setup/prefs", json={"audio_output": "headphones"})
    assert r.status_code == 422
    assert "robot" in r.json()["error"] and "laptop" in r.json()["error"]


async def test_the_line_is_served_once_over_http(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    c = _client(monkeypatch, tmp_path)
    robot, bus = _Robot(), _Bus()
    await speech_out.deliver(robot, bus, "Hallo.", AUDIO)
    uid = bus.published[0].utterance_id

    first = c.get(f"/speech/{uid}.wav")
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert first.content.endswith(PCM)

    # Asking twice means something replayed; a room hearing the last sentence
    # again is worse than hearing nothing.
    assert c.get(f"/speech/{uid}.wav").status_code == 404


async def test_no_bus_means_not_delivered_rather_than_quietly_held(monkeypatch) -> None:
    """The event IS the delivery. Without a bus nothing will ever fetch the
    audio, so holding it and reporting success would be an utterance that no
    room can hear (ADR-009: constructing is not connecting)."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    assert await speech_out.deliver(_Robot(), None, "Hallo.", AUDIO) is False
    assert speech_out.pending() == 0, "a line nobody can fetch must not be held"


async def test_robot_say_asks_where_he_speaks(monkeypatch, tmp_path) -> None:
    """U364: /robot/say is how the console makes him say a line on demand, so
    it honours the setting like every other speaking path. It was the one that
    went straight to the robot."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    from aura_brain import robot_api

    robot, bus = _Robot(), _Bus()
    monkeypatch.setattr(robot_api, "_robot", robot)
    monkeypatch.setattr(robot_api, "_bus", bus)
    monkeypatch.setattr("aura_brain.voice.synthesize_b64",
                        _always(AUDIO), raising=True)

    body = await robot_api.say({"text": "Goedemorgen."})
    assert body.status_code == 200
    assert robot.heard == [], "the robot spoke although the laptop had it"
    assert [e.text for e in bus.published] == ["Goedemorgen."]


async def test_robot_say_still_reaches_the_robot_by_default(monkeypatch, tmp_path) -> None:
    from aura_brain import robot_api

    robot, bus = _Robot(), _Bus()
    monkeypatch.setattr(robot_api, "_robot", robot)
    monkeypatch.setattr(robot_api, "_bus", bus)
    monkeypatch.setattr("aura_brain.voice.synthesize_b64",
                        _always(AUDIO), raising=True)

    await robot_api.say({"text": "Goedemorgen."})
    assert [t for t, _ in robot.heard] == ["Goedemorgen."]
    assert bus.published == []


def _always(value):
    async def _f(*a, **k):
        return value
    return _f
