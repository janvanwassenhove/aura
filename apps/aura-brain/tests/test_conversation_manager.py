"""U84: conversation state machine — transitions, barge-in, cancellation."""

from __future__ import annotations

import asyncio

from aura_brain.characters import CharacterStore
from aura_brain.conversation_manager import ConversationManager, ConversationState

# ── state transitions ────────────────────────────────────────────────

async def test_turn_lifecycle_transitions() -> None:
    m = ConversationManager()
    assert m.state is ConversationState.IDLE

    turn = m.begin_turn("voice")
    assert turn == 1
    assert m.state is ConversationState.TRANSCRIBING
    m.thinking()
    assert m.state is ConversationState.THINKING and m.llm_active
    m.speaking()
    assert m.state is ConversationState.SPEAKING and m.tts_playing
    m.listening()
    assert m.state is ConversationState.LISTENING
    assert not m.tts_playing and not m.llm_active

    assert m.begin_turn() == 2  # ids increment
    m.error("stt failed")
    assert m.state is ConversationState.ERROR
    m.shutdown()
    assert m.state is ConversationState.SHUTTING_DOWN
    assert m.llm_cancel.is_set() and m.tts_cancel.is_set()


async def test_begin_turn_rearms_cancellation() -> None:
    m = ConversationManager()
    m.begin_turn()
    await m.interrupt("half an answer")
    assert m.llm_cancel.is_set() and m.tts_cancel.is_set()
    m.begin_turn()
    assert not m.llm_cancel.is_set() and not m.tts_cancel.is_set()


# ── the core feature: barge-in cancels everything ─────────────────────

async def test_interrupt_cancels_speak_task_and_stops_robot_audio() -> None:
    stopped: list[bool] = []

    async def stop_audio():
        stopped.append(True)
        return {"stopped": True}

    m = ConversationManager(stop_robot_audio=stop_audio)
    m.begin_turn()
    m.thinking()

    async def long_speech():
        await asyncio.sleep(30)

    task = asyncio.ensure_future(long_speech())
    m.register_speak_task(task)
    assert m.state is ConversationState.SPEAKING

    await m.interrupt("Zeker, dat kan! Wil je dat ik")
    assert m.state is ConversationState.INTERRUPTED
    assert stopped == [True]           # robot playback cut
    assert m.llm_cancel.is_set()       # LLM turn cancelled
    await asyncio.sleep(0)             # let cancellation propagate
    assert task.cancelled() or task.done()
    assert not m.tts_playing and not m.llm_active


async def test_interruption_note_is_one_shot_and_mentions_cut_reply() -> None:
    m = ConversationManager()
    await m.interrupt("Ik was iets heel langs aan het uitleggen over")
    note = m.consume_interruption_note()
    assert "interrupted" in note
    assert "Ik was iets heel langs" in note
    assert m.consume_interruption_note() == ""  # one-shot


async def test_speak_task_completion_returns_to_listening() -> None:
    m = ConversationManager()
    m.begin_turn()

    async def quick():
        await asyncio.sleep(0.01)

    task = asyncio.ensure_future(quick())
    m.register_speak_task(task)
    await task
    await asyncio.sleep(0)
    assert m.state is ConversationState.LISTENING
    assert not m.tts_playing


# ── characters (U84 step 7) ───────────────────────────────────────────

def test_characters_seed_and_load(tmp_path) -> None:
    store = CharacterStore(str(tmp_path))
    ids = {c.id for c in store.all()}
    assert {"friendly_assistant", "dry_tech_butler", "kids_companion",
            "workshop_coach", "quiet_mode"} <= ids
    butler = store.get("dry_tech_butler")
    assert butler.voice_id == "ash"
    assert butler.robot_motion_style == "calm"
    assert butler.motion_scale() == 0.5
    assert "butler" in butler.system_note().lower()


def test_active_character_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHARACTERS_DIR", str(tmp_path))
    monkeypatch.setenv("ACTIVE_CHARACTER", "quiet_mode")
    store = CharacterStore()
    active = store.active()
    assert active is not None and active.id == "quiet_mode"
    assert active.interruptibility == "off"
    assert active.motion_scale() == 0.0
    monkeypatch.setenv("ACTIVE_CHARACTER", "nope")
    assert store.active() is None


def test_character_json_is_editable(tmp_path) -> None:
    import json

    store = CharacterStore(str(tmp_path))
    store.all()  # seed
    f = tmp_path / "friendly_assistant.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    data["voice_speed"] = 1.2
    f.write_text(json.dumps(data), encoding="utf-8")
    assert store.get("friendly_assistant").voice_speed == 1.2


# ── LLM cancellation mid-call (pipeline) ──────────────────────────────

async def test_pipeline_llm_cancelled_mid_call(monkeypatch) -> None:
    import os

    os.environ.setdefault("LLM_PROVIDER", "echo")
    from orchestrator import pipeline as pipeline_mod
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.intent_router import IntentRouter
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from shared_events.bus import AsyncEventBus

    async def slow_llm(messages, tools=None, **kw):
        await asyncio.sleep(30)  # the user will interrupt long before this
        return {"content": "too late", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", slow_llm)

    bus = AsyncEventBus()
    await bus.start()
    pipeline = OrchestratorPipeline(
        bus, IntentRouter(mode="work"), ApprovalManager(bus, session_id="t"),
        ContextBuilder(), PersonaManager(),
    )
    cancel = asyncio.Event()
    pipeline.set_cancel_event("s1", cancel)

    turn = asyncio.ensure_future(pipeline.orchestrate("vertel een lang verhaal", "s1"))
    await asyncio.sleep(0.05)   # LLM call is in flight
    cancel.set()                 # barge-in
    reply = await asyncio.wait_for(turn, timeout=2.0)
    await bus.stop()
    assert reply == ""           # cancelled turn stays silent — no stale answer


# ── U85: fuzzy wake word + character growth + edit ────────────────────

def test_fuzzy_wake_word_matches_misspellings() -> None:
    from aura_brain.voice_loop import wake_word_index

    assert wake_word_index("richie wat is het weer", "richie") == 0
    assert wake_word_index("Ritchie, zet muziek op", "richie") == 0   # edit-1
    assert wake_word_index("hey Richy kan je helpen", "richie") >= 0  # edit-1
    assert wake_word_index("oké prima dan", "richie") == -1           # absent
    assert wake_word_index("het is een rijke buurt", "richie") == -1  # not a match


def test_character_edit_and_growth(tmp_path) -> None:
    from aura_brain.characters import CharacterStore

    store = CharacterStore(str(tmp_path))
    store.all()  # seed
    updated = store.update("friendly_assistant", {
        "learned_traits": "onthoudt dat Jan van skate punk houdt",
        "verbosity": "normal",
    })
    assert updated.learned_traits.startswith("onthoudt")
    assert updated.verbosity == "normal"
    # persisted + surfaces in the system note
    reloaded = CharacterStore(str(tmp_path)).get("friendly_assistant")
    assert "skate punk" in reloaded.learned_traits
    assert "developed over time" in reloaded.system_note()
    assert store.update("nonexistent", {"x": 1}) is None
