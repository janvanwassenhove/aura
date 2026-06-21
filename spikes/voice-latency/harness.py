"""Phase 0 voice-latency spike — instrumented streaming voice round-trip.

THROWAWAY SPIKE. Purpose: produce *measured* first-word-out and full-turn
latency for the streaming voice path, to make the Phase 0 go/no-go decision
(see docs/reshape-plan.md). Correctness/cleanliness are secondary to honest
numbers.

Pipeline (the thing we're proving):
    [audio mode] mic → endpoint → streaming STT ─┐
    [text mode]  typed prompt ───────────────────┴─► streaming LLM (token stream)
        └─► first *clause* starts TTS immediately (don't wait for full answer)
            └─► streaming TTS → first audio byte = "first word out"
                └─► (audio mode) speaker playback + barge-in

Two modes:
  --mode text   (default) no hardware: measures LLM TTFT + first-clause + TTS
                first-byte + full turn. Runnable on the laptop right now.
  --mode audio  mic + speaker (needs `sounddevice`); adds STT and barge-in.

Run:
  uv run python harness.py --mode text --turns 5
  uv run python harness.py --mode text --prompt "What meetings do I have today?"
  uv run python harness.py --mode audio            # on the Reachy/laptop with mic

The headline metric is FIRST AUDIO OUT (submit → first TTS byte): the proxy for
"how long until AURA starts talking". Target from the plan: < ~700 ms.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from dataclasses import dataclass, field

from openai import AsyncOpenAI

# Windows consoles default to cp1252; force UTF-8 so the report glyphs print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DEFAULT_LLM_MODEL = "gpt-4o-mini"   # the responsive choice; override with --model
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "alloy"
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"

SYSTEM_PROMPT = (
    "You are AURA, a concise desk-robot assistant. Answer in 1-2 short spoken "
    "sentences. No markdown, no lists — this will be read aloud."
)

# Start TTS as soon as we have a clause this long or hit sentence punctuation.
_FIRST_CLAUSE_MIN_CHARS = 40
_CLAUSE_ENDINGS = ".!?;:"


# --------------------------------------------------------------------------- #
# Timing record
# --------------------------------------------------------------------------- #


@dataclass
class TurnTiming:
    """All times are perf_counter seconds, relative to submit (t0)."""

    prompt: str
    stt_ms: float | None = None          # audio mode: speech-end → transcript
    llm_first_token_ms: float = 0.0      # submit → first LLM token
    first_clause_ms: float = 0.0         # submit → first clause ready for TTS
    first_audio_ms: float = 0.0          # submit → first TTS audio byte  ◄ HEADLINE
    llm_done_ms: float = 0.0             # submit → LLM completion
    full_turn_ms: float = 0.0            # submit → last TTS audio byte
    reply: str = ""
    audio_bytes: int = 0


@dataclass
class Report:
    timings: list[TurnTiming] = field(default_factory=list)

    def add(self, t: TurnTiming) -> None:
        self.timings.append(t)

    def _col(self, attr: str) -> list[float]:
        return [getattr(t, attr) for t in self.timings if getattr(t, attr) is not None]

    def summary(self) -> str:
        def stat(attr: str, label: str) -> str:
            vals = self._col(attr)
            if not vals:
                return f"  {label:<26} (n/a)"
            med = statistics.median(vals)
            p95 = sorted(vals)[max(0, int(len(vals) * 0.95) - 1)]
            return f"  {label:<26} median {med:7.0f} ms   p95 {p95:7.0f} ms   (n={len(vals)})"

        lines = ["", "=" * 64, "  VOICE LATENCY SPIKE — RESULTS", "=" * 64]
        if any(t.stt_ms for t in self.timings):
            lines.append(stat("stt_ms", "STT (speech-end→text)"))
        lines += [
            stat("llm_first_token_ms", "LLM first token"),
            stat("first_clause_ms", "First clause ready"),
            stat("first_audio_ms", "► FIRST AUDIO OUT"),
            stat("llm_done_ms", "LLM full completion"),
            stat("full_turn_ms", "Full turn (last audio)"),
            "=" * 64,
        ]
        med_first = statistics.median(self._col("first_audio_ms")) if self._col("first_audio_ms") else 0
        verdict = "GO ✅  (feels responsive)" if med_first < 700 else (
            "MARGINAL ⚠️  (700–1200ms)" if med_first < 1200 else "NO-GO ❌  (>1200ms — fix transport first)"
        )
        lines += [f"  Go/no-go (first audio < 700ms): {verdict}", "=" * 64, ""]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Core streaming pipeline
# --------------------------------------------------------------------------- #


class VoiceTurn:
    def __init__(self, client: AsyncOpenAI, llm_model: str, tts_model: str, voice: str,
                 sink=None) -> None:
        self._client = client
        self._llm_model = llm_model
        self._tts_model = tts_model
        self._voice = voice
        self._sink = sink  # async callable(bytes) for audio mode playback; None = discard

    async def run(self, prompt: str, t0: float | None = None) -> TurnTiming:
        t0 = t0 if t0 is not None else time.perf_counter()
        timing = TurnTiming(prompt=prompt)

        # The whole point: TTS the FIRST CLAUSE the moment it's ready, while the
        # LLM keeps streaming the rest. We pipeline clause-1 → (remainder) so the
        # robot starts talking ~TTFT+TTS-first-byte, not full-completion+TTS.
        clause_q: asyncio.Queue[str | None] = asyncio.Queue()
        total = 0
        first_byte_seen = asyncio.Event()

        async def speak_consumer() -> None:
            nonlocal total
            while True:
                text = await clause_q.get()
                if text is None:
                    return
                async with self._client.audio.speech.with_streaming_response.create(
                    model=self._tts_model, voice=self._voice,
                    input=text, response_format="pcm",
                ) as resp:
                    async for audio_chunk in resp.iter_bytes(chunk_size=4096):
                        if not audio_chunk:
                            continue
                        if not first_byte_seen.is_set():
                            timing.first_audio_ms = (time.perf_counter() - t0) * 1000
                            first_byte_seen.set()
                        total += len(audio_chunk)
                        if self._sink is not None:
                            await self._sink(audio_chunk)

        speaker = asyncio.create_task(speak_consumer())

        # --- stream the LLM; emit clauses to the speaker as they complete ---
        buf = ""           # text not yet sent to TTS
        full = ""
        got_first_token = False

        stream = await self._client.chat.completions.create(
            model=self._llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )

        first_clause_sent = False
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if not delta:
                continue
            if not got_first_token:
                timing.llm_first_token_ms = (time.perf_counter() - t0) * 1000
                got_first_token = True
            buf += delta
            full += delta
            # Flush a clause to TTS at the first sentence boundary (or once it's
            # long enough that waiting would only add latency).
            if not first_clause_sent and (
                any(c in buf for c in _CLAUSE_ENDINGS) or len(buf) >= _FIRST_CLAUSE_MIN_CHARS
            ):
                timing.first_clause_ms = (time.perf_counter() - t0) * 1000
                await clause_q.put(buf.strip())
                buf = ""
                first_clause_sent = True

        timing.llm_done_ms = (time.perf_counter() - t0) * 1000
        timing.reply = full.strip()

        # send whatever's left (the remainder, or the whole reply if it was short)
        if buf.strip():
            await clause_q.put(buf.strip())
        await clause_q.put(None)  # sentinel: no more clauses
        await speaker

        timing.full_turn_ms = (time.perf_counter() - t0) * 1000
        timing.audio_bytes = total
        return timing


# --------------------------------------------------------------------------- #
# Text mode (no hardware) — runnable now
# --------------------------------------------------------------------------- #


async def run_text_mode(args) -> None:
    client = AsyncOpenAI()
    turn = VoiceTurn(client, args.model, args.tts_model, args.voice, sink=None)
    report = Report()

    prompts = [args.prompt] if args.prompt else [
        "What meetings do I have today?",
        "Remind me to call the plumber at four.",
        "What's the weather looking like this afternoon?",
        "Tell me a fun fact about octopuses.",
        "Summarize my unread email in one line.",
    ]

    print(f"\nLLM={args.model}  TTS={args.tts_model}  voice={args.voice}")
    print("Warming up (1 untimed turn)…")
    await turn.run("Say ready.")

    for i in range(args.turns):
        p = prompts[i % len(prompts)]
        t = await turn.run(p)
        report.add(t)
        print(f"  turn {i+1}: first-audio {t.first_audio_ms:5.0f}ms | "
              f"full {t.full_turn_ms:5.0f}ms | \"{t.reply[:50]}\"")

    print(report.summary())


# --------------------------------------------------------------------------- #
# Audio mode (mic + speaker + barge-in) — run on the Reachy/laptop with a mic
# --------------------------------------------------------------------------- #


async def run_audio_mode(args) -> None:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        raise SystemExit(
            "audio mode needs sounddevice + numpy:  uv add sounddevice numpy\n"
            "(text mode needs neither and runs now.)"
        )

    client = AsyncOpenAI()
    sr = 24_000  # OpenAI pcm is 24kHz mono s16le

    # ---- speaker sink with barge-in cancellation ----
    cancel = asyncio.Event()

    async def sink(chunk: bytes) -> None:
        if cancel.is_set():
            raise asyncio.CancelledError
        sd.play(np.frombuffer(chunk, dtype=np.int16), sr, blocking=False)

    turn = VoiceTurn(client, args.model, args.tts_model, args.voice, sink=sink)
    report = Report()

    print("\nAudio mode. Press Enter to start each utterance, speak, Enter to stop.")
    print("During playback, start speaking to test barge-in.\n")

    for i in range(args.turns):
        input(f"[turn {i+1}] Enter, then speak…")
        rec = sd.rec(int(args.max_secs * 16_000), samplerate=16_000, channels=1, dtype="int16")
        input("  …Enter when done speaking.")
        sd.stop()
        speech_end = time.perf_counter()

        # streaming STT (single call here; swap for Realtime API for true streaming)
        import io, wave
        wav = io.BytesIO()
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16_000)
            w.writeframes(rec.tobytes())
        wav.seek(0)
        tr = await client.audio.transcriptions.create(
            model=args.stt_model, file=("u.wav", wav, "audio/wav"),
        )
        t0 = time.perf_counter()
        stt_ms = (t0 - speech_end) * 1000
        print(f"  heard: \"{tr.text}\"")

        cancel.clear()
        t = await turn.run(tr.text, t0=t0)
        t.stt_ms = stt_ms
        report.add(t)
        print(f"  first-audio {t.first_audio_ms:.0f}ms | stt {stt_ms:.0f}ms | full {t.full_turn_ms:.0f}ms")

    print(report.summary())


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 0 voice-latency spike")
    ap.add_argument("--mode", choices=["text", "audio"], default="text")
    ap.add_argument("--turns", type=int, default=5)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--model", default=DEFAULT_LLM_MODEL)
    ap.add_argument("--tts-model", default=DEFAULT_TTS_MODEL)
    ap.add_argument("--stt-model", default=DEFAULT_STT_MODEL)
    ap.add_argument("--voice", default=DEFAULT_TTS_VOICE)
    ap.add_argument("--max-secs", type=float, default=10.0, help="audio mode max record seconds")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Set OPENAI_API_KEY first.")

    runner = run_audio_mode if args.mode == "audio" else run_text_mode
    asyncio.run(runner(args))


if __name__ == "__main__":
    main()
