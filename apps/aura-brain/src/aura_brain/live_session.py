"""U324: GPT-Live — the fourth speech path (ADR-011).

The three paths before this one each gave something up. The pipeline can use
tools but does not sound natural; the realtime session sounds natural but can
use no tools at all. GPT-Live is the first design that has both: a full-duplex
voice model that, when a request needs work done, *delegates* it — and with
client delegation the work comes back to US, so it runs in AURA's own
orchestrator, behind AURA's own approval gate (constitution IV). Measured in the
U321 spikes: it heard a Dutch sentence correctly, answered in Dutch, delegated
the agenda-and-weather request, and paraphrased the result naturally.

How it maps onto this robot — each rule is a measured fact, not a preference:

* **Mic.** The robot delivers 16 kHz; the session is opened at 24 kHz and the
  chunks are resampled, like the realtime session does.
* **Silence.** The model streams output audio CONTINUOUSLY, and 74–81 % of it
  is digital silence (max RMS 19–49; voice is well above 300). Playing that, or
  counting it as "he is speaking", would flood the robot's speaker and keep the
  half-duplex mic gate shut forever — a deaf robot. So output is gated on
  loudness, with a hangover that keeps the natural pauses between words.
* **Self-hearing.** The Pi has no echo cancellation (U156), so while he speaks
  the session is told `session.input_audio.mute`, and `unmute` after the reply
  plus a speaker tail. `LIVE_BARGE_IN=true` keeps listening — only with AEC.
* **Delegation.** `session.delegation.created` carries metadata, not the task
  text, so the session keeps the user's transcript itself and hands THAT to the
  delegate. The result goes back with `session.commentary.append`, which is
  limited to 500 tokens, so it is clipped at a sentence boundary.
* **Language.** GPT-Live has no language field; the rule travels in the
  instructions, which `voice_context.build_instructions` always appends (U291).
* **Cost.** Billed per minute while a session is open, so an idle session is
  closed, and the meter counts open time rather than turns.

Nothing here raises into the voice loop except to say "this session failed";
the loop then answers through the pipeline.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from aura_brain.realtime_session import _resample_16k_to_24k

logger = logging.getLogger(__name__)

#: () -> async context manager yielding a connection with send / recv / async-iter.
LiveFactory = Callable[[], Any]
#: The user's request, as text -> the result to be spoken.
Delegate = Callable[[str], Awaitable[str]]

_RATE = 24_000
_BYTES_PER_S = _RATE * 2
#: `session.*.append` content is limited to 500 tokens; ~4 characters a token,
#: with a margin, so a clipped result is never rejected for its length.
_APPEND_CHARS = 1800
#: Voices gpt-live-1 was measured to accept (U324 smoke run, 2026-09-11):
#: `session.started` for each of these; `nova` was refused ("forbidden"). A
#: character's voice outside this set would fail `session.start` — and with it
#: the whole conversation — so it is replaced by `marin` rather than passed on.
_LIVE_VOICES = frozenset({"marin", "cedar", "coral", "verse", "ash", "sage", "alloy"})


def live_model() -> str:
    return os.environ.get("LIVE_MODEL", "gpt-live-1")


def live_voice(character_voice: str = "") -> str:
    """LIVE_VOICE wins; else the character's voice if Live is known to accept
    it; else `marin`, the voice every spike ran with."""
    pinned = os.environ.get("LIVE_VOICE", "").strip()
    if pinned:
        return pinned
    wanted = (character_voice or "").strip().lower()
    return wanted if wanted in _LIVE_VOICES else "marin"


def _default_factory() -> Any:
    from openai import AsyncOpenAI  # noqa: PLC0415

    return AsyncOpenAI().live.connect()


def _as_dict(event: Any) -> dict:
    """SDK events are pydantic objects; tests send dicts. One shape for both."""
    if isinstance(event, dict):
        return event
    for attr in ("model_dump", "to_dict"):
        fn = getattr(event, attr, None)
        if callable(fn):
            try:
                out = fn()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(out, dict):
                return out
    return {"type": getattr(event, "type", "")}


def _rms(pcm: bytes) -> float:
    usable = len(pcm) - len(pcm) % 2
    if usable <= 0:
        return 0.0
    a = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a)))


def _clip(text: str, limit: int = _APPEND_CHARS) -> str:
    """Fit one append, ending on a sentence where one ends near the limit."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:stop + 1] if stop > limit * 0.75 else cut.rstrip() + "…"


