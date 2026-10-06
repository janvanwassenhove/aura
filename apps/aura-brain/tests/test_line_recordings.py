"""U409: a directed line sounds the same every time, and starts on the cue.

Reported (translated): the same line on the same slide *"sounds different on
every run, and starts with a delay"*.

Both were true, and both for one reason: every firing synthesized the line
afresh. `gpt-4o-mini-tts` is a generative model — each call is a new
performance — and the call is a network round-trip made at the cue, which on a
conference connection blows SC-002's 500 ms by itself.

Now each fixed line is recorded once, in the background, when the talk is
loaded; the cue plays the recording. Improvised lines cannot be recorded in
advance and are not. A take survives End, Run again and a restart, and is
replaced only when the line, its voice, its speed or its direction changes —
or when the presenter asks for another take.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from aura_brain import presentation_api, voice

TALK = {
    "title": "Devoxx",
    "direction": "warm",
    "beats": [
        {"id": "hello", "trigger": "manual", "mode": "speak", "text": "Goedemorgen, Devoxx."},
        {"id": "gag", "trigger": "manual", "mode": "speak", "text": "Oh, I know this one.",
         "direction": "powerful, short"},
        {"id": "riff", "trigger": "manual", "mode": "improvise", "topic": "the weather"},
        {"id": "duo", "trigger": "manual", "mode": "speak", "persona": "dry_tech_butler",
         "text": "Goedendag. [persona:kids_companion] Hoi hoi!"},
    ],
}
LINES = {"Goedemorgen, Devoxx.", "Oh, I know this one.", "Goedendag.", "Hoi hoi!"}


class _TTS:
    """A performance per call: each one sounds different, as the real model does."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: set[str] = set()
        self.delay = 0.0

    async def __call__(self, text, voice_id=None, speed=1.0, instructions=""):
        self.calls.append(text)
        if self.delay:
            await asyncio.sleep(self.delay)
        if text in self.fail:
            return None
        take = len(self.calls)
        return base64.b64encode(bytes([take % 251]) * 4800).decode()

    def count(self, text: str) -> int:
        return self.calls.count(text)


class _Robot:
    def __init__(self) -> None:
        self.heard: list[str] = []

    async def speak(self, text, audio_b64=None):
        self.heard.append(audio_b64)
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
def rig(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path / "personas"))
    monkeypatch.setenv("RECORDINGS_DIR", str(tmp_path / "recordings"))
    monkeypatch.setenv("TTS_MODEL", "gpt-4o-mini-tts")
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    from aura_brain import recordings, slides_watcher

    monkeypatch.setattr(slides_watcher, "SlidesWatcher", _NoSlides)

    async def improvised(topic, guardrails, engine, persona=""):
        return f"Over {topic}: zonnig."
    monkeypatch.setattr(presentation_api, "_generate", improvised)
    robot = _Robot()
    presentation_api.init(robot, _Bus())
    presentation_api._runner = None
    presentation_api._kept = None
    presentation_api._voice_note = ""
    tts = _TTS()
    monkeypatch.setattr(voice, "synthesize_b64", tts)
    recordings.reset()
    yield tts, robot
    presentation_api._runner = None
    presentation_api._kept = None
    recordings.reset()


async def _load(talk: dict = TALK) -> None:
    r = await presentation_api.load_scenario({"scenario": talk})
    assert r.status_code == 200, r.body


async def _settled() -> dict:
    for _ in range(300):
        rec = presentation_api._status_payload().get("recordings") or {}
        if rec and not rec.get("rendering"):
            return rec
        await asyncio.sleep(0.01)
    raise AssertionError(f"still recording: {rec}")


async def _fire(beat_id: str) -> None:
    """Advance until this beat has run."""
    for _ in range(len(TALK["beats"]) + 1):
        out = await presentation_api.next_beat()
        import json

        if json.loads(out.body)["fired"] == beat_id:
            return
    raise AssertionError(f"{beat_id} never fired")


# ── recorded before it is needed ────────────────────────────────────────────

async def test_loading_a_talk_records_every_fixed_line(rig) -> None:
    tts, _ = rig
    await _load()
    rec = await _settled()
    assert set(tts.calls) == LINES, "every voice of every fixed line, and nothing else"
    assert rec["ready"] == 3 and rec["total"] == 3 and rec["failed"] == 0, \
        "three lines — a line with two voices is still one line"
    assert rec["beats"] == {"hello": "ready", "gag": "ready", "duo": "ready"}


