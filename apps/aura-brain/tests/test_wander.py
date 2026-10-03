"""U393: the brain's half of wandering — when it is on, and what he may say.

Agreed as (translated): a switch next to follow-me, "but review that this
cannot conflict with other settings and modes"; and when someone speaks to him
while he wanders, "he looks at them, but only speaks if the sound mode is on".

The robot decides how to wander and refuses to while asleep. The brain decides
WHETHER: the owner's switch, paused while a presentation runs (until U394 lets a
scenario decide), and re-asserted whenever the robot comes back, because the
robot does not remember it across a restart.
"""

from __future__ import annotations

import httpx
import pytest
from aura_brain import wander


class _Robot:
    def __init__(self, *, status: int = 200) -> None:
        self.calls: list[bool] = []
        self.status = status

    async def set_wander(self, enabled: bool, emotions: bool = False) -> dict:
        self.calls.append(enabled)
        self.emotions_told = emotions
        if self.status != 200:
            req = httpx.Request("POST", "http://robot/robot/wander")
            raise httpx.HTTPStatusError(
                "nope", request=req, response=httpx.Response(self.status, request=req))
        return {"enabled": enabled, "active": enabled, "sound_direction": True,
                "emotions": enabled and emotions}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("WANDER_ENABLED", raising=False)
    monkeypatch.delenv("WANDER_SOUND", raising=False)
    monkeypatch.setattr(wander, "_quiet", lambda: False)
    from aura_brain import presentation_api
    monkeypatch.setattr(presentation_api, "is_active", lambda: False)
    wander.forget()
    yield
    wander.forget()


def test_off_unless_the_owner_turns_it_on(monkeypatch) -> None:
    assert wander.effective() is False
    monkeypatch.setenv("WANDER_ENABLED", "true")
    assert wander.effective() is True


def test_a_presentation_pauses_it(monkeypatch) -> None:
    from aura_brain import presentation_api

    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setattr(presentation_api, "is_active", lambda: True)
    assert wander.effective() is False
    assert wander.status()["paused"] == "presentation"


async def test_apply_tells_the_robot_what_is_in_force(monkeypatch) -> None:
    robot = _Robot()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(robot)
    monkeypatch.setenv("WANDER_ENABLED", "false")
    await wander.apply(robot)
    assert robot.calls == [True, False]
    assert wander.status()["note"] == ""


async def test_a_robot_too_old_to_wander_is_said_so_not_failed(monkeypatch) -> None:
    """The Pi is older than the app: a 404 from the robot is a degradation the
    owner can act on, never an error that breaks the switch."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(_Robot(status=404))
    assert "update" in wander.status()["note"]


async def test_an_unreachable_robot_is_said_so(monkeypatch) -> None:
    class _Gone:
        async def set_wander(self, enabled, emotions=False):
            raise httpx.ConnectError("no route")

    monkeypatch.setenv("WANDER_ENABLED", "true")
    await wander.apply(_Gone())
    assert "reach" in wander.status()["note"]


def test_quiet_unless_his_wander_sound_allows_it(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    assert wander.sound() == "silent"
    assert wander.silences_speech() is True
    monkeypatch.setenv("WANDER_SOUND", "talk")
    assert wander.silences_speech() is False


def test_a_sound_setting_that_is_not_one_is_silent(monkeypatch) -> None:
    """A typo must never be the reason he starts talking."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "lound")
    assert wander.sound() == "silent"


def test_not_wandering_never_silences_him(monkeypatch) -> None:
    assert wander.silences_speech() is False


def test_the_switch_sits_next_to_follow_me() -> None:
    from aura_brain.capabilities_api import _CAPS

    keys = list(_CAPS)
    assert "wander" in keys
    assert keys.index("wander") == keys.index("body_follow") + 1
    env, default, *_ = _CAPS["wander"]
    assert (env, default) == ("WANDER_ENABLED", "false")


def _client(monkeypatch, tmp_path):
    from aura_brain import setup_api
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / "dev.env"))
    (tmp_path / "dev.env").write_text("", encoding="utf-8")
    app = FastAPI()
    app.include_router(setup_api.router)
    return TestClient(app)


