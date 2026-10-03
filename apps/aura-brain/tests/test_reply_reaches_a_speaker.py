"""U384: an ordinary reply has to come out of a speaker — either one.

Reported as: "activated, but speaks via robot". Settings said *this laptop*.

Two things were wrong, and the first one was worse than the report:

1. U364 routed the reply path through `speech_out.deliver(_robot, bus, ...)`
   — and there is no `bus` in that scope. Every reply raised `NameError` on
   the way to *either* speaker, and `_embody_reply` logs failures at DEBUG,
   so nothing said so. In robot mode, the default, normal replies had been
   mute since U364 went live; only the gestures still ran. What the owner
   heard from the robot was the live engine, which speaks by another path.
2. Once that is fixed the laptop still hears nothing unless the event that
   tells the console to fetch the line is broadcast (see
   packages/shared-events/tests/test_broadcaster_coverage.py).

Every U364 test called `deliver()` or `/robot/say` directly. None of them ran a
reply through `_embody_reply`, which is the only path a conversation uses —
so these do, through the real lifespan, with only the robot and the TTS faked.
"""

from __future__ import annotations

import asyncio
import base64
import os

import pytest

PCM = b"\x01\x02" * 2400
AUDIO = base64.b64encode(PCM).decode()


class _Robot:
    """Records what it is told to say. Anything else the lifespan asks of a
    robot is answered with a harmless nothing."""

    def __init__(self, *a, **k) -> None:
        self.heard: list[tuple[str, str | None]] = []
        self.emoted: list[str] = []
        self._base_url = "http://fake-robot"

    async def speak(self, text, audio_b64=None):
        self.heard.append((text, audio_b64))
        return True

    async def play_emotion(self, name):
        self.emoted.append(name)
        return {"played": name}

    def __getattr__(self, name):
        async def _nothing(*a, **k):
            return None
        return _nothing


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Never the owner's data, never a real robot, never a real voice."""
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
        "VOICE_MODE": "off", "SPEAK_REPLIES": "true", "ROBOT_ASLEEP": "false",
        "EMOTION_ENABLED": "false", "SPEAK_STREAMING": "false",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)

    import aura_brain.robot_client as robot_client
    import aura_brain.voice as voice

    robots: list[_Robot] = []

    def _make(*a, **k):
        r = _Robot()
        robots.append(r)
        return r

    monkeypatch.setattr(robot_client, "RobotClient", _make)

    async def _synth(text, *a, **k):
        return AUDIO

    monkeypatch.setattr(voice, "synthesize_b64", _synth)

    # A fresh context per test. `ctx` is process-wide and the lifespan never
    # unsubscribes, so a second lifespan in the same process adds a second
    # `_embody_reply` and every reply is offered twice — a test artefact, not
    # what one running brain does.
    import aura_brain.main as brain_main

    monkeypatch.setattr(brain_main, "ctx", brain_main.BrainContext())
    yield robots
    os.environ.pop("AUDIO_OUTPUT", None)
    from aura_brain import speech_out
    speech_out.forget_all()


async def _reply(text: str):
    """Run one reply through the real brain and hand back what it did."""
    from aura_brain.main import create_app, ctx
    from shared_schemas.events.audio import SpeechAudioReady
    from shared_schemas.events.conversation import ResponseDrafted

    app = create_app()
    async with app.router.lifespan_context(app):
        offered: list[SpeechAudioReady] = []

        async def _probe(e: SpeechAudioReady) -> None:
            offered.append(e)

        ctx.bus.subscribe(SpeechAudioReady, _probe)
        await ctx.bus.publish(ResponseDrafted(session_id="default", response_text=text))
        for _ in range(100):
            await asyncio.sleep(0.02)
            if offered or any(r.heard or r.emoted for r in _ROBOTS):
                break
        await asyncio.sleep(0.05)
        return offered


_ROBOTS: list[_Robot] = []


async def test_by_default_a_reply_comes_out_of_the_robot(isolated) -> None:
    """The regression that mattered most: the default mode, mute."""
    _ROBOTS[:] = isolated
    offered = await _reply("Goedemorgen, alles klaar?")
    heard = [t for r in isolated for t, _ in r.heard]
    assert heard == ["Goedemorgen, alles klaar?"], (
        "the reply never reached the robot — _embody_reply failed silently")
    assert offered == []


async def test_with_the_laptop_chosen_the_reply_is_offered_to_the_laptop(
        isolated, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    _ROBOTS[:] = isolated
    offered = await _reply("Goedemorgen, alles klaar?")
    assert [e.text for e in offered] == ["Goedemorgen, alles klaar?"]
    assert all(r.heard == [] for r in isolated), "the robot spoke anyway"


async def test_wandering_silently_he_does_not_speak_the_reply(isolated, monkeypatch) -> None:
    """U393, as agreed (translated): "he looks at them, but only speaks if the
    sound mode is on". The robot turns to the voice by itself; the reply stays
    in the console."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "silent")
    _ROBOTS[:] = isolated
    offered = await _reply("Goedemorgen, alles klaar?")
    assert all(r.heard == [] for r in isolated)
    assert offered == []


async def test_wandering_with_talk_he_answers_as_usual(isolated, monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "talk")
    _ROBOTS[:] = isolated
    await _reply("Goedemorgen, alles klaar?")
    assert [t for r in isolated for t, _ in r.heard] == ["Goedemorgen, alles klaar?"]



async def test_wandering_with_emotions_he_answers_with_one(isolated, monkeypatch) -> None:
    """U395: the reply's mood as a sound and a movement — a giggle, a hmm —
    instead of the words. The words stay in the console."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    _ROBOTS[:] = isolated
    offered = await _reply("Haha, goeie!")
    assert all(r.heard == [] for r in isolated), "emotions mode makes sounds, not words"
    assert offered == []
    assert [e for r in isolated for e in r.emoted] == ["laughing2"]
