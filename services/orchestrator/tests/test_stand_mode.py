"""U397: Stand — a mode for a stand at a fair, where everyone is a stranger.

Asked as (translated): *"if I'm at a fair, say, and I want to put the robot
in wander mode there, how do I best do that? I'd think in work mode and
activate it there? Doing it via Settings seems so strange"* — and then, of the
new mode, *"I assume a lot of capabilities are switched off / greyed out
there"*.

Work mode at a fair would hand every passer-by an assistant with the owner's
calendar, mail, files and screen, that remembers whoever talks to it and knows
the household by name. Stand is the opposite: he talks, looks things up and
wanders; nothing of the owner's is within reach, nothing about the visitors
is kept, and none of it is in the prompt to be overheard.
"""

from __future__ import annotations

import pytest
from orchestrator import mode_policy
from orchestrator import pipeline as pipeline_mod
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus
from shared_policies import MODE_TOOL_MAP


@pytest.fixture(autouse=True)
def _policy(monkeypatch, tmp_path):
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.reset_cache_for_tests()
    mode_policy.set_active("work")
    yield
    mode_policy.set_active("work")
    mode_policy.reset_cache_for_tests()


# --- the mode ------------------------------------------------------------------

def test_stand_sits_between_work_and_present_in_the_header() -> None:
    assert mode_policy.UI_MODES == ("home", "work", "stand", "presentation")
    assert "stand" in mode_policy.describe("work")["modes"]


def test_the_header_can_switch_to_it() -> None:
    IntentRouter(mode="work").set_mode("stand")
    assert PersonaManager().switch("stand").name == "stand"
    assert mode_policy.set_active("stand") == "stand"
    assert mode_policy.in_public() is True


@pytest.mark.parametrize("mode", ["home", "work", "presentation"])
def test_only_the_stand_is_in_public(mode) -> None:
    mode_policy.set_active(mode)
    assert mode_policy.in_public() is False


# --- greyed out: nothing of the owner's ---------------------------------------

@pytest.mark.parametrize("group", [
    "calendar", "mail", "reminders", "music", "dev tools", "screen control", "slides",
])
def test_nothing_of_yours_is_within_reach_at_a_stand(group) -> None:
    assert mode_policy.default_state("stand", group) == mode_policy.BLOCKED


def test_he_can_still_talk_and_look_things_up() -> None:
    assert mode_policy.default_state("stand", "conversation") == mode_policy.ALLOWS
    assert mode_policy.default_state("stand", "web") == mode_policy.ALLOWS


def test_tools_you_added_are_blocked_at_a_stand(monkeypatch) -> None:
    monkeypatch.setattr(mode_policy, "_mcp_tools", lambda: frozenset({"turn_on_lights"}))
    assert mode_policy.default_state("stand", mode_policy.MCP_GROUP) == mode_policy.BLOCKED
    assert "turn_on_lights" not in mode_policy.allowed_tools("stand")
    assert "turn_on_lights" in mode_policy.allowed_tools("work")


def test_he_cannot_look_up_the_people_you_know_at_a_stand() -> None:
    """U294 put looking someone up in every mode: the judgment layer decides
    per person what may be said — to the household. At a stand the person
    asking is a stranger."""
    assert "look_up_person" in MODE_TOOL_MAP["work"]
    assert "look_up_person" not in MODE_TOOL_MAP["stand"]


# --- how he behaves there ------------------------------------------------------

def test_at_a_stand_he_remembers_nobody_and_never_starts() -> None:
    mode_policy.set_active("stand")
    assert mode_policy.may_write_memory() is False
    assert mode_policy.may_speak_unprompted("reminder") is False, \
        "a reminder read out at a stand is your agenda, read to strangers"


def test_at_a_stand_he_wanders_and_talks_by_default() -> None:
    b = mode_policy.behaviour("stand")
    assert (b["wander"], b["wander_sound"]) == ("on", "talk")


@pytest.mark.parametrize("mode", ["home", "work", "presentation"])
def test_elsewhere_he_does_not_wander_unless_you_say_so(mode) -> None:
    b = mode_policy.behaviour(mode)
    assert (b["wander"], b["wander_sound"]) == ("off", "silent")


def test_wandering_is_set_per_mode() -> None:
    mode_policy.set_behaviour("home", {"wander": "on", "wander_sound": "emotions"})
    assert mode_policy.behaviour("home")["wander"] == "on"
    assert mode_policy.behaviour("home")["wander_sound"] == "emotions"
    assert mode_policy.behaviour("work")["wander"] == "off"


