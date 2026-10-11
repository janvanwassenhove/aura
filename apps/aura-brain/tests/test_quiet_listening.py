"""U413: in Quiet he answered the room, one question after another.

Reported with a screenshot, Quiet on, the header reading *"Awake but hushed —
he answers when asked and never speaks first"*: *"aura in quiet mode, but still
talking / asking"*. The chat showed him answering "Ne rodime.", "This book?"
and "Ik heb al veel" — each answer ending in a question of his own.

Nobody had asked him anything. `mode-policy.json` said `"quiet": true`, and
`turn_traces.jsonl` held eight turns in forty minutes on transcripts like
"Jestę parkirny.", "Tu as divisé." and "Now, so this tovalted meja." — a room,
heard by a transcriber that always returns words. Three ways in, all three
used that afternoon:

1. **The follow-up window.** After he speaks he listens nine seconds without
   the wake word. "Ne rodíme." arrived eighteen seconds after the turn before
   it: his own answer had opened the door for it.
2. **His name alone.** Two of the last three traces carry a `second_capture`:
   the transcriber returned his name for noise, and whatever the room said
   next — "This book?", "Ik heb al veel" — became the question.
3. **The local wake detector alone.** When it fires, the whole transcript is
   taken as addressed to him, whether or not his name is in it.

U332 had already written the rule down — *"while Quiet is on, every turn goes
back through the wake word"* — and applied it to the open sessions only. U398
closed (1) and (2) for a Stand. Quiet is the mode whose whole promise is that
he speaks only when asked, and it had neither.

In Quiet: his name and the question in one breath, his name actually in what
was transcribed, and no answer of his opens a window.
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

    async def listen(self, seconds: float):
        if self.left <= 0:
            self.done.set()
            await asyncio.Event().wait()
        self.left -= 1
        self.clock.t += seconds
        return b"wav", 1.0

    async def execute_motion(self, *_a, **_k):
        return None

    async def stop_audio(self):
        return {}


class _Vad:
    interruptibility = "vad"


class _Bus:
    async def publish(self, e):
        return None


class _Pipeline:
    async def orchestrate(self, text, session_id):
        return "ok"

    def __getattr__(self, _name):
        return lambda *a, **k: None


class _AlwaysHearsHisName:
    """The local detector on a television: it fires."""

    def detect(self, _wav) -> bool:
        return True


@pytest.fixture
def room(monkeypatch, tmp_path):
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
    mode_policy.set_active("home")
    from aura_brain import presentation_api
    monkeypatch.setattr(presentation_api, "is_active", lambda: False)

    async def nosleep(*_a, **_k):
        clock.t += 0.5
    monkeypatch.setattr(vl.asyncio, "sleep", nosleep)
    yield clock, monkeypatch
    mode_policy.set_quiet(False)
    mode_policy.set_active("work")
    mode_policy.reset_cache_for_tests()


def _quiet(on: bool) -> None:
    from orchestrator import mode_policy

    mode_policy.set_quiet(on)


async def _run(room, lines, *, windows: int = 30, spoken_first: str | None = None,
               character=None, detector=None) -> list[str]:
    """Run the real loop over a scripted room; return what he answered."""
    clock, monkeypatch = room
    script = itertools.cycle(lines)

    async def transcribe(*_a, **_k):
        return next(script)

    from aura_brain import voice
    monkeypatch.setattr(voice, "transcribe", transcribe)
    robot = _Room(clock, windows)
    manager = None
    if character is not None:
        from aura_brain.conversation_manager import ConversationManager
        manager = ConversationManager(stop_robot_audio=None)
        manager.character = character
    loop = vl.VoiceLoop(robot=robot, pipeline=_Pipeline(), bus=_Bus(),
                        default_wake_word="richie", manager=manager, followup_s=9.0)
    loop._wake_detector = detector
    if detector is not None:
        # The clock here is moved by hand, and it is the event loop's clock too:
        # a real thread hop would let the test's own timeout fire on fake time.
        async def inline(fn, *a, **k):
            return fn(*a, **k)
        monkeypatch.setattr(vl.asyncio, "to_thread", inline)
    answered: list[str] = []

    async def handle(command: str) -> None:
        answered.append(command)
        # What he actually said back that afternoon: an answer that asks.
        loop.note_spoken("Heb je het over een specifiek boek? Laat me weten welke het is!")
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
    return answered


# The room as it was transcribed that afternoon, with his name out of noise.
ROOM = ["Richie", "This book?", "Richie", "Ik heb al veel", "Ne rodíme.",
        "Richie", "Now, so this tovalted meja."]


# ── his name alone ─────────────────────────────────────────────────────────

async def test_without_quiet_his_name_alone_still_opens_the_window(room) -> None:
    """The control: say his name, wait for the nod, then ask. That stays."""
    _quiet(False)
    assert await _run(room, ROOM), "his name alone no longer works"


async def test_in_quiet_his_name_alone_opens_nothing(room) -> None:
    """The reported loop: "Richie" out of noise, the room's next line as the
    question — "This book?"."""
    _quiet(True)
    answered = await _run(room, ROOM)
    assert answered == [], f"answered the room: {answered}"


async def test_in_quiet_his_name_with_a_question_is_answered(room) -> None:
    """Quiet never meant deaf: asked properly, he answers."""
    _quiet(True)
    answered = await _run(room, ["Richie, hoe laat is het?", "Ne rodíme."], windows=2)
    assert answered == ["hoe laat is het?"]


# ── the follow-up window ───────────────────────────────────────────────────

async def test_without_quiet_an_answer_opens_the_window(room) -> None:
    """The control: outside Quiet you may simply answer him back."""
    _quiet(False)
    answered = await _run(room, ["Ne rodíme."], windows=3,
                          spoken_first="Vertel me meer als je wilt!")
    assert answered, "the follow-up window is gone everywhere"


async def test_in_quiet_his_own_answer_opens_no_window(room) -> None:
    """"Ne rodíme." came in eighteen seconds after the turn before it — through
    the window his own answer had opened."""
    _quiet(True)
    answered = await _run(room, ["Ne rodíme.", "This book?"],
                          spoken_first="Vertel me meer als je wilt!")
    assert answered == []


async def test_in_quiet_one_real_question_does_not_start_a_conversation(room) -> None:
    """Asked once, he answers once — the room does not get the next turn."""
    _quiet(True)
    answered = await _run(room, ["Richie, hoe laat is het?", "Ik heb al veel",
                                 "This book?", "Ne rodíme."], windows=8)
    assert answered and {a.rstrip("?") for a in answered} == {"hoe laat is het"}, (
        f"only what he was asked by name, never the room: {answered}")


# ── the local detector ─────────────────────────────────────────────────────

async def test_without_quiet_the_detector_vouches_for_the_sentence(room) -> None:
    """The control (U128): the detector heard his name even if the transcript
    dropped it."""
    _quiet(False)
    answered = await _run(room, ["Tu as divisé."], windows=1,
                          detector=_AlwaysHearsHisName())
    assert answered == ["Tu as divisé."]


async def test_in_quiet_the_detector_alone_is_not_being_asked(room) -> None:
    """A detector that fires on a television must not make the television's
    sentence his question."""
    _quiet(True)
    answered = await _run(room, ["Tu as divisé.", "Jestę parkirny.",
                                 "Wat wiek is achterbiede moar."],
                          detector=_AlwaysHearsHisName())
    assert answered == []


async def test_in_quiet_the_detector_and_his_name_together_are(room) -> None:
    _quiet(True)
    answered = await _run(room, ["Richie, zet de muziek zachter"], windows=1,
                          detector=_AlwaysHearsHisName())
    assert answered == ["zet de muziek zachter"]


# ── interrupting him ───────────────────────────────────────────────────────

async def test_in_quiet_only_his_name_interrupts_him(room) -> None:
    """A `vad` character takes any plausible voice as an interruption, and an
    interruption opens a window. In Quiet the room is not an interruption."""
    _quiet(True)
    answered = await _run(room, ["Now, so this tovalted meja.", "Tu as divisé."],
                          spoken_first="Hallo! " * 40, character=_Vad())
    assert answered == []