@dataclass
class LiveMeter:
    """Open time, not turns — that is what GPT-Live bills (per second).

    The orchestrator's own model calls for delegated work are billed
    separately, by whichever model it uses, and are NOT included here.
    """

    seconds: float = 0.0
    sessions: int = 0
    delegations: int = 0

    @staticmethod
    def usd_per_min() -> float:
        try:
            return float(os.environ.get("LIVE_USD_PER_MIN", "0.05"))
        except ValueError:
            return 0.05

    def add_session(self, seconds: float) -> None:
        self.sessions += 1
        self.seconds += max(0.0, seconds)

    def summary(self) -> dict:
        return {
            "sessions": self.sessions,
            "seconds": round(self.seconds, 1),
            "delegations": self.delegations,
            "usd_per_min": self.usd_per_min(),
            "estimated_usd": round(self.seconds / 60 * self.usd_per_min(), 4),
            "excludes": "the orchestrator's own model calls for delegated work",
        }


LIVE_METER = LiveMeter()


class LiveSession:
    """One open GPT-Live conversation: robot mic in, natural voice out, tools
    through the orchestrator."""

    def __init__(
        self,
        robot: Any,                      # RobotClient: stream_audio / speak_segment / stop_audio
        bus: Any,                        # TranscriptUpdated / ResponseDrafted
        session_id: str = "default",
        instructions: str = "",
        voice: str = "marin",
        conn_factory: LiveFactory | None = None,
        delegate: Delegate | None = None,
        on_reply: Callable[[str], None] | None = None,   # the echo guard
        trace: Any = None,
        context_provider: Callable[[], Awaitable[str]] | None = None,
        meter: LiveMeter | None = None,
    ) -> None:
        self._robot = robot
        self._bus = bus
        self._session_id = session_id
        # U326: Live is full duplex and has no wake word, so without this he
        # listens to a whole sentence without moving a millimetre.
        from aura_brain.body_language import ConversationBody

        self._body = ConversationBody(robot, session_id)
        self._instructions = instructions
        self._voice = voice
        self._factory = conn_factory or _default_factory
        self._delegate_fn = delegate
        self._on_reply = on_reply
        self._trace = trace
        self._context_provider = context_provider
        self._meter = meter or LIVE_METER
        self._playing_until = 0.0
        self._muted = False
        self._last_activity = time.monotonic()
        self._stopping = False
        self._closed = asyncio.Event()
        self._user_parts: list[str] = []
        self._reply_parts: list[str] = []
        self._last_user_text = ""
        self._seed_text = ""
        self._context_note: str | None = None
        self._context_checked = 0.0
        self._in_flight: set[asyncio.Task] = set()
        self._n = 0
        self.turns = 0
        self.delegations = 0
        self.closed_reason = ""
        self.remote_id = ""

    # -- knobs ---------------------------------------------------------

    @staticmethod
    def _f(name: str, default: str) -> float:
        try:
            return float(os.environ.get(name, default))
        except ValueError:
            return float(default)

    @property
    def _idle_s(self) -> float:
        # Shorter than the realtime session's 60 s: this one is billed per
        # minute for as long as it stays open.
        return self._f("LIVE_SESSION_IDLE_S", "45")

    @property
    def _max_s(self) -> float:
        return self._f("LIVE_SESSION_MAX_S", "600")

    @property
    def _speaker_tail_s(self) -> float:
        return self._f("SELF_HEARING_COOLDOWN_S", "1.2")

    @property
    def _barge_in(self) -> bool:
        return os.environ.get("LIVE_BARGE_IN", "false").lower() == "true"

    @property
    def _silence_rms(self) -> float:
        return self._f("LIVE_SILENCE_RMS", "150")

    @property
    def _hangover_bytes(self) -> int:
        return int(self._f("LIVE_VOICE_HANGOVER_S", "0.6") * _BYTES_PER_S)

    @property
    def _segment_bytes(self) -> int:
        return int(self._f("LIVE_SEGMENT_MS", "1000") / 1000 * _BYTES_PER_S)

    @property
    def _delegate_timeout_s(self) -> float:
        # Long enough for the approval gate to ask the owner and be answered.
        return self._f("LIVE_DELEGATE_TIMEOUT_S", "60")

    @property
    def _refresh_s(self) -> float:
        return self._f("REALTIME_CONTEXT_REFRESH_S", "5")

    def _eid(self, what: str) -> str:
        self._n += 1
        return f"aura_{what}_{self._n}"

    # -- protocol ------------------------------------------------------

    def start_event(self) -> dict:
        return {
            "type": "session.start",
            "event_id": self._eid("start"),
            "session": {
                "model": live_model(),
                "instructions": self._instructions,
                "audio": {"format": {"type": "audio/pcm", "rate": _RATE},
                          "output": {"voice": self._voice}},
                # Client delegation: the work comes back HERE, to the
                # orchestrator and its approval gate — never to a backend we
                # do not control.
                "delegation": {"type": "client"},
            },
        }

    async def _await_started(self, conn: Any) -> None:
        deadline = time.monotonic() + self._f("LIVE_START_TIMEOUT_S", "15")
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RuntimeError("live session did not start in time")
            ev = _as_dict(await asyncio.wait_for(conn.recv(), timeout=left))
            etype = ev.get("type", "")
            if etype == "session.started":
                self.remote_id = str((ev.get("session") or {}).get("id", ""))
                return
            if etype == "error":
                raise RuntimeError(f"live session did not start: {ev.get('error') or ev}")

    async def _send_audio(self, conn: Any, pcm24: bytes) -> None:
        step = _BYTES_PER_S // 5                      # 200 ms per message
        for i in range(0, len(pcm24) - len(pcm24) % 2, step):
            await conn.send({"type": "session.input_audio.append",
                             "audio": base64.b64encode(pcm24[i:i + step]).decode()})

    # -- run -----------------------------------------------------------

    async def run(self, initial_pcm: bytes = b"", initial_text: str = "") -> None:
        """Run until idle, the cap, the owner's Stop, or the server closes.

        `initial_pcm` is the command he was woken with, as 24 kHz audio: GPT-Live
        has no text input, so it hears the words rather than being told them.
        `initial_text` is our own transcript of it — the fallback task for a
        delegation if the model's input transcript has not arrived yet.
        """
        started = time.monotonic()
        self._seed_text = initial_text
        try:
            async with self._factory() as conn:
                await conn.send(self.start_event())
                await self._await_started(conn)
                if initial_pcm:
                    await self._send_audio(conn, initial_pcm)
                    self._last_activity = time.monotonic()
                mic = asyncio.ensure_future(self._pump_mic(conn))
                events = asyncio.ensure_future(self._pump_events(conn))
                try:
                    await self._supervise(mic, events, conn, started)
                finally:
                    tail = self._playing_until - time.monotonic()
                    if tail > 0:
                        await asyncio.sleep(min(tail + 0.3, self._f("REALTIME_TAIL_MAX_S", "20")))
                    for task in list(self._in_flight):
                        task.cancel()
                    await self._close(conn, events)
                    for task in (mic, events):
                        task.cancel()
        finally:
            self._meter.add_session(time.monotonic() - started)
            logger.info("live session closed (%s): %d replies, %d delegations, %.0fs open",
                        self.closed_reason, self.turns, self.delegations,
                        time.monotonic() - started)

    async def _supervise(self, mic: asyncio.Task, events: asyncio.Task,
                         conn: Any, started: float) -> None:
        tick = min(1.0, max(0.05, self._idle_s / 4))
        while True:
            if self._stopping:
                self.closed_reason = "stopped by owner"
                return
            done, _ = await asyncio.wait({mic, events}, timeout=tick,
                                         return_when=asyncio.FIRST_COMPLETED)
            if events in done:
                events.result()                  # re-raise a server error
                self.closed_reason = self.closed_reason or "server closed"
                return
            if mic in done:
                mic.result()
                self.closed_reason = "mic stream ended"
                return
            await self._refresh_context(conn)
            now = time.monotonic()
            if now - started > self._max_s:
                self.closed_reason = f"max session length ({self._max_s:.0f}s)"
                return
            # Waiting on the orchestrator is not idleness; neither is talking.
            busy_until = now if self._in_flight else max(self._last_activity,
                                                          self._playing_until)
            if now - busy_until > self._idle_s:
                self.closed_reason = f"idle {self._idle_s:.0f}s"
                return

    async def _close(self, conn: Any, events: asyncio.Task) -> None:
        """`session.close`, then give the server a moment to say `session.closed`
        — billing stops on the server's word, not on our socket going away."""
        if self._closed.is_set() or events.done():
            return
        try:
            await conn.send({"type": "session.close", "event_id": self._eid("close")})
            await asyncio.wait_for(self._closed.wait(),
                                   timeout=self._f("LIVE_CLOSE_WAIT_S", "5"))
        except Exception as exc:  # noqa: BLE001 — closing is best-effort
            logger.debug("live session close: %s", exc)

    def request_stop(self) -> None:
        """U184: the panic stop ends this conversation at the next tick."""
        self._stopping = True

    # -- mic → server --------------------------------------------------

    async def _set_muted(self, conn: Any, muted: bool) -> None:
        self._muted = muted
        await conn.send({"type": "session.input_audio.mute" if muted
                         else "session.input_audio.unmute",
                         "event_id": self._eid("mute" if muted else "unmute")})

    async def _pump_mic(self, conn: Any) -> None:
        async for chunk in self._robot.stream_audio():
            if not chunk:
                continue
            speaking = (not self._barge_in
                        and time.monotonic() < self._playing_until + self._speaker_tail_s)
            if speaking != self._muted:
                await self._set_muted(conn, speaking)
            if self._muted:
                continue                         # never send him his own voice
            pcm24 = _resample_16k_to_24k(chunk)
            if pcm24:
                await conn.send({"type": "session.input_audio.append",
                                 "audio": base64.b64encode(pcm24).decode()})

    # -- server → robot ------------------------------------------------

    async def _pump_events(self, conn: Any) -> None:
        play_q: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def _consume() -> None:
            first = True
            while True:
                data = await play_q.get()
                if data is None:
                    return
                if first and self._trace is not None:
                    self._trace.mark("tts_first_audio")
                    self._trace.mark("playback_first_sample")
                first = False
                try:
                    await self._robot.speak_segment(base64.b64encode(data).decode())
                except Exception as exc:  # noqa: BLE001 — drop a segment, keep talking
                    logger.debug("live segment playback failed: %s", exc)

        consumer = asyncio.ensure_future(_consume())

        async def _play(data: bytes) -> None:
            now = time.monotonic()
            self._playing_until = max(now, self._playing_until) + len(data) / _BYTES_PER_S
            await play_q.put(data)

        seg = bytearray()
        pending = bytearray()
        in_voice = False

        async def _end_utterance() -> None:
            nonlocal seg, in_voice
            if seg:
                await _play(bytes(seg))
                seg = bytearray()
            pending.clear()
            in_voice = False
            self.turns += 1
            await self._end_reply()

        try:
            async for raw in conn:
                ev = _as_dict(raw)
                etype = ev.get("type", "")
                if etype == "session.output_audio.delta":
                    pcm = base64.b64decode(ev.get("delta") or "")
                    if _rms(pcm) >= self._silence_rms:
                        if not in_voice:
                            in_voice = True
                            await self._finalize_user()
                        seg += pending
                        pending.clear()
                        seg += pcm
                        self._last_activity = time.monotonic()
                        if len(seg) >= self._segment_bytes:
                            await _play(bytes(seg))
                            seg = bytearray()
                    elif in_voice:
                        # A pause inside a sentence is part of the sentence;
                        # only a pause longer than the hangover ends it.
                        pending += pcm
                        if len(pending) >= self._hangover_bytes:
                            await _end_utterance()
                    # Silence while he is listening is not audio anybody hears.
                elif etype == "session.output_transcript.delta":
                    self._reply_parts.append(ev.get("delta") or "")
                    # U326: move with what he is saying (rate-limited inside).
                    await self._body.replying("".join(self._reply_parts))
                elif etype == "session.input_transcript.delta":
                    self._user_parts.append(ev.get("delta") or "")
                    self._last_activity = time.monotonic()
                    # U326: deltas arrive while they speak — acknowledge, paced.
                    await self._body.heard()
                elif etype == "session.delegation.created":
                    delegation = ev.get("delegation") or {}
                    task = asyncio.ensure_future(
                        self._delegate(conn, str(delegation.get("id") or "")))
                    self._in_flight.add(task)
                    task.add_done_callback(self._in_flight.discard)
                elif etype == "session.closed":
                    self.closed_reason = self.closed_reason or f"server closed ({ev.get('reason') or 'no reason'})"
                    self._closed.set()
                    return
                elif etype == "error":
                    err = ev.get("error")
                    ref = err.get("event_id", "") if isinstance(err, dict) else ""
                    if str(ref).startswith("aura_"):
                        # One of OUR commands was refused (a stale delegation, a
                        # mute out of order). That costs the command, not the
                        # conversation.
                        logger.warning("live session refused %s: %s", ref, err)
                        continue
                    raise RuntimeError(f"live session error: {err or ev}")
        finally:
            if in_voice:
                await _end_utterance()
            await play_q.put(None)
            try:
                await asyncio.wait_for(consumer, timeout=30.0)
            except (TimeoutError, asyncio.CancelledError):
                consumer.cancel()

    async def _finalize_user(self) -> None:
        """What the person said is complete once he answers or asks for help."""
        from shared_schemas.events.audio import TranscriptUpdated  # noqa: PLC0415

        text = "".join(self._user_parts).strip()
        self._user_parts.clear()
        if not text:
            return
        self._last_user_text = text
        await self._bus.publish(TranscriptUpdated(
            session_id=self._session_id, transcript=text, is_final=True))

    async def _end_reply(self) -> None:
        from shared_schemas.events.conversation import ResponseDrafted  # noqa: PLC0415

        reply = "".join(self._reply_parts).strip()
        self._reply_parts.clear()
        self._last_activity = time.monotonic()
        if not reply:
            return
        await self._bus.publish(ResponseDrafted(
            session_id=self._session_id, response_text=reply, already_voiced=True))
        if self._on_reply is not None:
            self._on_reply(reply)
        if self._trace is not None and self.turns == 1:
            self._trace.mark("llm_final")
            self._trace.reply_chars = len(reply)

    # -- delegation → orchestrator ------------------------------------

    async def _append(self, conn: Any, kind: str, delegation_id: str, content: str) -> None:
        try:
            await conn.send({"type": kind, "event_id": self._eid("d"),
                             "delegation_id": delegation_id or None,
                             "content": content})
        except Exception as exc:  # noqa: BLE001
            logger.debug("live %s failed: %s", kind, exc)

    async def _delegate(self, conn: Any, delegation_id: str) -> None:
        """Run what the person asked through the delegate; speak the result.

        U292's rule holds here too: when the work fails, he is told a FACT
        through `thinking` (not spoken verbatim) — never handed a sentence to
        say, and never an invented result through `commentary`.
        """
        await self._finalize_user()
        task_text = self._last_user_text or self._seed_text
        self._last_activity = time.monotonic()
        if self._delegate_fn is None or not task_text:
            await self._append(conn, "session.thinking.append", delegation_id,
                               "No tools are connected for this request, so it cannot be "
                               "looked up. Say that in one short sentence.")
            return
        try:
            result = await asyncio.wait_for(self._delegate_fn(task_text),
                                            timeout=self._delegate_timeout_s)
        except Exception as exc:  # noqa: BLE001 — CancelledError still propagates
            logger.warning("live delegation failed: %s", exc)
            await self._append(conn, "session.thinking.append", delegation_id,
                               f"The lookup failed ({type(exc).__name__}). Tell the person "
                               "briefly that it did not work this time.")
            return
        self.delegations += 1
        self._meter.delegations += 1
        await self._append(conn, "session.commentary.append", delegation_id,
                           _clip(result) or "The lookup returned nothing to report.")
        self._last_activity = time.monotonic()

    # -- the room ------------------------------------------------------

    async def _refresh_context(self, conn: Any) -> bool:
        """U245 for Live: when who is in the room changes, TELL the session.

        GPT-Live's instructions are appended, not replaced, so only the room
        note is sent — never the whole prompt again, which would pile up. The
        first answer is the one the session was opened with; only a change is
        worth an append. Never raises.
        """
        if self._context_provider is None or self._refresh_s <= 0:
            return False
        now = time.monotonic()
        if now - self._context_checked < self._refresh_s:
            return False
        self._context_checked = now
        try:
            note = (await self._context_provider() or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.debug("live context refresh failed: %s", exc)
            return False
        if self._context_note is None:
            self._context_note = note
            return False
        if not note or note == self._context_note:
            return False
        self._context_note = note
        await self._append(conn, "session.instructions.append", "",
                           _clip("Update — who you are talking to now:\n" + note))
        logger.info("live session told the room changed")
        return True


async def probe(conn_factory: LiveFactory | None = None) -> dict:
    """Can this account open a GPT-Live session? Opens one, waits for
    `session.started`, closes it. Billed per second, so this costs a second.
    Never raises."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"ok": False, "model": live_model(), "reason": "no OPENAI_API_KEY set"}
    factory = conn_factory or _default_factory
    voice = live_voice()
    try:
        async with factory() as conn:
            await conn.send({"type": "session.start", "event_id": "aura_probe",
                             "session": {"model": live_model(),
                                         "audio": {"format": {"type": "audio/pcm", "rate": _RATE},
                                                   "output": {"voice": voice}}}})
            ev = _as_dict(await asyncio.wait_for(conn.recv(), timeout=15))
            if ev.get("type") == "error":
                return {"ok": False, "model": live_model(),
                        "reason": f"api error: {ev.get('error') or ev}"}
            try:
                await conn.send({"type": "session.close", "event_id": "aura_probe_close"})
            except Exception:  # noqa: BLE001
                pass
            if ev.get("type") != "session.started":
                return {"ok": False, "model": live_model(),
                        "reason": f"unexpected first event {ev.get('type')!r}"}
            return {"ok": True, "model": live_model(), "voice": voice,
                    "reason": "session started",
                    "hint": "GPT-Live works on this account. It is billed per minute "
                            "while a conversation is open; idle sessions close by themselves."}
    except TimeoutError:
        return {"ok": False, "model": live_model(),
                "reason": "timed out — the Live API did not answer within 15 s"}
    except Exception as exc:  # noqa: BLE001
        raw = getattr(exc, "reason", None) or str(exc)
        return {"ok": False, "model": live_model(), "reason": f"{type(exc).__name__}: {raw}"}
