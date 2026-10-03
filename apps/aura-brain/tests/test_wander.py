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
def _clean(monkeypatch, tmp_path):
    from orchestrator import mode_policy

    # U397: wandering is a behaviour of the active mode, kept in the policy.
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.reset_cache_for_tests()
    mode_policy.set_active("work")
    monkeypatch.setattr(wander, "_quiet", lambda: False)
    from aura_brain import presentation_api
    monkeypatch.setattr(presentation_api, "is_active", lambda: False)
    wander.forget()
    yield
    wander.forget()
    mode_policy.set_active("work")
    mode_policy.reset_cache_for_tests()


def _owner(*, wander: bool | None = None, sound: str | None = None, mode: str = "work") -> None:
    """What the owner chose in Modes for `mode`, and that mode active."""
    from orchestrator import mode_policy

    update = {}
    if wander is not None:
        update["wander"] = "on" if wander else "off"
    if sound is not None:
        update["wander_sound"] = sound
    if update:
        mode_policy.set_behaviour(mode, update)
    mode_policy.set_active(mode)


def test_off_unless_the_owner_turns_it_on(monkeypatch) -> None:
    assert wander.effective() is False
    _owner(wander=True)
    assert wander.effective() is True


def test_a_presentation_pauses_it(monkeypatch) -> None:
    from aura_brain import presentation_api

    _owner(wander=True)
    monkeypatch.setattr(presentation_api, "is_active", lambda: True)
    assert wander.effective() is False
    assert wander.status()["paused"] == "presentation"


async def test_apply_tells_the_robot_what_is_in_force(monkeypatch) -> None:
    robot = _Robot()
    _owner(wander=True)
    await wander.apply(robot)
    _owner(wander=False)
    await wander.apply(robot)
    assert robot.calls == [True, False]
    assert wander.status()["note"] == ""


async def test_a_robot_too_old_to_wander_is_said_so_not_failed(monkeypatch) -> None:
    """The Pi is older than the app: a 404 from the robot is a degradation the
    owner can act on, never an error that breaks the switch."""
    _owner(wander=True)
    await wander.apply(_Robot(status=404))
    assert "update" in wander.status()["note"]


async def test_an_unreachable_robot_is_said_so(monkeypatch) -> None:
    class _Gone:
        async def set_wander(self, enabled, emotions=False):
            raise httpx.ConnectError("no route")

    _owner(wander=True)
    await wander.apply(_Gone())
    assert "reach" in wander.status()["note"]


def test_quiet_unless_his_wander_sound_allows_it(monkeypatch) -> None:
    _owner(wander=True)
    assert wander.sound() == "silent"
    assert wander.silences_speech() is True
    _owner(sound="talk")
    assert wander.silences_speech() is False


def test_a_sound_setting_that_is_not_one_is_silent(monkeypatch, tmp_path) -> None:
    """A typo must never be the reason he starts talking — not even one made
    by hand in the policy file, which the Modes editor would have refused."""
    import json

    from orchestrator import mode_policy

    (tmp_path / "policy.json").write_text(json.dumps({"behaviour": {
        "work": {"wander": "on", "wander_sound": "lound"}}}), encoding="utf-8")
    mode_policy.reset_cache_for_tests()
    assert wander.effective() is True
    assert wander.sound() == "silent"


def test_not_wandering_never_silences_him(monkeypatch) -> None:
    assert wander.silences_speech() is False


def test_wandering_is_not_a_setting_any_more() -> None:
    """U397, asked as (translated): "doing it via Settings seems so strange".
    Where he is decides whether he wanders — it is a behaviour of each mode."""
    from aura_brain.capabilities_api import _CAPS

    assert "wander" not in _CAPS


