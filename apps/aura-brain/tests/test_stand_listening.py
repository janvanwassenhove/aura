"""U398: at a stand he hears a crowd — and he answered it.

Reported, in Stand with *emotions* (translated): *"I notice in the chat that he
still starts a conversation"* — and *"not spoken aloud, only in the chat"*.

He was not starting anything. The log showed the room becoming his questions,
one every fifteen seconds: "Ik weet niet of dat piept.", "I needed to see more
in the", "Det er en god speking.", "De nieuwste en spannendste". Nobody had
said his name. What happened instead, each time:

1. The transcriber returned "AURA" for noise, for a clipping microphone (peak
   1.0) and for his own emotion sounds — the voice loop's last transcript was
   literally "AURA".
2. His name alone is the wake word: a nod, and a window that accepts anything.
3. Whatever the room said next was the question. He answered with an emotion,
   and the answer's text went to the chat.
4. That emotion's sound was heard as "AURA" — the self-hearing guard measured
   the *text* he did not speak, not the sound he made — and round it went.

Agreed fixes: at a stand his name and the question come in one breath, and
nothing he says opens a window for the next voice in a crowd; his emotion's
sound is his own voice to the echo guards; and in *emotions* a heard question
gets an emotion picked from what was said, without composing an answer
nobody will hear.
"""

from __future__ import annotations

import asyncio
import itertools

import pytest
from aura_brain import voice_loop as vl


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Room:
    """A robot whose microphone hears the scripted lines, loudly."""

    def __init__(self, clock: _Clock, windows: int) -> None:
        self.clock = clock
        self.left = windows
        self.done = asyncio.Event()
        self.played: list[str] = []

    async def listen(self, seconds: float):
        if self.left <= 0:
            self.done.set()
            await asyncio.Event().wait()
        self.left -= 1
        self.clock.t += seconds
        return b"wav", 1.0

    async def execute_motion(self, *_a, **_k):
        return None

    async def play_emotion(self, name: str):
        self.played.append(name)
        return {"played": name}

    async def stop_audio(self):
        return {}


class _Vad:
    interruptibility = "vad"


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, e):
        self.events.append(e)


class _Pipeline:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def orchestrate(self, text, session_id):
        self.asked.append(text)
        return "ok"

    def __getattr__(self, _name):
        return lambda *a, **k: None


@pytest.fixture
def stand(monkeypatch, tmp_path):
    """A scratch mode policy, a clock moved by hand, and a scripted room."""
    from orchestrator import mode_policy

    clock = _Clock()
    monkeypatch.setattr(vl.time, "monotonic", clock)
    monkeypatch.setenv("VOICE_MODE", "wake_word")
    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    monkeypatch.setenv("WAKE_ACK", "off")
    monkeypatch.setenv("LISTENING_CUE", "false")
    monkeypatch.delenv("FOLLOWUP_CHAIN_MAX", raising=False)
    monkeypatch.delenv("FOLLOWUP_S", raising=False)
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    mode_policy.reset_cache_for_tests()
    from aura_brain import presentation_api
    monkeypatch.setattr(presentation_api, "is_active", lambda: False)

    async def nosleep(*_a, **_k):
        clock.t += 0.5
    monkeypatch.setattr(vl.asyncio, "sleep", nosleep)
    yield clock, monkeypatch
    mode_policy.set_active("work")
    mode_policy.reset_cache_for_tests()


def _mode(name: str, *, sound: str | None = None) -> None:
    from orchestrator import mode_policy

    if sound is not None:
        mode_policy.set_behaviour(name, {"wander": "on", "wander_sound": sound})
    mode_policy.set_active(name)


async def _run(stand, lines, *, windows: int = 30, spoken_first: str | None = None,
               character=None, real_handle: bool = False):
    """Run the real loop over a scripted room; return (answered, loop, robot, bus, pipeline)."""
    clock, monkeypatch = stand
    script = itertools.cycle(lines)

    async def transcribe(*_a, **_k):
        return next(script)

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", transcribe)
    robot, bus, pipeline = _Room(clock, windows), _Bus(), _Pipeline()
    manager = None
    if character is not None:
        from aura_brain.conversation_manager import ConversationManager
        manager = ConversationManager(stop_robot_audio=None)
        manager.character = character
    loop = vl.VoiceLoop(robot=robot, pipeline=pipeline, bus=bus, default_wake_word="aura",
                        manager=manager, followup_s=9.0)
    loop._wake_detector = None
    answered: list[str] = []

    if not real_handle:
        async def handle(command: str) -> None:
            answered.append(command)
            loop.note_spoken("Dat is een goede vraag, ik vertel je er graag meer over.")
        loop._handle = handle

    async def pipeline_engine(*_a, **_k):
        return False
    loop._speech_turn = pipeline_engine
    if spoken_first:
        loop.note_spoken(spoken_first)

    task = asyncio.ensure_future(loop._run())
    await asyncio.wait_for(robot.done.wait(), timeout=10)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return answered, loop, robot, bus, pipeline


