"""U409: a scenario directs HOW a line is spoken.

Reported (translated): *"In the presentation scenario I want to define not only
the persona and the voice, but also the direction: powerful, short, emotional,
…"*.

`_speak` handed the TTS the text and nothing else, and the provider called the
model without `instructions` — so `gpt-4o-mini-tts`, a model that performs a
line as directed, was never directed. Now a beat, a persona and the talk can
each say how; the narrowest one that does wins: the beat, then the persona
speaking, then the talk, then nothing.
"""

from __future__ import annotations

import base64
import json

import pytest
from aura_brain import presentation_api, voice
from aura_brain.characters import CharacterStore

PCM = b"\x00\x01" * 2400


class _TTS:
    """Records what each line was asked to be."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, text, voice_id=None, speed=1.0, instructions=""):
        self.calls.append({"text": text, "voice": voice_id, "instructions": instructions})
        return base64.b64encode(PCM).decode()

    def asked(self, text: str) -> str:
        return [c["instructions"] for c in self.calls if c["text"] == text][-1]


class _Robot:
    def __init__(self) -> None:
        self.audio: list[str] = []

    async def speak(self, text, audio_b64=None):
        self.audio.append(audio_b64)
        return True

    async def execute_motion(self, cmd):
        return True


class _Bus:
    async def publish(self, event):
        return None


class _NoSlides:
    def __init__(self, on_slide=None) -> None: ...
    def start(self) -> None: ...
    async def stop(self) -> None: ...
    state = None


@pytest.fixture()
def talk(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "recordings"))
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    monkeypatch.setenv("TTS_MODEL", "gpt-4o-mini-tts")
    from aura_brain import slides_watcher

    monkeypatch.setattr(slides_watcher, "SlidesWatcher", _NoSlides)
    robot = _Robot()
    presentation_api.init(robot, _Bus())
    presentation_api._runner = None
    presentation_api._kept = None
    presentation_api._voice_note = ""
    tts = _TTS()
    monkeypatch.setattr(voice, "synthesize_b64", tts)
    from aura_brain import recordings

    recordings.reset()

    async def run(beat: dict, scenario_direction: str = "") -> None:
        scenario = {"title": "t", "beats": [{"id": "b", "trigger": "manual", **beat}]}
        if scenario_direction:
            scenario["direction"] = scenario_direction
        r = await presentation_api.load_scenario({"scenario": scenario})
        assert r.status_code == 200, r.body
        await presentation_api.next_beat()

    yield run, tts, robot
    presentation_api._runner = None
    presentation_api._kept = None
    recordings.reset()


def _own(name: str) -> str:
    return CharacterStore().get(name).voice_direction


# ── who directs ──────────────────────────────────────────────────────────────

async def test_the_beat_says_how(talk) -> None:
    run, tts, _ = talk
    await run({"text": "Oh, I know this one.", "persona": "dry_tech_butler",
               "direction": "powerful, short"}, scenario_direction="warm")
    assert tts.asked("Oh, I know this one.") == "powerful, short"


async def test_then_the_persona_speaking_says_how(talk) -> None:
    run, tts, _ = talk
    assert _own("dry_tech_butler"), "a built-in comes with a way of speaking"
    await run({"text": "Goedendag.", "persona": "dry_tech_butler"}, scenario_direction="warm")
    assert tts.asked("Goedendag.") == _own("dry_tech_butler")


async def test_then_the_talk(talk) -> None:
    run, tts, _ = talk
    await run({"text": "Welkom."}, scenario_direction="warm, unhurried")
    assert tts.asked("Welkom.") == "warm, unhurried"


async def test_and_otherwise_nobody(talk) -> None:
    run, tts, _ = talk
    await run({"text": "Welkom."})
    assert tts.asked("Welkom.") == ""


async def test_a_voice_handed_over_mid_line_speaks_its_own_way(talk) -> None:
    run, tts, _ = talk
    await run({"text": "Goedendag. [persona:kids_companion] Hoi hoi!",
               "persona": "dry_tech_butler"})
    assert tts.asked("Goedendag.") == _own("dry_tech_butler")
    assert tts.asked("Hoi hoi!") == _own("kids_companion")


async def test_unless_the_beat_directs_the_whole_line(talk) -> None:
    run, tts, _ = talk
    await run({"text": "Goedendag. [persona:kids_companion] Hoi hoi!",
               "persona": "dry_tech_butler", "direction": "whispered"})
    assert tts.asked("Goedendag.") == "whispered"
    assert tts.asked("Hoi hoi!") == "whispered"


# ── a model that cannot be directed ─────────────────────────────────────────

async def test_a_model_that_cannot_take_a_direction_still_speaks_and_says_so(
        talk, monkeypatch) -> None:
    run, _, robot = talk
    monkeypatch.setenv("TTS_MODEL", "tts-1")
    await run({"text": "Oh, I know this one.", "direction": "powerful, short"})
    assert robot.audio, "the line is still spoken"
    note = presentation_api._status_payload()["voice_note"]
    assert "direction" in note and "tts-1" in note, \
        "never pretend the direction was applied (constitution XI)"


async def test_a_model_that_can_says_nothing(talk) -> None:
    run, _, _ = talk
    await run({"text": "Oh, I know this one.", "direction": "powerful, short"})
    assert presentation_api._status_payload()["voice_note"] == ""


# ── through the voice module ────────────────────────────────────────────────

async def test_the_direction_reaches_the_provider(monkeypatch) -> None:
    from conversation_runtime.providers import openai_provider

    seen: list[dict] = []

    class _Provider:
        def __init__(self, **kwargs) -> None: ...

        async def synthesize(self, text, instructions=""):
            seen.append({"text": text, "instructions": instructions})
            return PCM

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(openai_provider, "OpenAITTSProvider", _Provider)
    monkeypatch.setattr(voice, "_tts_cache", {})
    assert await voice.synthesize_b64("Hallo.", "ash", 1.0, instructions="warm") is not None
    assert seen == [{"text": "Hallo.", "instructions": "warm"}]


# ── a persona's own way of speaking ─────────────────────────────────────────

@pytest.fixture()
def personas(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    return CharacterStore(), tmp_path / "personas"


def test_the_built_ins_each_have_a_way_of_speaking(personas) -> None:
    store, _ = personas
    assert "dry" in store.get("dry_tech_butler").voice_direction
    assert "playful" in store.get("kids_companion").voice_direction
    assert "energetic" in store.get("workshop_coach").voice_direction


def test_a_persona_written_before_this_gets_its_built_in_one(personas) -> None:
    store, folder = personas
    store.all()
    path = folder / "kids_companion.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("voice_direction", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert "playful" in store.get("kids_companion").voice_direction


def test_one_of_your_own_has_none_until_you_give_it_one(personas) -> None:
    store, folder = personas
    store.all()
    (folder / "mine.json").write_text(json.dumps({"id": "mine"}), encoding="utf-8")
    assert store.get("mine").voice_direction == ""
    assert store.update("mine", {"voice_direction": "bright, quick"}).voice_direction \
        == "bright, quick"
    assert store.get("mine").voice_direction == "bright, quick"


def test_an_essay_is_not_a_direction(personas) -> None:
    store, _ = personas
    before = store.get("dry_tech_butler").voice_direction
    assert store.update("dry_tech_butler", {"voice_direction": "x" * 301}).voice_direction \
        == before


def test_the_characters_api_says_it(personas) -> None:
    from aura_brain import setup_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(setup_api.router)
    chars = TestClient(app).get("/setup/characters").json()["characters"]
    assert all("voice_direction" in c for c in chars)