async def test_an_improvised_line_is_not_recorded_in_advance(rig) -> None:
    tts, _ = rig
    await _load()
    await _settled()
    assert not any("zonnig" in c for c in tts.calls)


# ── the same take, on the cue ───────────────────────────────────────────────

async def test_at_the_cue_nothing_is_synthesized(rig) -> None:
    tts, robot = rig
    await _load()
    await _settled()
    before = len(tts.calls)
    await _fire("hello")
    assert len(tts.calls) == before, "no round-trip at the cue"
    assert robot.heard


async def test_the_line_sounds_the_same_on_every_run(rig) -> None:
    tts, robot = rig
    await _load()
    await _settled()
    await _fire("gag")
    first = robot.heard[-1]
    await presentation_api.end_presentation()
    await _load()                                      # Run again
    await _settled()
    await _fire("gag")
    assert robot.heard[-1] == first, "the same take"
    assert tts.count("Oh, I know this one.") == 1


async def test_a_line_still_being_recorded_is_waited_for_not_asked_twice(rig) -> None:
    tts, robot = rig
    tts.delay = 0.2
    await _load()
    await _fire("hello")                               # before the render is back
    assert robot.heard and robot.heard[0]
    await _settled()
    assert tts.count("Goedemorgen, Devoxx.") == 1


# ── honest status ───────────────────────────────────────────────────────────

async def test_a_failed_recording_is_not_ready_and_is_tried_again_at_the_cue(rig) -> None:
    tts, robot = rig
    tts.fail = {"Oh, I know this one."}
    await _load()
    rec = await _settled()
    assert rec["ready"] == 2 and rec["failed"] == 1
    assert rec["beats"]["gag"] == "failed"
    tts.fail = set()
    await _fire("gag")
    assert tts.count("Oh, I know this one.") == 2
    assert robot.heard[-1]
    assert presentation_api._status_payload()["recordings"]["beats"]["gag"] == "ready"


async def test_if_the_retry_fails_too_the_beat_says_he_was_not_heard(rig) -> None:
    tts, _ = rig
    tts.fail = {"Oh, I know this one."}
    await _load()
    await _settled()
    await _fire("gag")
    assert presentation_api._status_payload().get("speech_error"), "U269: never a silent success"


# ── another take ────────────────────────────────────────────────────────────

async def test_rerecording_one_line_takes_it_again_and_only_it(rig) -> None:
    tts, robot = rig
    await _load()
    await _settled()
    await _fire("hello")
    await _fire("gag")
    old = robot.heard[-1]
    r = await presentation_api.rerecord({"beat_id": "gag"})
    assert r.status_code == 200
    await _settled()
    assert tts.count("Oh, I know this one.") == 2
    assert tts.count("Goedemorgen, Devoxx.") == 1
    await presentation_api.end_presentation()
    await _load()
    await _settled()
    await _fire("gag")
    assert robot.heard[-1] != old, "the new take is the one he plays"


async def test_rerecording_everything(rig) -> None:
    tts, _ = rig
    await _load()
    await _settled()
    r = await presentation_api.rerecord({})
    assert r.status_code == 200
    await _settled()
    assert all(tts.count(line) == 2 for line in LINES)


async def test_rerecording_says_what_it_cannot_do(rig) -> None:
    r = await presentation_api.rerecord({"beat_id": "gag"})
    assert r.status_code == 409, "nothing loaded"
    await _load()
    assert (await presentation_api.rerecord({"beat_id": "nope"})).status_code == 404
    assert (await presentation_api.rerecord({"beat_id": "riff"})).status_code == 422, \
        "an improvised line has no recording to take again"


async def test_a_changed_direction_is_a_new_recording(rig) -> None:
    tts, _ = rig
    await _load()
    await _settled()
    changed = {**TALK, "beats": [
        {**b, "direction": "whispered"} if b["id"] == "gag" else b for b in TALK["beats"]]}
    await _load(changed)
    await _settled()
    assert tts.count("Oh, I know this one.") == 2
    assert tts.count("Goedemorgen, Devoxx.") == 1


# ── kept between rehearsal and the talk ─────────────────────────────────────

async def test_the_rehearsed_take_survives_a_restart(rig) -> None:
    tts, robot = rig
    from aura_brain import recordings

    await _load()
    await _settled()
    await _fire("gag")
    rehearsed = robot.heard[-1]
    recordings.store().clear_memory()                  # what a restart forgets
    presentation_api._runner = None
    presentation_api._kept = None
    await _load()
    await _settled()
    await _fire("gag")
    assert robot.heard[-1] == rehearsed
    assert tts.count("Oh, I know this one.") == 1
