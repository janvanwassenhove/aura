"""U349: a scenario hands beats — and parts of single lines — to other characters.

Reported as: for presenter mode, be able to change the robot persona from the
scenario, "also in one text so it can switch to different kind of vocals".

Two things are being pinned here:

  - a beat's `persona` reaches TTS as that character's OWN voice and speed,
    where before every beat came out in the one presentation voice;
  - `[persona:x]` inside a line produces several synthesis calls that reach the
    robot as ONE utterance, because an utterance is the unit the robot decides
    loudness on (FR-019) — sending the halves separately is how you get a
    character change that is also a volume change.
"""

from __future__ import annotations

import base64

import pytest
from aura_brain import presentation_api, voice
from fastapi import FastAPI
from fastapi.testclient import TestClient

# dry_tech_butler is ash @ 0.95, kids_companion is nova @ 1.05 (built-ins).
TWO_VOICES_YAML = """
title: Personas
beats:
  - id: butler
    trigger: manual
    mode: speak
    persona: dry_tech_butler
    text: "Goedendag."
  - id: handover
    trigger: manual
    mode: speak
    persona: dry_tech_butler
    text: "Ik stel mijn collega voor. [persona:kids_companion]Hoi hoi![persona] Dank u."
  - id: plain
    trigger: manual
    mode: speak
    text: "Gewoon mijn eigen stem."
"""


class _FakeRobot:
    def __init__(self) -> None:
        self.heard: list[tuple[str, str | None]] = []

    async def speak(self, text, audio_b64=None):
        self.heard.append((text, audio_b64))
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
    """A brain with a throwaway character store and a TTS that only records.

    CHARACTERS_DIR is redirected because CharacterStore SEEDS the built-ins on
    first read — pointed at the repo it would write into the real ./personas.
    """
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("TTS_VOICE_PRESENTATION", raising=False)

    robot, bus = _FakeRobot(), _FakeBus()
    presentation_api.init(robot, bus)
    presentation_api._runner = None
    presentation_api._voice_note = ""

    calls: list[tuple[str, str, float]] = []

    async def recording_tts(text, voice_id=None, speed=1.0):
        calls.append((text, voice_id or "", speed))
        # Stand-in PCM whose bytes name the voice, so the joined utterance can
        # be read back and checked.
        return base64.b64encode((voice_id or "?").encode()).decode()

    monkeypatch.setattr(voice, "synthesize_b64", recording_tts)

    app = FastAPI()
    app.include_router(presentation_api.router)
    yield TestClient(app), robot, bus, calls
    presentation_api._runner = None


def _load(c, yaml_text=TWO_VOICES_YAML):
    assert c.post("/presentation/scenario", json={"yaml": yaml_text}).status_code == 200


# --------------------------------------------------------------------------- #
# joining PCM — one utterance, however many voices are in it
# --------------------------------------------------------------------------- #

def test_joining_segments_concatenates_the_decoded_audio() -> None:
    a = base64.b64encode(b"one").decode()
    b = base64.b64encode(b"two").decode()
    assert base64.b64decode(voice.join_pcm_b64([a, b])) == b"onetwo"