def test_the_wander_sound_is_a_setting(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    assert c.post("/setup/prefs", json={"wander_sound": "talk"}).status_code == 200
    assert c.get("/setup/prefs").json()["wander_sound"] == "talk"
    assert c.post("/setup/prefs", json={"wander_sound": "shout"}).status_code == 422


# --------------------------------------------------------------------------- #
# U394: during a talk the scenario decides; afterwards the owner's settings
# --------------------------------------------------------------------------- #

def _stage(monkeypatch, *, wander=None, follow_me=None):
    from aura_brain import presentation_api

    monkeypatch.setattr(presentation_api, "is_active", lambda: True)
    monkeypatch.setattr(presentation_api, "stage_robot",
                        lambda: {"wander": wander, "follow_me": follow_me})


def test_a_scenario_can_make_him_wander_even_with_the_switch_off(monkeypatch) -> None:
    """The scenario is the owner's own script for that talk."""
    _stage(monkeypatch, wander=True)
    assert wander.wanted() is False
    assert wander.effective() is True


def test_a_scenario_that_says_nothing_still_pauses_it(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    _stage(monkeypatch, wander=None)
    assert wander.effective() is False
    assert wander.status()["paused"] == "presentation"


class _Tracker(_Robot):
    def __init__(self) -> None:
        super().__init__()
        self.tracking: list[bool] = []

    async def set_tracking(self, enabled: bool) -> bool:
        self.tracking.append(enabled)
        return enabled


async def test_a_scenario_overrides_follow_me_and_gives_it_back(monkeypatch) -> None:
    from aura_brain import presentation_api

    robot = _Tracker()
    monkeypatch.setenv("HEAD_TRACKING", "true")       # the owner has it on
    _stage(monkeypatch, follow_me=False)              # the demo wants him still
    await wander.apply(robot)
    assert robot.tracking == [False]

    monkeypatch.setattr(presentation_api, "is_active", lambda: False)   # End
    await wander.apply(robot)
    assert robot.tracking == [False, True], "the owner's follow-me must come back"


async def test_a_scenario_that_leaves_follow_me_alone_touches_nothing(monkeypatch) -> None:
    robot = _Tracker()
    _stage(monkeypatch, follow_me=None)
    await wander.apply(robot)
    assert robot.tracking == []

# --------------------------------------------------------------------------- #
# U395: emotion sounds — "maybe provide variations, e.g. just a hmm or giggling
# — emotion sounds, besides actually conversing" (translated)
# --------------------------------------------------------------------------- #

class _Emoter(_Robot):
    def __init__(self, *, status: int = 200) -> None:
        super().__init__()
        self.played: list[str] = []
        self.emotion_status = status

    async def play_emotion(self, name: str) -> dict:
        if self.emotion_status != 200:
            req = httpx.Request("POST", "http://robot/robot/emotion")
            raise httpx.HTTPStatusError(
                "nope", request=req, response=httpx.Response(self.emotion_status, request=req))
        self.played.append(name)
        return {"played": name}


def test_emotions_is_a_sound_level_between_silent_and_talk(monkeypatch) -> None:
    assert wander.SOUNDS == ("silent", "emotions", "talk")
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    assert wander.sound() == "emotions"
    assert wander.silences_speech() is True, "emotions mode makes sounds, not words"


def test_spontaneous_emotions_only_when_the_owner_allows_them(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    assert wander.spontaneous_emotions() is False            # silent
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    assert wander.spontaneous_emotions() is True
    monkeypatch.setenv("WANDER_SOUND", "talk")
    assert wander.spontaneous_emotions() is True, "talk is emotions and words"
    monkeypatch.setenv("WANDER_ENABLED", "false")
    assert wander.spontaneous_emotions() is False, "not wandering, no wander sounds"


def test_quiet_means_he_makes_no_sound_of_his_own(monkeypatch) -> None:
    """Quiet: he answers when asked, never starts (U256). A giggle at nobody
    is starting."""
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    monkeypatch.setattr(wander, "_quiet", lambda: True)
    assert wander.spontaneous_emotions() is False


def test_on_stage_only_the_scenario_makes_sound(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    _stage(monkeypatch, wander=True)
    assert wander.effective() is True
    assert wander.spontaneous_emotions() is False


async def test_apply_tells_the_robot_whether_emotions_are_allowed(monkeypatch) -> None:
    robot = _Robot()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    await wander.apply(robot)
    assert robot.emotions_told is True
    monkeypatch.setenv("WANDER_SOUND", "silent")
    await wander.apply(robot)
    assert robot.emotions_told is False


async def test_a_robot_too_old_for_emotions_is_said_so(monkeypatch) -> None:
    """The Pi is older than the app: it wanders, but ignores the new flag."""
    class _Older(_Robot):
        async def set_wander(self, enabled, emotions=False):
            return {"enabled": enabled, "active": enabled, "sound_direction": True}

    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    await wander.apply(_Older())
    assert "update" in wander.status()["note"]


@pytest.mark.parametrize("reply, emotion", [
    ("Haha, that is a good one!", "laughing2"),
    ("Sorry, I could not find it.", "oops1"),
    ("Wow, amazing!!", "enthusiastic2"),
    ("What do you mean?", "inquiring2"),
    ("It is half past nine.", "understanding2"),
])
def test_a_reply_becomes_an_emotion_that_fits_it(reply, emotion) -> None:
    assert wander.emotion_for(reply) == emotion


async def test_in_emotions_mode_he_answers_with_an_emotion(monkeypatch) -> None:
    robot = _Emoter()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    assert await wander.react(robot, "Haha, that is a good one!") == "laughing2"
    assert robot.played == ["laughing2"]


async def test_answering_with_an_emotion_is_not_starting(monkeypatch) -> None:
    """Quiet stops what he starts, not how he answers — the same line U256 drew
    for words."""
    robot = _Emoter()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    monkeypatch.setattr(wander, "_quiet", lambda: True)
    assert await wander.react(robot, "Sure.") == "understanding2"


@pytest.mark.parametrize("sound", ["silent", "talk"])
async def test_only_emotions_mode_answers_with_an_emotion(monkeypatch, sound) -> None:
    robot = _Emoter()
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", sound)
    assert await wander.react(robot, "Haha!") is None
    assert robot.played == []


async def test_on_stage_he_does_not_answer_with_an_emotion(monkeypatch) -> None:
    robot = _Emoter()
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    _stage(monkeypatch, wander=True)
    assert await wander.react(robot, "Haha!") is None


async def test_a_robot_too_old_to_play_emotions_is_said_so(monkeypatch) -> None:
    monkeypatch.setenv("WANDER_ENABLED", "true")
    monkeypatch.setenv("WANDER_SOUND", "emotions")
    assert await wander.react(_Emoter(status=404), "Haha!") is None
    assert "update" in wander.status()["note"]


def test_the_wander_sound_can_be_emotions(monkeypatch, tmp_path) -> None:
    c = _client(monkeypatch, tmp_path)
    assert c.post("/setup/prefs", json={"wander_sound": "emotions"}).status_code == 200
    assert c.get("/setup/prefs").json()["wander_sound"] == "emotions"


def test_switching_quiet_reaches_the_robot(monkeypatch, tmp_path) -> None:
    """Spontaneous emotions live on the robot; Quiet lives in the brain. A
    switch the robot never hears about would be a header and nothing else."""
    from orchestrator import mode_policy

    heard: list[bool] = []
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.on_quiet_change(heard.append)
    try:
        mode_policy.set_quiet(True)
        mode_policy.set_quiet(False)
    finally:
        mode_policy.on_quiet_change(heard.append, remove=True)
    assert heard == [True, False]


def test_changing_the_wander_sound_reaches_the_robot(monkeypatch, tmp_path) -> None:
    """Whether he may emote of his own accord is the robot's to act on: the
    choice in Settings has to reach it then, not at the next wake-up."""
    robot = _Robot()
    wander.bind(robot)
    monkeypatch.setenv("WANDER_ENABLED", "true")
    c = _client(monkeypatch, tmp_path)
    assert c.post("/setup/prefs", json={"wander_sound": "emotions"}).status_code == 200
    assert robot.emotions_told is True
    assert c.post("/setup/prefs", json={"wander_sound": "silent"}).status_code == 200
    assert robot.emotions_told is False
