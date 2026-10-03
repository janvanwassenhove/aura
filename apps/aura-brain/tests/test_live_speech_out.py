"""U385: the live engine speaks where the owner chose, and Stop silences both.

What the owner heard in U384's report was not the broken reply path — it was a
live session, which voices its replies as ~1.4 s segments over
`POST /robot/speak/segment`. U364 left that path unrouted on purpose and wrote
the exception down; the owner never agreed to it, and a setting called *Where
he speaks* cannot mean "except sometimes". Four call sites — the live session,
the realtime session, and two in the voice loop — sent audio straight to the
robot.

And every way of stopping him — barge-in, the realtime cut, the panic stop —
called the robot's audio-stop and nothing else. In laptop mode, which U364
shipped, that left the laptop talking after you pressed Stop.
"""

from __future__ import annotations

import base64

import pytest
from aura_brain import speech_out

PCM = b"\x03\x04" * 1200
AUDIO = base64.b64encode(PCM).decode()


class _Robot:
    def __init__(self) -> None:
        self.segments: list[str] = []
        self.stopped = 0

    async def speak_segment(self, audio_b64):
        self.segments.append(audio_b64)
        return True

    async def stop_audio(self):
        self.stopped += 1
        return {"stopped": True}


class _OfflineRobot(_Robot):
    async def stop_audio(self):
        raise OSError("robot offline")


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event):
        self.published.append(event)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("AUDIO_OUTPUT", raising=False)
    speech_out.forget_all()
    yield
    speech_out.forget_all()


async def test_a_live_segment_goes_to_the_robot_by_default() -> None:
    robot, bus = _Robot(), _Bus()
    assert await speech_out.deliver_segment(robot, bus, AUDIO) is True
    assert robot.segments == [AUDIO]
    assert bus.published == []


async def test_with_the_laptop_chosen_a_live_segment_never_reaches_the_robot(monkeypatch) -> None:
    """The reported symptom, at the call the live engine actually makes."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    robot, bus = _Robot(), _Bus()
    assert await speech_out.deliver_segment(robot, bus, AUDIO) is True
    assert robot.segments == [], "the live engine still spoke through the robot"
    [event] = bus.published
    assert event.event_type == "SpeechAudioReady"
    assert speech_out.take(event.utterance_id).endswith(PCM)


async def test_segments_keep_their_order(monkeypatch) -> None:
    """A live reply is a burst. The console plays them in the order offered,
    so the order offered has to be the order spoken."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    bus = _Bus()
    pieces = [base64.b64encode(bytes([i]) * 64).decode() for i in range(5)]
    for p in pieces:
        await speech_out.deliver_segment(None, bus, p)
    served = [speech_out.take(e.utterance_id) for e in bus.published]
    assert [s[-64:] for s in served] == [bytes([i]) * 64 for i in range(5)]


async def test_stop_tells_the_laptop_and_the_robot() -> None:
    robot, bus = _Robot(), _Bus()
    await speech_out.stop(robot, bus)
    assert robot.stopped == 1
    assert [e.event_type for e in bus.published] == ["SpeechAudioStopped"]


async def test_stop_drops_lines_nobody_has_fetched_yet(monkeypatch) -> None:
    """After Stop, a console that was about to fetch the next segment must find
    nothing — otherwise the sentence carries on from where it was cut."""
    monkeypatch.setenv("AUDIO_OUTPUT", "laptop")
    bus = _Bus()
    await speech_out.deliver_segment(None, bus, AUDIO)
    await speech_out.stop(None, bus)
    assert speech_out.pending() == 0


async def test_an_offline_robot_does_not_stop_the_laptop_being_silenced() -> None:
    """The laptop is told first, because the robot call is the one that can
    fail — a panic stop must never be undone by the robot being away."""
    bus = _Bus()
    with pytest.raises(OSError):
        await speech_out.stop(_OfflineRobot(), bus)
    assert [e.event_type for e in bus.published] == ["SpeechAudioStopped"]


def test_nothing_in_the_brain_talks_to_the_robots_speaker_directly() -> None:
    """The rule that keeps "Where he speaks" true: speech_out decides, and is
    the only caller of the robot's speak, speak_segment and stop_audio. Four
    call sites had gone around it; this is what would have caught them.

    Read as code (AST), not text, so a docstring that *mentions* a call does
    not count as one.
    """
    import ast
    import pathlib

    import aura_brain

    root = pathlib.Path(aura_brain.__file__).parent
    allowed = {"speech_out.py", "robot_client.py"}   # the decider, the driver
    found = []
    for path in sorted(root.glob("*.py")):
        if path.name in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"speak", "speak_segment", "stop_audio"}):
                found.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
    assert not found, f"bypasses the speaker choice: {found}"


async def test_the_barge_in_stop_reaches_the_laptop() -> None:
    """ConversationManager's interrupt() is wired to `speech_out.stop` in the
    brain, not to the robot alone."""
    from aura_brain.conversation_manager import ConversationManager

    robot, bus = _Robot(), _Bus()
    manager = ConversationManager(stop_robot_audio=lambda: speech_out.stop(robot, bus))
    await manager.interrupt("half a sentence")
    assert robot.stopped == 1
    assert any(e.event_type == "SpeechAudioStopped" for e in bus.published)