@pytest.mark.parametrize("update", [{"wander": "maybe"}, {"wander_sound": "shout"}])
def test_a_wander_setting_that_is_not_one_is_refused(update) -> None:
    with pytest.raises(ValueError):
        mode_policy.set_behaviour("work", update)


def test_changing_mode_or_its_behaviour_is_heard() -> None:
    """The robot wanders on its own clock; it has to be told."""
    heard: list[str] = []
    mode_policy.on_mode_change(heard.append)
    try:
        mode_policy.set_active("stand")
        mode_policy.set_behaviour("stand", {"wander_sound": "emotions"})
        mode_policy.set_active("work")
    finally:
        mode_policy.on_mode_change(heard.append, remove=True)
    assert heard == ["stand", "stand", "work"]


# --- nothing personal in the prompt ------------------------------------------------

class _Snapshot:
    async def get_calendar_summary(self) -> str:
        return "Dentist at 14:00"

    async def get_unread_mail_count(self) -> int:
        return 3

    async def get_pending_tasks_summary(self) -> str:
        return "Finish the Acme memo"


class _PersonCtx:
    def to_system_note(self) -> str:
        return "You are talking to Jan, the owner. He lives with Elke."


class _Judgment:
    def __init__(self) -> None:
        from shared_schemas.knowledge import InMemoryKnowledgeStore
        self._store = InMemoryKnowledgeStore()

    async def build_context(self, person_id):
        return _PersonCtx()


async def _pipeline(monkeypatch, mode: str):
    seen: list[list[dict]] = []

    async def fake_llm(messages, tools=None, **kw):
        seen.append(messages)
        return {"content": "ok", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)
    bus = AsyncEventBus()
    await bus.start()
    persona = PersonaManager()
    persona.switch(mode)
    pipe = OrchestratorPipeline(
        bus, IntentRouter(mode=mode), ApprovalManager(bus, session_id="t"),
        ContextBuilder(_Snapshot()), persona,
    )
    from shared_schemas.knowledge import Person

    judgment = _Judgment()
    await judgment._store.upsert_person(Person(person_id="elke", display_name="Elke", role="family"))
    pipe.set_judgment_layer(judgment)
    pipe.set_active_person("jan")
    return pipe, seen, bus


def _text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


async def test_at_work_his_context_is_personal(monkeypatch) -> None:
    """The control: the same pipeline outside the stand does carry it."""
    pipe, seen, bus = await _pipeline(monkeypatch, "work")
    await pipe.orchestrate("what's up?", "s")
    await bus.stop()
    prompt = _text(seen[-1])
    assert "Dentist" in prompt and "Elke" in prompt


async def test_at_a_stand_nothing_personal_reaches_the_prompt(monkeypatch) -> None:
    mode_policy.set_active("stand")
    pipe, seen, bus = await _pipeline(monkeypatch, "stand")
    await pipe.orchestrate("what's on his agenda today?", "s")
    await bus.stop()
    prompt = _text(seen[-1])
    for private in ("Dentist", "Unread mail", "Acme", "Elke", "Jan"):
        assert private not in prompt, f"{private!r} reached a prompt at a stand"
    assert "stranger" in prompt.lower(), "he must be told where he is"


async def test_the_speech_paths_get_nothing_personal_at_a_stand(monkeypatch) -> None:
    """Live and realtime ask the pipeline for who is in the room (U245, U293);
    at a stand, the answer is a stand."""
    mode_policy.set_active("stand")
    pipe, _seen, bus = await _pipeline(monkeypatch, "stand")
    await bus.stop()
    assert await pipe.household_note() == ""
    note = await pipe.person_note()
    assert "Jan" not in note and "Elke" not in note
    assert "stranger" in note.lower()


async def test_what_was_said_at_work_does_not_follow_him_to_the_stand(monkeypatch) -> None:
    pipe, seen, bus = await _pipeline(monkeypatch, "work")
    await pipe.orchestrate("the Acme merger closes on Friday", "default")

    mode_policy.set_active("stand")
    await pipe.orchestrate("hello, what do you do?", "default")
    assert "Acme" not in _text(seen[-1]), "a visitor could ask what was just said"

    mode_policy.set_active("work")
    await pipe.orchestrate("so, Friday?", "default")
    await bus.stop()
    back = _text(seen[-1])
    assert "Acme" in back, "the work conversation carries on where it was"
    assert "what do you do" not in back, "and the stand's stays at the stand"
