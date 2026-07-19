"""U140 (voice-brief Phase 0): per-turn latency traces — instrument first.

One structured trace per conversational turn, with monotonic timestamps at
every pipeline stage. Nothing may be optimised until these numbers exist:
the report proves where the milliseconds go instead of guessing.

Stages (subset fires depending on path; missing marks stay null):
    capture_start        first sample of the capture window (approximate:
                         the current pipeline records FIXED windows, so this
                         is window_end - window_length, not a VAD frame)
    capture_end          capture window closed
    endpoint_fired       system decided the user is done (== capture_end
                         today — fixed windows have no real endpointing)
    stt_final            final transcript available
    llm_request_sent     request handed to the model
    llm_first_token      first token back (== llm_final today: non-streaming)
    llm_final            full completion available
    tts_request_sent     synthesis requested
    tts_first_audio      first audio byte available (== full audio today)
    playback_first_sample robot playback started
    playback_complete    robot playback finished

Mouth-to-ear = playback_first_sample − endpoint_fired. With fixed windows the
true "user stopped speaking" moment is unknown; endpoint_fired is the honest
proxy and the baseline doc says so.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STAGES = (
    "capture_start", "capture_end", "endpoint_fired", "stt_final",
    # U153: a bare wake word ("Richie" alone) triggers a SECOND full listen
    # window for the actual command — this is the big gap the traces showed
    # inside llm_queue. These marks bracket it so it's visible, not hidden.
    "second_capture_start", "second_capture_end",
    "llm_request_sent", "llm_first_token", "llm_final",
    "tts_request_sent", "tts_first_audio",
    "playback_first_sample", "playback_complete",
)

# Consecutive stage pairs whose deltas make up the turn breakdown.
_SEGMENTS = (
    ("capture", "capture_start", "capture_end"),
    ("endpoint_wait", "capture_end", "endpoint_fired"),
    ("stt", "endpoint_fired", "stt_final"),
    # U153: only present on bare-wake turns; otherwise the marks are absent and
    # this segment is None while llm_queue spans stt_final → llm_request_sent.
    ("second_capture", "second_capture_start", "second_capture_end"),
    ("llm_queue", "stt_final", "llm_request_sent"),
    ("llm", "llm_request_sent", "llm_final"),
    ("tts", "tts_request_sent", "tts_first_audio"),
    ("playback_start", "tts_first_audio", "playback_first_sample"),
    ("playback", "playback_first_sample", "playback_complete"),
)


@dataclass
class TurnTrace:
    session_id: str
    turn_id: int
    engine: str = "pipeline"          # pipeline | realtime
    transcript: str = ""
    reply_chars: int = 0
    started_at: float = field(default_factory=time.time)  # wall clock, for the log
    marks: dict[str, float] = field(default_factory=dict)  # stage -> monotonic s
    notes: list[str] = field(default_factory=list)

    def mark(self, stage: str, ts: float | None = None) -> None:
        """Record a stage timestamp once (first write wins)."""
        if stage in STAGES:
            self.marks.setdefault(stage, ts if ts is not None else time.monotonic())

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    # -- derived numbers -------------------------------------------------

    def _delta_ms(self, a: str, b: str) -> float | None:
        if a in self.marks and b in self.marks:
            return round((self.marks[b] - self.marks[a]) * 1000.0, 1)
        return None

    def mouth_to_ear_ms(self) -> float | None:
        """endpoint_fired → first audible sample (the §2 headline metric)."""
        return self._delta_ms("endpoint_fired", "playback_first_sample")

    def breakdown_ms(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for name, a, b in _SEGMENTS:
            d = self._delta_ms(a, b)
            if d is not None:
                out[name] = d
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "engine": self.engine,
            "started_at": round(self.started_at, 3),
            "transcript": self.transcript[:120],
            "reply_chars": self.reply_chars,
            "mouth_to_ear_ms": self.mouth_to_ear_ms(),
            "breakdown_ms": self.breakdown_ms(),
            "notes": self.notes,
        }


class TraceLog:
    """Ring of recent traces + one JSON line per completed turn on disk."""

    def __init__(self, keep: int = 50, path: str | None = None) -> None:
        self._keep = keep
        self._ring: list[TurnTrace] = []
        self._current: dict[str, TurnTrace] = {}
        self._turn_counter = 0
        self._path = path

    def _resolved_path(self) -> str | None:
        # Read the env lazily so tests can redirect it. Empty string disables.
        path = self._path if self._path is not None else os.environ.get(
            "TURN_TRACE_PATH", os.path.join("data", "turn_traces.jsonl"))
        return path or None

    def start(self, session_id: str, engine: str = "pipeline") -> TurnTrace:
        """Begin a new turn; an unfinished previous turn is finalised as-is."""
        dangling = self._current.pop(session_id, None)
        if dangling is not None:
            dangling.note("finalised by next turn (no playback_complete)")
            self._store(dangling)
        self._turn_counter += 1
        trace = TurnTrace(session_id=session_id, turn_id=self._turn_counter, engine=engine)
        self._current[session_id] = trace
        return trace

    def current(self, session_id: str) -> TurnTrace | None:
        return self._current.get(session_id)

    def discard(self, session_id: str) -> None:
        """Drop the in-flight trace (e.g. window turned out to be silence)."""
        self._current.pop(session_id, None)

    def finish(self, session_id: str) -> None:
        trace = self._current.pop(session_id, None)
        if trace is not None:
            self._store(trace)

    def _store(self, trace: TurnTrace) -> None:
        self._ring.append(trace)
        del self._ring[:-self._keep]
        path = self._resolved_path()
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.debug("turn trace not written: %s", exc)

    # -- reporting -------------------------------------------------------

    def report(self, n: int = 20) -> dict[str, Any]:
        """Last ``n`` completed turns, slowest first, plus p50/p95 aggregates."""
        recent = self._ring[-n:]
        turns = sorted((t.to_dict() for t in recent),
                       key=lambda d: d.get("mouth_to_ear_ms") or 0.0, reverse=True)
        m2e = sorted(t["mouth_to_ear_ms"] for t in turns
                     if t.get("mouth_to_ear_ms") is not None)

        def _pct(p: float) -> float | None:
            if not m2e:
                return None
            idx = min(len(m2e) - 1, max(0, round(p * (len(m2e) - 1))))
            return m2e[idx]

        return {
            "count": len(turns),
            "mouth_to_ear_p50_ms": _pct(0.50),
            "mouth_to_ear_p95_ms": _pct(0.95),
            "turns": turns,
        }


# One log per brain process.
LOG = TraceLog()