def _client():
    """The Modes editor's route — where wandering is set now (U397)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from orchestrator import routes as orchestrator_routes

    app = FastAPI()
    app.include_router(orchestrator_routes.router)
    return TestClient(app)


def _behaviour(c, mode: str, **update):
    return c.post("/orchestrator/policy/behaviour", json={"mode": mode, "behaviour": update})


def test_the_wander_sound_is_set_per_mode() -> None:
    c = _client()
    assert _behaviour(c, "work", wander_sound="talk").status_code == 200
    _owner(wander=True)
    assert wander.sound() == "talk"
    assert _behaviour(c, "work", wander_sound="shout").status_code == 422


def test_each_mode_has_its_own_wandering() -> None:
    _owner(wander=True, sound="emotions", mode="home")
    _owner(mode="work")
    assert wander.effective() is False
    _owner(mode="home")
    assert wander.effective() is True and wander.sound() == "emotions"


def test_at_a_stand_he_wanders_and_talks_without_being_told() -> None:
    _owner(mode="stand")
    assert wander.effective() is True
    assert wander.sound() == "talk"
    assert wander.spontaneous_emotions() is True


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
    _owner(wander=True)
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
    _owner(wander=True)
    _owner(sound="emotions")
    assert wander.sound() == "emotions"
    assert wander.silences_speech() is True, "emotions mode makes sounds, not words"


def test_spontaneous_emotions_only_when_the_owner_allows_them(monkeypatch) -> None:
    _owner(wander=True)
    assert wander.spontaneous_emotions() is False            # silent
    _owner(sound="emotions")
    assert wander.spontaneous_emotions() is True
    _owner(sound="talk")
    assert wander.spontaneous_emotions() is True, "talk is emotions and words"
    _owner(wander=False)
    assert wander.spontaneous_emotions() is False, "not wandering, no wander sounds"


def test_quiet_means_he_makes_no_sound_of_his_own(monkeypatch) -> None:
    """Quiet: he answers when asked, never starts (U256). A giggle at nobody
    is starting."""
    _owner(wander=True)
    _owner(sound="emotions")
    monkeypatch.setattr(wander, "_quiet", lambda: True)
    assert wander.spontaneous_emotions() is False


def test_on_stage_only_the_scenario_makes_sound(monkeypatch) -> None:
    _owner(sound="emotions")
    _stage(monkeypatch, wander=True)
    assert wander.effective() is True
    assert wander.spontaneous_emotions() is False


async def test_apply_tells_the_robot_whether_emotions_are_allowed(monkeypatch) -> None:
    robot = _Robot()
    _owner(wander=True)
    _owner(sound="emotions")
    await wander.apply(robot)
    assert robot.emotions_told is True
    _owner(sound="silent")
    await wander.apply(robot)
    assert robot.emotions_told is False


async def test_a_robot_too_old_for_emotions_is_said_so(monkeypatch) -> None:
    """The Pi is older than the app: it wanders, but ignores the new flag."""
    class _Older(_Robot):
        async def set_wander(self, enabled, emotions=False):
            return {"enabled": enabled, "active": enabled, "sound_direction": True}

    _owner(wander=True)
    _owner(sound="emotions")
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
    _owner(wander=True)
    _owner(sound="emotions")
    assert await wander.react(robot, "Haha, that is a good one!") == "laughing2"
    assert robot.played == ["laughing2"]


async def test_answering_with_an_emotion_is_not_starting(monkeypatch) -> None:
    """Quiet stops what he starts, not how he answers — the same line U256 drew
    for words."""
    robot = _Emoter()
    _owner(wander=True)
    _owner(sound="emotions")
    monkeypatch.setattr(wander, "_quiet", lambda: True)
    assert await wander.react(robot, "Sure.") == "understanding2"


@pytest.mark.parametrize("sound", ["silent", "talk"])
async def test_only_emotions_mode_answers_with_an_emotion(monkeypatch, sound) -> None:
    robot = _Emoter()
    _owner(wander=True)
    _owner(sound=sound)
    assert await wander.react(robot, "Haha!") is None
    assert robot.played == []


async def test_on_stage_he_does_not_answer_with_an_emotion(monkeypatch) -> None:
    robot = _Emoter()
    _owner(sound="emotions")
    _stage(monkeypatch, wander=True)
    assert await wander.react(robot, "Haha!") is None


async def test_a_robot_too_old_to_play_emotions_is_said_so(monkeypatch) -> None:
    _owner(wander=True)
    _owner(sound="emotions")
    assert await wander.react(_Emoter(status=404), "Haha!") is None
    assert "update" in wander.status()["note"]


def test_the_wander_sound_can_be_emotions() -> None:
    c = _client()
    assert _behaviour(c, "work", wander_sound="emotions").status_code == 200
    _owner(wander=True)
    assert wander.sound() == "emotions"


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


def _until(check, timeout: float = 2.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "the robot was never told"
        time.sleep(0.02)


def test_changing_the_wander_sound_reaches_the_robot() -> None:
    """Whether he may emote of his own accord is the robot's to act on: the
    choice in Modes has to reach it then, not at the next wake-up."""
    from orchestrator import mode_policy

    robot = _Robot()
    wander.bind(robot)
    _owner(wander=True)
    mode_policy.on_mode_change(wander.mode_changed)
    try:
        c = _client()
        assert _behaviour(c, "work", wander_sound="emotions").status_code == 200
        _until(lambda: getattr(robot, "emotions_told", None) is True)
        assert _behaviour(c, "work", wander_sound="silent").status_code == 200
        _until(lambda: robot.emotions_told is False)
    finally:
        mode_policy.on_mode_change(wander.mode_changed, remove=True)


def test_switching_to_the_stand_sets_him_wandering(monkeypatch) -> None:
    """One click in the header, as asked — no trip to Settings or Modes."""
    from orchestrator import mode_policy

    robot = _Robot()
    wander.bind(robot)
    mode_policy.on_mode_change(wander.mode_changed)
    try:
        c = _client()
        from orchestrator import routes as orchestrator_routes
        from orchestrator.intent_router import IntentRouter

        monkeypatch.setattr(orchestrator_routes, "_router", IntentRouter(mode="work"))
        assert c.post("/orchestrator/mode", json={"mode": "stand"}).status_code == 200
        _until(lambda: robot.calls[-1:] == [True])
        assert c.post("/orchestrator/mode", json={"mode": "work"}).status_code == 200
        _until(lambda: robot.calls[-1:] == [False])
    finally:
        mode_policy.on_mode_change(wander.mode_changed, remove=True)


async def test_the_brain_listens_for_mode_and_quiet(monkeypatch, tmp_path) -> None:
    """Through the real lifespan: the listeners above are only worth anything
    if the running brain registers them."""
    from orchestrator import mode_policy

    for k, v in {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "LLM_PROVIDER": "echo", "STT_PROVIDER": "null",
        "KNOWLEDGE_DB_PATH": str(tmp_path / "k.db"),
        "RECOGNITION_DB_PATH": str(tmp_path / "r.db"),
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
    app = brain_main.create_app()
    async with app.router.lifespan_context(app):
        assert wander.mode_changed in mode_policy._mode_listeners
        assert wander.quiet_changed in mode_policy._quiet_listeners