ROOM = ["AURA", "I needed to see more in the", "AURA", "Det er en god speking.",
        "Ik weet niet of dat piept.", "AURA", "De nieuwste en spannendste"]


# --- at a stand: his name and the question in one breath ----------------------

async def test_elsewhere_his_name_alone_still_opens_the_window(stand) -> None:
    """The control — a person at home may say "AURA", wait for the nod, then
    ask. That stays."""
    _mode("work")
    answered, *_ = await _run(stand, ROOM)
    assert answered, "his name alone no longer works at home"


async def test_at_a_stand_his_name_alone_opens_nothing(stand) -> None:
    """The reported loop: "AURA" out of noise, and the room's next sentence as
    the question."""
    _mode("stand")
    answered, loop, *_ = await _run(stand, ROOM)
    assert answered == [], f"answered the crowd: {answered}"


async def test_at_a_stand_his_name_with_a_question_is_answered(stand) -> None:
    _mode("stand")
    answered, *_ = await _run(stand, ["AURA, wat ben jij eigenlijk?", "Det er en god speking."],
                              windows=2)
    assert answered == ["wat ben jij eigenlijk?"]


async def test_at_a_stand_an_answer_opens_no_window_for_the_next_voice(stand) -> None:
    """In a crowd the next sentence after his answer is as likely someone
    else's."""
    _mode("stand")
    answered, *_ = await _run(stand, ["Ik weet niet of dat piept.", "Yeah, OK."],
                              spoken_first="Hallo! Leuk dat je er bent.")
    assert answered == []


async def test_at_a_stand_only_his_name_interrupts_him(stand) -> None:
    """A `vad` character takes any plausible voice as an interruption — and an
    interruption opens a window. At a stand, a crowd is not an interruption."""
    _mode("stand")
    answered, *_ = await _run(stand, ["Kann ich ihn jetzt rauskaufen?", "Evet, bu sizinle"],
                              spoken_first="Hallo! " * 40, character=_Vad())
    assert answered == []


# --- his emotion is his own voice -----------------------------------------------

def test_his_own_emotion_is_not_his_name(stand) -> None:
    clock, _ = stand
    loop = vl.VoiceLoop(robot=_Room(clock, 0), pipeline=_Pipeline(), bus=_Bus(),
                        default_wake_word="aura")
    assert loop._is_own_name_echo("AURA") is False
    loop.note_sound(3.0)
    assert loop._is_own_name_echo("AURA") is True, "his giggle, heard as his name"
    clock.t += 3.0 + 2.0
    assert loop._is_own_name_echo("AURA") is False, "and only while it can still be heard"


def test_a_sound_opens_no_conversation(stand) -> None:
    """An emotion is not a question put to the room: it guards, it does not
    invite."""
    clock, _ = stand
    loop = vl.VoiceLoop(robot=_Room(clock, 0), pipeline=_Pipeline(), bus=_Bus(),
                        default_wake_word="aura", followup_s=9.0)
    loop.note_sound(3.0)
    assert loop._followup_until == 0.0


# --- in emotions mode a heard question gets an emotion, not an answer --------------

async def test_in_emotions_mode_he_does_not_compose_an_answer(stand) -> None:
    from shared_schemas.events.audio import TranscriptUpdated
    from shared_schemas.events.conversation import ResponseDrafted

    _mode("work", sound="emotions")
    _answered, loop, robot, bus, pipeline = await _run(
        stand, ["AURA, hallo!"], windows=1, real_handle=True)
    assert pipeline.asked == [], "no answer is composed for nobody to hear"
    assert robot.played == ["welcoming1"]
    heard = [e for e in bus.events if isinstance(e, TranscriptUpdated)]
    said = [e for e in bus.events if isinstance(e, ResponseDrafted)]
    assert [e.transcript for e in heard] == ["hallo!"], "what was said still shows"
    assert len(said) == 1 and said[0].already_voiced is True
    assert "welcoming1" in said[0].response_text, "the chat says what he did"
    assert loop._is_own_name_echo("AURA"), "and his own welcome is not his name"


async def test_in_talk_mode_he_still_answers(stand) -> None:
    _mode("work", sound="talk")
    _answered, _loop, robot, _bus, pipeline = await _run(
        stand, ["AURA, hallo!"], windows=1, real_handle=True)
    assert pipeline.asked == ["hallo!"]
    assert robot.played == []


@pytest.mark.parametrize("heard, emotion", [
    ("Hallo!", "welcoming1"),
    ("Hi there", "welcoming1"),
    ("Haha, wat grappig", "laughing2"),
    ("Dank je wel", "grateful1"),
    ("Thank you!", "grateful1"),
    ("Wat kan jij eigenlijk?", "thoughtful2"),
    ("what can you do", "thoughtful2"),
    ("Wow, amazing!!", "enthusiastic2"),
    ("Ik weet het niet.", "understanding2"),
    ("This is nice", "understanding2"),
])
def test_what_he_heard_picks_the_emotion(heard, emotion) -> None:
    from aura_brain import wander

    assert wander.emotion_for_heard(heard) == emotion
