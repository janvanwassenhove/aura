"""U22: Realtime voice transport state machine — tested over a fake wire."""

from __future__ import annotations

import base64

from conversation_runtime.realtime import RealtimeVoiceSession, SessionState


class FakeWire:
    """Scripted server events in, sent client events captured."""

    def __init__(self, server_events: list[dict] | None = None) -> None:
        self.server_events = server_events or []
        self.sent: list[dict] = []

    async def send(self, event: dict) -> None:
        self.sent.append(event)

    def __aiter__(self):
        async def _gen():
            for e in self.server_events:
                yield e
        return _gen()


class Recorder:
    def __init__(self) -> None:
        self.audio: list[bytes] = []
        self.user_transcripts: list[str] = []
        self.assistant_text: list[str] = []
        self.interrupts = 0
        self.done = 0

    async def on_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def on_user_transcript(self, text: str) -> None:
        self.user_transcripts.append(text)

    async def on_assistant_text(self, text: str) -> None:
        self.assistant_text.append(text)

    async def on_interrupt(self) -> None:
        self.interrupts += 1

    async def on_response_done(self) -> None:
        self.done += 1


def _session(wire: FakeWire, rec: Recorder) -> RealtimeVoiceSession:
    return RealtimeVoiceSession(
        wire,
        on_audio=rec.on_audio,
        on_user_transcript=rec.on_user_transcript,
        on_assistant_text=rec.on_assistant_text,
        on_interrupt=rec.on_interrupt,
        on_response_done=rec.on_response_done,
    )


async def test_configure_sends_session_update_with_vad_and_voice() -> None:
    wire = FakeWire()
    await _session(wire, Recorder()).configure()
    (msg,) = wire.sent
    assert msg["type"] == "session.update"
    assert msg["session"]["audio"]["input"]["turn_detection"] == {"type": "server_vad"}
    assert msg["session"]["audio"]["output"]["voice"] == "alloy"


async def test_send_audio_is_base64_append() -> None:
    wire = FakeWire()
    await _session(wire, Recorder()).send_audio(b"\x01\x02\x03")
    (msg,) = wire.sent
    assert msg["type"] == "input_audio_buffer.append"
    assert base64.b64decode(msg["audio"]) == b"\x01\x02\x03"


async def test_send_text_creates_item_then_response() -> None:
    wire = FakeWire()
    await _session(wire, Recorder()).send_text("hello")
    assert [m["type"] for m in wire.sent] == ["conversation.item.create", "response.create"]
    assert wire.sent[0]["item"]["content"][0]["text"] == "hello"


async def test_audio_deltas_are_decoded_and_played() -> None:
    pcm = b"PCMDATA0"
    wire = FakeWire([
        {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()},
        {"type": "response.done"},
    ])
    rec = Recorder()
    session = _session(wire, rec)
    await session.run()
    assert rec.audio == [pcm]
    assert rec.done == 1
    assert session.state is SessionState.IDLE


async def test_transcript_deltas_reach_console_not_speaker() -> None:
    wire = FakeWire([
        {"type": "response.output_audio_transcript.delta", "delta": "Hel"},
        {"type": "response.output_audio_transcript.delta", "delta": "lo."},
        {"type": "response.done"},
    ])
    rec = Recorder()
    await _session(wire, rec).run()
    assert "".join(rec.assistant_text) == "Hello."
    assert rec.audio == []  # transcript deltas must not be treated as audio


async def test_user_transcript_completed_is_surfaced() -> None:
    wire = FakeWire([
        {"type": "conversation.item.input_audio_transcription.completed",
         "transcript": "what time is it"},
    ])
    rec = Recorder()
    await _session(wire, rec).run()
    assert rec.user_transcripts == ["what time is it"]


async def test_barge_in_cancels_response_and_stops_playback() -> None:
    audio = base64.b64encode(b"x" * 8).decode()
    wire = FakeWire([
        {"type": "response.output_audio.delta", "delta": audio},   # AURA talking
        {"type": "input_audio_buffer.speech_started"},             # user interrupts
        {"type": "response.cancelled"},
    ])
    rec = Recorder()
    session = _session(wire, rec)
    await session.run()
    assert {"type": "response.cancel"} in wire.sent  # told the server to stop
    assert rec.interrupts == 1                       # told the speaker to stop
    assert session.state is SessionState.IDLE        # cancelled response settled


async def test_speech_started_while_idle_is_not_barge_in() -> None:
    wire = FakeWire([{"type": "input_audio_buffer.speech_started"}])
    rec = Recorder()
    session = _session(wire, rec)
    await session.run()
    assert wire.sent == []          # nothing to cancel
    assert rec.interrupts == 0
    assert session.state is SessionState.LISTENING


async def test_error_events_are_collected_not_fatal() -> None:
    wire = FakeWire([
        {"type": "error", "error": {"message": "rate limited"}},
        {"type": "response.done"},
    ])
    rec = Recorder()
    session = _session(wire, rec)
    await session.run()
    assert session.errors == [{"message": "rate limited"}]
    assert rec.done == 1  # session kept running after the error


async def test_full_voice_turn_state_flow() -> None:
    audio = base64.b64encode(b"pcm").decode()
    wire = FakeWire([
        {"type": "input_audio_buffer.speech_started"},
        {"type": "input_audio_buffer.speech_stopped"},
        {"type": "conversation.item.input_audio_transcription.completed",
         "transcript": "hi"},
        {"type": "response.output_audio.delta", "delta": audio},
        {"type": "response.output_audio_transcript.delta", "delta": "Hey!"},
        {"type": "response.done"},
    ])
    rec = Recorder()
    session = _session(wire, rec)
    await session.run()
    assert rec.user_transcripts == ["hi"]
    assert rec.audio == [b"pcm"]
    assert "".join(rec.assistant_text) == "Hey!"
    assert rec.done == 1
    assert session.state is SessionState.IDLE
