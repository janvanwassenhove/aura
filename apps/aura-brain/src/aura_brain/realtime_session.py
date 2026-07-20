"""U154: conversation-session mode — ChatGPT-voice-style fluid turns.

One persistent Realtime connection per conversation instead of one per turn.
The robot's mic streams continuously into the session; the Realtime server's
VAD (semantic by default) decides when the user finished a sentence — no fixed
capture windows, no local STT step, no second listen window. Reply audio
streams back out through the U153 segment playback path, so the first words
play while the model is still generating.

Lifecycle: the wake word (voice_loop) opens a session and passes the already-
captured first command as text; within the session the user just talks — no
wake word. The session closes on idle (REALTIME_SESSION_IDLE_S without any
speech or response) or an absolute cap (REALTIME_SESSION_MAX_S), bounding cost.

Self-hearing (§6.1): the robot has no acoustic echo cancellation, so the mic
hears Richie's own speaker. The session is half-duplex: while reply segments
are playing (tracked brain-side via a playback clock) mic chunks are DROPPED,
not appended — the server never hears the robot's own voice. The trade-off is
honest: no true mid-sentence barge-in in this mode (the pipeline's loudness
barge-in doesn't run either); interrupting works again the moment a reply
finishes. True barge-in needs AEC on the robot — out of scope here.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Any

import numpy as np

from aura_brain.realtime_voice import (
    METER,
    ConnFactory,
    CostMeter,
    _default_conn_factory,
    _default_realtime_model,
    _usage_dict,
)

logger = logging.getLogger(__name__)


def session_enabled() -> bool:
    """Session mode rides on the realtime engine; opt out per env."""
    return os.environ.get("REALTIME_SESSION", "true").lower() == "true"


def _turn_detection(vad: str) -> dict:
    """Server-side turn detection config (U163).

    semantic_vad decides end-of-turn from meaning as well as silence; its
    ``eagerness`` controls how readily it commits. The default fires on short
    pauses, which — combined with an over-amplified mic — made the session
    treat room noise as turns and reply to nothing. ``low`` waits for a clear
    end-of-turn. server_vad instead takes explicit silence/threshold numbers.
    """
    if vad == "semantic_vad":
        return {
            "type": "semantic_vad",
            "eagerness": os.environ.get("REALTIME_VAD_EAGERNESS", "low"),
        }
    return {
        "type": vad,
        "threshold": float(os.environ.get("REALTIME_VAD_THRESHOLD", "0.6")),
        "silence_duration_ms": int(os.environ.get("REALTIME_VAD_SILENCE_MS", "900")),
        "prefix_padding_ms": int(os.environ.get("REALTIME_VAD_PREFIX_MS", "300")),
    }


def _resample_16k_to_24k(chunk: bytes) -> bytes:
    """Mic chunks arrive as s16le mono 16 kHz; Realtime input is 24 kHz."""
    audio = np.frombuffer(chunk, dtype=np.int16)
    if audio.size == 0:
        return b""
    idx = np.linspace(0, audio.size - 1, int(audio.size * 24_000 / 16_000))
    return np.interp(idx, np.arange(audio.size), audio).astype(np.int16).tobytes()


class RealtimeSession:
    """One open conversation: mic in → server VAD → streamed reply out."""

    def __init__(
        self,
        robot: Any,                    # RobotClient: stream_audio/speak_segment/…
        bus: Any,                      # event bus (TranscriptUpdated/ResponseDrafted)
        session_id: str = "default",
        instructions: str = "",
        voice: str = "alloy",
        conn_factory: ConnFactory | None = None,
        meter: CostMeter | None = None,
        on_reply=None,                 # callable(str) — feeds the echo guard
        trace=None,                    # TurnTrace | None — first-turn latency marks
    ) -> None:
        self._robot = robot
        self._bus = bus
        self._session_id = session_id
        self._instructions = instructions
        self._voice = voice
        self._factory = conn_factory or _default_conn_factory
        self._meter = meter or METER
        self._on_reply = on_reply
        self._trace = trace
        self._last_activity = time.monotonic()
        # Playback clock: mic chunks are dropped while now < _playing_until
        # (+ a speaker tail) so the server never hears Richie's own voice.
        self._playing_until = 0.0
        # U163: mic stays shut until this time (seed-utterance tail, see run()).
        self._mic_open_at = 0.0
        self._first_segment_played = False
        self.turns = 0
        self.closed_reason = ""

    # -- knobs ---------------------------------------------------------

    @property
    def _idle_s(self) -> float:
        return float(os.environ.get("REALTIME_SESSION_IDLE_S", "60"))

    @property
    def _max_s(self) -> float:
        return float(os.environ.get("REALTIME_SESSION_MAX_S", "600"))

    @property
    def _speaker_tail_s(self) -> float:
        return float(os.environ.get("SELF_HEARING_COOLDOWN_S", "1.2"))

    @property
    def _barge_in(self) -> bool:
        """U156: full duplex — keep the mic streaming during playback and let
        the server VAD interrupt Richie mid-sentence. Requires the robot's
        WebRTC AEC path (ROBOT_WEBRTC_AEC on the Pi), otherwise the server
        hears Richie's own voice; hence opt-in and OFF by default."""
        return os.environ.get("REALTIME_BARGE_IN", "false").lower() == "true"

    # -- run -----------------------------------------------------------

    async def run(self, initial_text: str = "") -> None:
        """Run the session until idle/max timeout or the mic stream ends.
        Raises on connection/API errors so the caller can fall back."""
        model = _default_realtime_model()
        started = time.monotonic()
        vad = os.environ.get("REALTIME_VAD", "semantic_vad")
        async with self._factory(model) as conn:
            await conn.session.update(session={
                "type": "realtime",
                "output_modalities": ["audio"],
                "instructions": self._instructions or (
                    "You are a friendly robot assistant. Reply in the language "
                    "the user speaks (Dutch, English, French or German). Keep "
                    "spoken replies concise."),
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        # U163: eagerness=low — the default fires on the
                        # slightest pause, so room noise and the tail of a
                        # reply became "turns" and Richie answered nothing.
                        # Low waits for a clear end-of-turn.
                        "turn_detection": _turn_detection(vad),
                        "transcription": {"model": os.environ.get(
                            "STT_MODEL", "gpt-4o-mini-transcribe")},
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self._voice,
                    },
                },
            })
            if initial_text:
                # The wake-window already captured the first command — answer
                # it immediately instead of making the user repeat it.
                await conn.conversation.item.create(item={
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": initial_text}]})
                await conn.response.create()
                self._last_activity = time.monotonic()
                # U163: that utterance is already answered, but the mic stream
                # opens on its TAIL (and the room's reverb of it). Feeding that
                # to the server VAD produced a second, duplicate reply to the
                # same sentence — the "double answer" in the transcript. Hold
                # the mic shut until the sentence has fully died away.
                self._mic_open_at = time.monotonic() + float(
                    os.environ.get("REALTIME_SEED_MUTE_S", "1.5"))

            mic = asyncio.ensure_future(self._pump_mic(conn))
            events = asyncio.ensure_future(self._pump_events(conn))
            try:
                tick = min(1.0, max(0.05, self._idle_s / 4))
                while True:
                    done, _ = await asyncio.wait(
                        {mic, events}, timeout=tick,
                        return_when=asyncio.FIRST_COMPLETED)
                    if events in done:
                        events.result()  # surface API errors to the caller
                        self.closed_reason = self.closed_reason or "server closed"
                        return
                    if mic in done:
                        mic.result()
                        self.closed_reason = "mic stream ended"
                        return
                    now = time.monotonic()
                    if now - started > self._max_s:
                        self.closed_reason = f"max session length ({self._max_s:.0f}s)"
                        return
                    # Don't idle out mid-reply: playback counts as activity.
                    busy_until = max(self._last_activity, self._playing_until)
                    if now - busy_until > self._idle_s:
                        self.closed_reason = f"idle {self._idle_s:.0f}s"
                        return
            finally:
                # U157: let the tail of the last reply finish before closing
                # the mic stream — its teardown stops the robot's SHARED audio
                # pipeline (stop_recording → NULL), which would clip the reply.
                tail = self._playing_until - time.monotonic()
                if tail > 0:
                    cap = float(os.environ.get("REALTIME_TAIL_MAX_S", "20"))
                    await asyncio.sleep(min(tail + 0.3, cap))
                for t in (mic, events):
                    t.cancel()
                logger.info("realtime session closed (%s): %d turns, ~$%.4f total",
                            self.closed_reason, self.turns, self._meter.spent_usd())

    # -- mic → server --------------------------------------------------

    async def _pump_mic(self, conn) -> None:
        barge = self._barge_in
        async for chunk in self._robot.stream_audio():
            if not chunk:
                continue
            # Half-duplex gate: drop mic audio while Richie is (probably still)
            # speaking, plus a speaker tail — the classic §6.1 self-hearing fix.
            # With AEC + barge-in (U156) the mic keeps streaming: the echo is
            # cancelled robot-side, so the server can hear the user interrupt.
            if time.monotonic() < self._mic_open_at:
                continue  # U163: tail of the already-answered seed utterance
            if not barge and time.monotonic() < self._playing_until + self._speaker_tail_s:
                continue
            pcm24 = _resample_16k_to_24k(chunk)
            if pcm24:
                await conn.input_audio_buffer.append(
                    audio=base64.b64encode(pcm24).decode())

    # -- server → robot ------------------------------------------------

    async def _pump_events(self, conn) -> None:
        from shared_schemas.events.audio import TranscriptUpdated
        from shared_schemas.events.conversation import ResponseDrafted

        seg = bytearray()
        seg_bytes = int(24_000 * 2 * float(
            os.environ.get("REALTIME_SEGMENT_MS", "1400")) / 1000)
        reply_parts: list[str] = []

        # U155: ORDERED playback — a dedicated consumer posts segments one by
        # one. The previous fire-and-forget ensure_future could deliver
        # segments out of order and hit the 10 s HTTP timeout on long replies
        # (segments queued behind earlier playback) → audible hangs mid-reply.
        play_q: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def _consume() -> None:
            while True:
                data = await play_q.get()
                if data is None:
                    return
                if not self._first_segment_played:
                    self._first_segment_played = True
                    if self._trace is not None:
                        self._trace.mark("tts_first_audio")
                        self._trace.mark("playback_first_sample")
                try:
                    await self._robot.speak_segment(base64.b64encode(data).decode())
                except Exception as exc:  # noqa: BLE001 — drop, don't die
                    logger.debug("segment playback failed: %s", exc)

        consumer = asyncio.ensure_future(_consume())

        async def _play(data: bytes) -> None:
            dur = len(data) / (24_000 * 2)
            now = time.monotonic()
            # The robot's appsrc path buffers and returns immediately →
            # playback is serial in push order; extend the estimate clock.
            self._playing_until = max(now, self._playing_until) + dur
            await play_q.put(data)

        try:
            async for event in conn:
                etype = getattr(event, "type", "")
                if etype in ("response.output_audio.delta", "response.audio.delta"):
                    self._last_activity = time.monotonic()
                    seg += base64.b64decode(getattr(event, "delta", "") or "")
                    if len(seg) >= seg_bytes:
                        await _play(bytes(seg))
                        seg = bytearray()
                elif etype in ("response.output_audio_transcript.delta",
                               "response.audio_transcript.delta"):
                    reply_parts.append(getattr(event, "delta", "") or "")
                elif etype == "input_audio_buffer.speech_started":
                    self._last_activity = time.monotonic()
                    # U156: user starts talking while Richie is still playing →
                    # true barge-in (only reachable with AEC full duplex; in
                    # half-duplex the gated mic can't trigger this mid-reply).
                    if self._barge_in and time.monotonic() < self._playing_until:
                        logger.info("barge-in: user interrupts — cutting playback")
                        seg = bytearray()          # drop unplayed audio
                        self._playing_until = 0.0
                        try:
                            await self._robot.stop_audio()
                        except Exception:  # noqa: BLE001 — cut is best-effort
                            pass
                        try:
                            await conn.response.cancel()
                        except Exception:  # noqa: BLE001 — may already be done
                            pass
                elif etype == "input_audio_buffer.speech_stopped":
                    self._last_activity = time.monotonic()
                elif etype in ("conversation.item.input_audio_transcription.completed",
                               "conversation.item.audio_transcription.completed"):
                    text = (getattr(event, "transcript", "") or "").strip()
                    if text:
                        await self._bus.publish(TranscriptUpdated(
                            session_id=self._session_id, transcript=text,
                            is_final=True))
                elif etype == "response.done":
                    if seg:  # flush the reply's tail
                        await _play(bytes(seg))
                        seg = bytearray()
                    self._last_activity = time.monotonic()
                    self.turns += 1
                    reply = "".join(reply_parts).strip()
                    reply_parts.clear()
                    if reply:
                        await self._bus.publish(ResponseDrafted(
                            session_id=self._session_id, response_text=reply,
                            already_voiced=True))
                        if self._on_reply is not None:
                            self._on_reply(reply)
                    if self._trace is not None and self.turns == 1:
                        self._trace.mark("llm_final")
                        self._trace.reply_chars = len(reply)
                    resp = getattr(event, "response", None)
                    self._meter.add(_usage_dict(getattr(resp, "usage", None)))
                elif etype == "error":
                    err = getattr(event, "error", "")
                    # Session-level VAD/turn errors shouldn't kill the whole
                    # conversation loop; real failures (auth, model) should.
                    raise RuntimeError(f"realtime session error: {err}")
        finally:
            await play_q.put(None)  # drain remaining segments, then stop
            try:
                await asyncio.wait_for(consumer, timeout=30.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                consumer.cancel()
