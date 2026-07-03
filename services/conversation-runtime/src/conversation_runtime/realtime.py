"""U22 — OpenAI Realtime API voice transport (GA wire protocol).

Replaces the batch whisper-1 → LLM → tts-1 chain with one persistent
speech-to-speech session: server-side VAD, streamed audio out, and barge-in
(user speech cancels the in-flight response, like interrupting a person).

The transport is written against a minimal ``RealtimeWire`` protocol — anything
with ``send(dict)`` + async iteration of event dicts. That is exactly the shape
of a raw ``websockets`` connection wrapped in JSON (and trivially adaptable to
the OpenAI SDK's realtime connection), so the full state machine is unit-tested
offline; only the socket itself needs the API key (🔒 SECRET) and a speaker/mic
(🔒 HW).

Event names follow the GA Realtime API, as proven in spikes/voice-latency.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Voice instructions mirror the spike: short spoken sentences, no markdown.
DEFAULT_INSTRUCTIONS = (
    "You are AURA, a concise desk-robot assistant. Answer in 1-2 short spoken "
    "sentences. No markdown, no lists — this will be read aloud."
)


class RealtimeWire(Protocol):
    """The minimal connection surface the transport needs."""

    async def send(self, event: dict[str, Any]) -> None: ...

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]: ...


class SessionState(StrEnum):
    IDLE = "idle"            # connected, nobody talking
    LISTENING = "listening"  # user speech detected (server VAD)
    RESPONDING = "responding"  # assistant audio streaming out


AudioSink = Callable[[bytes], Awaitable[None]]
TextSink = Callable[[str], Awaitable[None]]
EventHook = Callable[[], Awaitable[None]]


class RealtimeVoiceSession:
    """State machine for one persistent Realtime voice session.

    Callbacks (all optional, all async):
      - ``on_audio(bytes)``          — decoded PCM to play on the robot speaker
      - ``on_user_transcript(str)``  — what the user said (final transcript)
      - ``on_assistant_text(str)``   — assistant transcript deltas (for the console)
      - ``on_interrupt()``           — barge-in: STOP PLAYBACK NOW
      - ``on_response_done()``       — assistant finished a response
    """

    def __init__(
        self,
        wire: RealtimeWire,
        *,
        instructions: str = DEFAULT_INSTRUCTIONS,
        voice: str = "alloy",
        on_audio: AudioSink | None = None,
        on_user_transcript: TextSink | None = None,
        on_assistant_text: TextSink | None = None,
        on_interrupt: EventHook | None = None,
        on_response_done: EventHook | None = None,
    ) -> None:
        self._wire = wire
        self._instructions = instructions
        self._voice = voice
        self._on_audio = on_audio
        self._on_user_transcript = on_user_transcript
        self._on_assistant_text = on_assistant_text
        self._on_interrupt = on_interrupt
        self._on_response_done = on_response_done
        self.state = SessionState.IDLE
        self.errors: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Client → server
    # ------------------------------------------------------------------

    async def configure(self) -> None:
        """session.update — voice, VAD, and audio format (once after connect)."""
        await self._wire.send({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": self._instructions,
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24_000},
                        "turn_detection": {"type": "server_vad"},
                    },
                    "output": {
                        "voice": self._voice,
                        "format": {"type": "audio/pcm", "rate": 24_000},
                    },
                },
            },
        })

    async def send_audio(self, pcm: bytes) -> None:
        """Stream a mic chunk. Server VAD segments turns — no commit needed."""
        await self._wire.send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm).decode(),
        })

    async def send_text(self, text: str) -> None:
        """Text-initiated turn (console input) over the same session."""
        await self._wire.send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        })
        await self._wire.send({"type": "response.create"})

    # ------------------------------------------------------------------
    # Server → client
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Consume server events until the wire closes."""
        async for event in self._wire:
            await self._handle(event)

    async def _handle(self, event: dict[str, Any]) -> None:
        etype = event.get("type", "")

        if etype == "input_audio_buffer.speech_started":
            # Barge-in: the user started talking. If AURA is mid-answer, cancel
            # the response AND stop local playback immediately.
            if self.state is SessionState.RESPONDING:
                await self._wire.send({"type": "response.cancel"})
                if self._on_interrupt is not None:
                    await self._on_interrupt()
                logger.debug("barge-in: response cancelled")
            self.state = SessionState.LISTENING

        elif etype == "input_audio_buffer.speech_stopped":
            if self.state is SessionState.LISTENING:
                self.state = SessionState.IDLE

        elif etype == "conversation.item.input_audio_transcription.completed":
            if self._on_user_transcript is not None:
                await self._on_user_transcript(event.get("transcript", ""))

        elif "audio.delta" in etype and "transcript" not in etype:
            self.state = SessionState.RESPONDING
            if self._on_audio is not None:
                await self._on_audio(base64.b64decode(event.get("delta", "") or ""))

        elif etype.endswith("transcript.delta") or etype.endswith("text.delta"):
            self.state = SessionState.RESPONDING
            if self._on_assistant_text is not None:
                await self._on_assistant_text(event.get("delta", "") or "")

        elif etype in ("response.done", "response.cancelled"):
            self.state = SessionState.IDLE
            if self._on_response_done is not None:
                await self._on_response_done()

        elif etype == "error":
            # Keep the session alive on recoverable errors; surface them all.
            self.errors.append(event.get("error", event))
            logger.warning("realtime error event: %s", event.get("error", event))
