"""U334: on stage he says the scenario, and nothing else.

Reported as "in presentatie mode mag hij enkel iets zeggen op basis van
scenario, nu gaat hij praten los van het scenario (dit mag nooit gebeuren)".

Present mode already *declared* this — its behaviour row reads
`speaks_first: "never — cues only"` — but nothing enforced it, so every other
speaking path stayed live in front of an audience: a reply to a typed message,
a greeting when the camera recognised somebody in the room, a proactive line,
and (worst, because it needs no one to address him) an open Live session
answering whatever it heard.

The scenario itself speaks through a different door — `presentation_api._speak`
calls `robot.speak(text, audio_b64=…)` directly — so the gate closes the
conversational path without touching the show. The last test here is the one
that matters: it proves the gate did not silence the thing it exists to serve.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.embodiment import embodiment_plan, scenario_only
from orchestrator import mode_policy


@pytest.fixture(autouse=True)
def _restore_mode():
    before = mode_policy.active()
    yield
    mode_policy.set_active(before)


def test_the_policy_knows_which_mode_is_on_stage() -> None:
    mode_policy.set_active("work")
    assert mode_policy.presenting() is False
    mode_policy.set_active("presentation")
    assert mode_policy.presenting() is True
    assert mode_policy.active() == "presentation"
    assert scenario_only() is True


def test_a_reply_is_not_spoken_while_presenting() -> None:
    """The conversational path — typed replies, greetings, proactive lines."""
    mode_policy.set_active("presentation")
    speak, _motion, _amp = embodiment_plan("Hallo Jan, goedemorgen!", None)
    assert speak is False


def test_and_is_spoken_again_in_any_other_mode() -> None:
    for mode in ("work", "home"):
        mode_policy.set_active(mode)
        speak, motion, _amp = embodiment_plan("Hallo Jan!", None)
        assert speak is True, mode
        assert motion == "wave"


async def test_a_spoken_turn_opens_no_session_on_stage(monkeypatch) -> None:
    """An open microphone is the one that needs nobody to address him — with a
    film or an audience in the room it answers the room, on stage."""
    from aura_brain.voice_loop import VoiceLoop

    class _R:
        async def stream_audio(self, raw: bool = False):
            if False:
                yield b""

    class _Bus:
        async def publish(self, event) -> None: ...

    monkeypatch.setenv("VOICE_ENGINE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mode_policy.set_active("presentation")
    loop = VoiceLoop(robot=_R(), pipeline=None, bus=_Bus(), default_wake_word="richie")
    opened: list[int] = []

    async def _fake(wav, command):
        opened.append(1)
        return True

    monkeypatch.setattr(loop, "_live_session_turn", _fake)
    assert await loop._speech_turn(b"wav", "hallo") is False
    assert opened == []


async def test_the_scenario_itself_still_speaks(monkeypatch) -> None:
    """The whole point of the mode. If this ever fails, the gate has eaten the
    show it was supposed to protect."""
    from aura_brain import presentation_api, voice

    said: list[str] = []

    class _Robot:
        async def speak(self, text: str, audio_b64: str | None = None) -> bool:
            said.append(text)
            return True

    async def _fake_tts(text: str, voice_id: str | None = None) -> str:
        return "YXVkaW8="          # any non-empty base64 payload

    monkeypatch.setattr(voice, "synthesize_b64", _fake_tts)
    monkeypatch.setattr(presentation_api, "_robot", _Robot(), raising=False)
    mode_policy.set_active("presentation")

    await presentation_api._speak("Welkom bij deze presentatie.")

    assert said == ["Welkom bij deze presentatie."]


def test_switching_the_mode_actually_reaches_the_policy() -> None:
    """The gate is only as good as the thing that arms it. ruff caught this
    line calling an unimported module — a NameError on every mode switch —
    while every test above still passed, because none of them switched the
    mode the way the header does."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orchestrator import routes
    from orchestrator.intent_router import IntentRouter
    from orchestrator.persona_manager import PersonaManager

    app = FastAPI()
    app.include_router(routes.router)
    routes._router = IntentRouter()
    routes._persona_mgr = PersonaManager()
    try:
        mode_policy.set_active("work")
        resp = TestClient(app).post("/orchestrator/mode", json={"mode": "presentation"})
        assert resp.status_code == 200, resp.text
        assert mode_policy.presenting() is True
    finally:
        routes._router = None
        routes._persona_mgr = None
