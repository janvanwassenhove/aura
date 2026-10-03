"""U392: he answered the room.

Agreed after U391, in the owner's words (translated): *"do 1-2-3"* — check
whether it is his own voice, stop opening paid live sessions without the wake
word, and keep foreign-language fragments out.

What the log showed (3 Oct, 19:36-19:51): with the wake word "AURA" and the
live engine selected, he acted on 25 fragments in fifteen minutes — "Sie machen
das über nationalen", "Evet, bu sizinle", "Kann ich ihn jetzt rauskaufen?" — and
on 130 that day, six of which contained his name. It was **not** his own voice:
those were caught and logged as self-hearing. It was speech in the room, and
the window that accepts speech without the wake word never closed.

That window is capped: after FOLLOWUP_CHAIN_MAX (2) answers without the wake
word, the wake word is required again. But a character with
`interruptibility: vad` may be interrupted by any plausible voice, and that
barge-in path reopened the window on its own — `followup_until = now + 9 s`,
whatever the count — and handed the interrupting fragment straight to the
pipeline as a command. With a television on, every answer was interrupted, and
every interruption was the next question.

These tests run the real listening loop on a clock they move by hand, with a
robot that hears the room and a transcriber that returns the owner's own
fragments from that evening.
"""

from __future__ import annotations

import asyncio
import itertools

import pytest
from aura_brain import voice_loop as vl

NOISE = [
    "Sie machen das über nationalen", "Na taliahrina", "Es nu an spilen.",
    "Ysa visma,", "Sammus narrendjan, nar", "Kann ich ihn jetzt rauskaufen?",
    "Die Ananas, da ist er, gell?", "Chic de la Francaise.", "Evet, bu sizinle",
    "Er hat das Bienenauge.", "Sind die Antibakteries Feuerpolynom?",
]
REPLY = "Dat begrijp ik niet helemaal, kun je dat nog eens zeggen? Ik luister."


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class _Room:
    """A robot whose microphone always hears someone talking."""

    def __init__(self, clock: _Clock, windows: int) -> None:
        self.clock = clock
        self.left = windows
        self.done = asyncio.Event()

    async def listen(self, seconds: float):
        if self.left <= 0:
            self.done.set()
            await asyncio.Event().wait()           # park until cancelled
        self.left -= 1
        self.clock.t += seconds
        return b"wav", 1.0                          # loud: well above any gate

    async def stop_audio(self):
        return {}

    async def speak_segment(self, *_a):
        return True


class _Character:
    interruptibility = "vad"


def _manager():
    """The real conversation manager, with a character that takes interruptions."""
    from aura_brain.conversation_manager import ConversationManager

    m = ConversationManager(stop_robot_audio=None)
    m.character = _Character()
    return m


class _Pipeline:
    """Answers nothing itself — `_handle` is replaced; this only absorbs the
    bookkeeping calls the loop makes on the way."""

    def __getattr__(self, _name):
        return lambda *a, **k: None


class _Bus:
    async def publish(self, _e):
        return None


@pytest.fixture
def room(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(vl.time, "monotonic", clock)
    monkeypatch.setenv("VOICE_MODE", "wake_word")
    monkeypatch.setenv("WAKE_WORD", "aura")
    monkeypatch.setenv("VOICE_ENGINE", "pipeline")
    monkeypatch.delenv("FOLLOWUP_CHAIN_MAX", raising=False)
    monkeypatch.delenv("FOLLOWUP_S", raising=False)

    lines = itertools.cycle(NOISE)

    async def transcribe(*_a, **_k):
        return next(lines)

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", transcribe)

    async def nosleep(*_a, **_k):
        clock.t += 0.5
    monkeypatch.setattr(vl.asyncio, "sleep", nosleep)
    return clock


async def _run(clock: _Clock, *, manager, windows: int = 200) -> list[str]:
    """Run the loop for `windows` listening windows; return what it answered."""
    robot = _Room(clock, windows)
    loop = vl.VoiceLoop(robot=robot, pipeline=_Pipeline(), bus=_Bus(), default_wake_word="aura",
                        manager=manager, followup_s=9.0)
    answered: list[str] = []

    async def handle(command: str) -> None:
        answered.append(command)
        loop.note_spoken(REPLY)                     # he answers; the window opens

    async def engine_says_pipeline(*_a, **_k):
        return False

    loop._handle = handle
    loop._speech_turn = engine_says_pipeline

    # A conversation that really happened: he greeted someone, so the
    # wake-word-free window is open — exactly as after any real reply.
    loop.note_spoken("Goedenavond! Waarmee kan ik helpen?")

    task = asyncio.ensure_future(loop._run())
    await asyncio.wait_for(robot.done.wait(), timeout=10)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return answered


async def test_room_speech_gets_at_most_the_capped_answers(room) -> None:
    """The reported failure. FOLLOWUP_CHAIN_MAX is 2: after a real exchange, at
    most two answers without the wake word — however chatty the room is."""
    answered = await _run(room, manager=_manager())
    assert len(answered) <= 2, (
        f"answered the room {len(answered)} times without being addressed: "
        f"{answered[:6]}")


async def test_a_character_that_does_not_take_interruptions_was_never_affected(room) -> None:
    """The control: without the vad barge-in path, the cap already held."""
    answered = await _run(room, manager=None)
    assert len(answered) <= 2


async def test_a_fragment_nobody_addressed_does_not_open_a_paid_session(monkeypatch) -> None:
    """A Live session bills for every second it is open and keeps listening
    without the wake word until it goes idle. One opened that evening on
    "Hva sa du?" from across the room. Unaddressed, the pipeline answers."""
    loop = vl.VoiceLoop(robot=_Room(_Clock(), 0), pipeline=_Pipeline(), bus=_Bus(),
                        default_wake_word="aura")
    opened: list[str] = []

    async def live(_wav, command):
        opened.append(command)
        return True

    loop._live_session_turn = live
    loop._engine = lambda: "live"

    assert await loop._speech_turn(b"w", "Hva sa du?", addressed=False) is False
    assert opened == []
    assert await loop._speech_turn(b"w", "wat is het weer", addressed=True) is True
    assert opened == ["wat is het weer"]

