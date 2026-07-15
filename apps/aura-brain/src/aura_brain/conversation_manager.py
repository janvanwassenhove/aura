"""U84: conversation state machine — the one owner of turn state.

Everything that used to be scattered timing (speaking_until, followup_until,
ad-hoc flags) reports here instead. The manager owns:

  - the active turn id
  - the current ConversationState
  - cancellation events for the LLM turn and the TTS/audio playback
  - interruption status (so the NEXT turn can tell the LLM its previous
    answer was cut off)
  - the selected character persona (U84 characters.py)

Structured logging: every transition emits ONE log line with timestamp,
state, event, turn id, tts_playing, llm_active and cancel_requested — never
raw audio, transcripts are truncated, and never secrets.

The manager is transport-agnostic and fully testable without hardware: the
speak/LLM sides register handles; interrupt() cancels through them.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum

logger = logging.getLogger("aura.conversation")


class ConversationState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class ConversationManager:
    def __init__(self, *, stop_robot_audio: Callable[[], Awaitable[object]] | None = None) -> None:
        self._state = ConversationState.IDLE
        self._turn_ids = itertools.count(1)
        self.turn_id = 0
        # Cancellation tokens (one pair per turn; re-armed in begin_turn).
        self.llm_cancel = asyncio.Event()
        self.tts_cancel = asyncio.Event()
        # Live handles registered by the speak side.
        self._speak_task: asyncio.Task | None = None
        self._stop_robot_audio = stop_robot_audio
        # Interruption context for the NEXT turn.
        self.interrupted_reply: str | None = None
        self._llm_active = False
        self._tts_playing = False
        self.character = None  # CharacterPersona | None (characters.py)

    # -- observability ---------------------------------------------------

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def tts_playing(self) -> bool:
        return self._tts_playing

    @property
    def llm_active(self) -> bool:
        return self._llm_active

    def _log(self, event: str, **extra: object) -> None:
        logger.info(
            "conv state=%s event=%s turn=%d tts_playing=%s llm_active=%s "
            "cancel_requested=%s%s",
            self._state.value, event, self.turn_id,
            self._tts_playing, self._llm_active,
            self.llm_cancel.is_set() or self.tts_cancel.is_set(),
            "".join(f" {k}={v}" for k, v in extra.items()),
        )

    def _transition(self, new: ConversationState, event: str, **extra: object) -> None:
        if new is not self._state:
            self._state = new
        self._log(event, **extra)

    # -- turn lifecycle ----------------------------------------------------

    def begin_turn(self, source: str = "voice") -> int:
        """A new user turn becomes active; previous cancellation state is
        re-armed. Returns the new turn id."""
        self.turn_id = next(self._turn_ids)
        self.llm_cancel = asyncio.Event()
        self.tts_cancel = asyncio.Event()
        self._transition(ConversationState.TRANSCRIBING, f"turn_started:{source}")
        return self.turn_id

    def thinking(self) -> None:
        self._llm_active = True
        self._transition(ConversationState.THINKING, "llm_started")

    def speaking(self) -> None:
        self._llm_active = False
        self._tts_playing = True
        self._transition(ConversationState.SPEAKING, "tts_started")

    def listening(self) -> None:
        self._llm_active = False
        self._tts_playing = False
        self._transition(ConversationState.LISTENING, "listening")

    def user_speaking(self) -> None:
        self._transition(ConversationState.USER_SPEAKING, "vad_speech")

    def idle(self) -> None:
        self._llm_active = False
        self._tts_playing = False
        self._transition(ConversationState.IDLE, "idle")

    def error(self, what: str) -> None:
        self._llm_active = False
        self._tts_playing = False
        self._transition(ConversationState.ERROR, f"error:{what[:120]}")

    def shutdown(self) -> None:
        self.llm_cancel.set()
        self.tts_cancel.set()
        self._transition(ConversationState.SHUTTING_DOWN, "shutdown")

    # -- speak-side registration -------------------------------------------

    def register_speak_task(self, task: asyncio.Task) -> None:
        """The embodiment layer hands over its speak task so interrupt() can
        cancel it. Also flips SPEAKING state bookkeeping on completion."""
        self._speak_task = task
        self.speaking()

        def _done(_t: asyncio.Task) -> None:
            self._tts_playing = False
            if self._state is ConversationState.SPEAKING:
                self._transition(ConversationState.LISTENING, "tts_finished")

        task.add_done_callback(_done)

    # -- the core feature: barge-in ------------------------------------------

    async def interrupt(self, reply_text: str = "") -> None:
        """The user talked over the robot. Cut EVERYTHING now:
        stop robot playback, cancel the speak task, cancel the LLM turn, and
        remember what was interrupted so the next turn can mention it."""
        t0 = time.perf_counter()
        self.llm_cancel.set()
        self.tts_cancel.set()
        self.interrupted_reply = (reply_text or "")[:200] or self.interrupted_reply
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()
        if self._stop_robot_audio is not None:
            try:
                await self._stop_robot_audio()
            except Exception:  # noqa: BLE001 — robot offline; nothing to stop
                pass
        self._tts_playing = False
        self._llm_active = False
        self._transition(
            ConversationState.INTERRUPTED, "barge_in",
            cut_ms=round((time.perf_counter() - t0) * 1000),
        )

    def consume_interruption_note(self) -> str:
        """One-shot system note for the next LLM turn after a barge-in."""
        if self.interrupted_reply is None:
            return ""
        cut = self.interrupted_reply
        self.interrupted_reply = None
        return (
            "[The user interrupted your previous answer mid-sentence "
            f"(it was: \"{cut}…\"). Do not restart or repeat it — respond to "
            "what they just said, briefly.]"
        )