def test_a_handover_pause_goes_between_the_segments_only() -> None:
    a = base64.b64encode(b"one").decode()
    b = base64.b64encode(b"two").decode()
    joined = base64.b64decode(voice.join_pcm_b64([a, b], pause_ms=10))
    silence = b"\x00" * (24000 * 2 * 10 // 1000)
    assert joined == b"one" + silence + b"two"


def test_joining_one_or_no_segments_is_not_clever_about_it() -> None:
    only = base64.b64encode(b"one").decode()
    assert voice.join_pcm_b64([only], pause_ms=10) == only
    assert voice.join_pcm_b64([]) == ""
    assert voice.join_pcm_b64([None, only, ""], pause_ms=0) == only


# --------------------------------------------------------------------------- #
# a beat is spoken by its own character
# --------------------------------------------------------------------------- #

def test_a_beat_uses_its_personas_own_voice_and_speed(rig) -> None:
    """Before U349 every beat resolved with mode="presentation" and nothing
    else, so a scenario could not change who was speaking at all."""
    c, robot, _, calls = rig
    _load(c)
    c.post("/presentation/next")                       # butler

    assert calls == [("Goedendag.", "ash", 0.95)]
    assert robot.heard[0][0] == "Goedendag."


def test_a_beat_without_a_persona_keeps_the_presentation_voice(rig) -> None:
    c, robot, _, calls = rig
    _load(c)
    for _ in range(3):
        c.post("/presentation/next")

    assert calls[-1] == ("Gewoon mijn eigen stem.", "alloy", 1.0)


def test_the_present_voice_setting_still_wins_when_no_persona_is_named(rig, monkeypatch) -> None:
    """U273's Voice dropdown must keep working — a persona-less beat is still
    the presentation's own voice, not a new default."""
    monkeypatch.setenv("TTS_VOICE_PRESENTATION", "shimmer")
    c, _, _, calls = rig
    _load(c)
    for _ in range(3):
        c.post("/presentation/next")

    assert calls[-1][1] == "shimmer"
    assert calls[0][1] == "ash", "a persona still overrides the mode voice"


# --------------------------------------------------------------------------- #
# several voices inside one line
# --------------------------------------------------------------------------- #

def test_one_line_can_be_spoken_by_two_characters(rig) -> None:
    c, robot, _, calls = rig
    _load(c)
    c.post("/presentation/next")                       # butler
    c.post("/presentation/next")                       # handover

    assert [(t, v) for t, v, _ in calls[1:]] == [
        ("Ik stel mijn collega voor.", "ash"),
        ("Hoi hoi!", "nova"),
        ("Dank u.", "ash"),
    ]


def test_the_markers_are_never_spoken(rig) -> None:
    c, robot, _, calls = rig
    _load(c)
    c.post("/presentation/next")
    c.post("/presentation/next")

    for text, _, _ in calls:
        assert "persona" not in text and "[" not in text
    # ...and the subtitle the room reads is the clean line, not the markup.
    said = robot.heard[-1][0]
    assert said == "Ik stel mijn collega voor. Hoi hoi! Dank u."


def test_a_multi_voice_line_reaches_the_robot_as_one_utterance(rig) -> None:
    """FR-019: the robot decides loudness once per utterance. Two speak calls
    would be two gain decisions, so the character change would be audible as a
    volume change as well."""
    c, robot, _, _ = rig
    _load(c)
    c.post("/presentation/next")
    before = len(robot.heard)
    c.post("/presentation/next")

    assert len(robot.heard) - before == 1
    audio = base64.b64decode(robot.heard[-1][1])
    assert audio.startswith(b"ash") and audio.endswith(b"ash")
    assert b"nova" in audio


def test_a_dead_segment_does_not_let_a_half_line_pass_as_whole(rig, monkeypatch) -> None:
    """If one voice cannot be synthesized, speaking the rest would drop a
    sentence in the middle of a talk with nothing anywhere saying so."""
    c, robot, _, _ = rig

    async def only_the_butler(text, voice_id=None, speed=1.0):
        if voice_id == "nova":
            return None
        return base64.b64encode((voice_id or "?").encode()).decode()

    monkeypatch.setattr(voice, "synthesize_b64", only_the_butler)
    _load(c)
    c.post("/presentation/next")
    c.post("/presentation/next")

    assert len(robot.heard) == 1, "the half line must not be played as if whole"
    assert "synthesi" in c.get("/presentation/status").json()["speech_error"]


# --------------------------------------------------------------------------- #
# a persona that is not there is reported, not silently ignored
# --------------------------------------------------------------------------- #

def test_an_unknown_persona_falls_back_and_says_so(rig) -> None:
    """Constitution XI: the line still has to be heard, but a talk that quietly
    used the wrong voice is exactly the kind of success this repo does not get
    to claim."""
    c, robot, _, calls = rig
    _load(c, """
title: Typo
beats:
  - id: oops
    trigger: manual
    mode: speak
    persona: dry_tech_buttler
    text: "Goedendag."
""")
    c.post("/presentation/next")

    assert calls == [("Goedendag.", "alloy", 1.0)]     # heard, in the fallback
    note = c.get("/presentation/status").json()["voice_note"]
    assert "dry_tech_buttler" in note


def test_the_note_clears_once_every_persona_resolves(rig) -> None:
    c, _, _, _ = rig
    _load(c, """
title: Mixed
beats:
  - id: oops
    trigger: manual
    mode: speak
    persona: nobody_here
    text: "Eerst."
  - id: fine
    trigger: manual
    mode: speak
    persona: dry_tech_butler
    text: "Daarna."
""")
    c.post("/presentation/next")
    assert c.get("/presentation/status").json()["voice_note"]
    c.post("/presentation/next")
    assert c.get("/presentation/status").json()["voice_note"] == ""


# --------------------------------------------------------------------------- #
# the persona shapes the improvised line, not just its timbre
# --------------------------------------------------------------------------- #

def test_an_improvised_beat_is_written_in_its_characters_voice(rig, monkeypatch) -> None:
    seen: list[str] = []

    async def fake_chat(messages, **kw):
        seen.append(messages[0]["content"])
        return {"content": "Iets verzonnen."}

    import orchestrator.llm as llm
    monkeypatch.setattr(llm, "openai_chat", fake_chat)

    c, _, _, calls = rig
    _load(c, """
title: Improv
beats:
  - id: i
    trigger: manual
    mode: improvise
    persona: kids_companion
    topic: "de toekomst"
""")
    c.post("/presentation/next")

    assert seen and "Kids Companion" in seen[0]
    # ...and it is read out in that character's voice as well.
    assert calls == [("Iets verzonnen.", "nova", 1.05)]


def test_the_beat_persona_is_published_with_the_subtitle(rig) -> None:
    c, _, bus, _ = rig
    _load(c)
    c.post("/presentation/next")

    fired = [e for e in bus.published if getattr(e, "beat_id", "") == "butler"]
    assert fired and fired[0].persona == "dry_tech_butler"


def test_a_new_talk_does_not_inherit_the_last_ones_complaint(rig) -> None:
    """The note describes the line that was just spoken. Carried into the next
    scenario it would accuse a talk of something the previous one did."""
    c, _, _, _ = rig
    _load(c, """
title: Typo
beats:
  - id: oops
    trigger: manual
    mode: speak
    persona: nobody_here
    text: "Eerst."
""")
    c.post("/presentation/next")
    assert c.get("/presentation/status").json()["voice_note"]

    _load(c)                                   # a different talk starts
    assert c.get("/presentation/status").json()["voice_note"] == ""
