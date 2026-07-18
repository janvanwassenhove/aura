# Voice latency baseline (voice-brief Phase 0)

> Instrument before you change anything (brief §3). This file records the
> **measured** p50/p95 per stage so later phases prove improvement instead of
> asserting it. It is populated from real turns, not estimates.

## How the numbers are produced

Every confirmed voice turn emits one `TurnTrace` (`aura_brain/turn_trace.py`)
with monotonic timestamps at each stage. Traces are:

- kept in a ring (last 50) and appended as JSON lines to `TURN_TRACE_PATH`
  (default `data/turn_traces.jsonl`);
- exposed at **`GET /voice/turn-traces?n=20`** — last N turns slowest-first,
  with mouth-to-ear p50/p95.

**Mouth-to-ear** = `playback_first_sample − endpoint_fired`.

### Honest caveat about the current stack

The pipeline records **fixed-length windows** (`capture_audio(duration_s)`,
`reachy.py:448`), so there is no true VAD endpoint. Therefore:

- `capture_start` is `window_end − window_length` (approximate, not a VAD frame);
- `capture_end == endpoint_fired` (the window simply closing is treated as the
  endpoint);
- `endpoint_wait` is effectively 0 here — but the *fixed window itself* adds a
  flat `window_length` of dead time to every turn, which the mouth-to-ear number
  does **not** capture because "the user stopped speaking" is unknown. This is
  exactly the endpointing debt Phase 2 pays down, and it is called out so the
  baseline isn't read as rosier than reality.

## Baseline table — FILL FROM ~30 REAL TURNS

Run ~30 unscripted turns on the robot, then read `GET /voice/turn-traces?n=30`
(or aggregate `data/turn_traces.jsonl`) and paste the medians here.

| Stage segment            | p50 (ms) | p95 (ms) | Notes |
|--------------------------|---------:|---------:|-------|
| capture (fixed window)   |    _TBD_ |    _TBD_ | ≈ VOICE_WINDOW_S; flat tax, pre-endpoint |
| stt (endpoint→final)     |    _TBD_ |    _TBD_ | network Whisper round-trip |
| llm (request→final)      |    _TBD_ |    _TBD_ | non-streaming today |
| tts (request→first audio)|    _TBD_ |    _TBD_ | non-streaming: == full synthesis |
| playback_start           |    _TBD_ |    _TBD_ | first audio → first sample |
| **mouth-to-ear (p50)**   |    _TBD_ |        — | target ≤600, ceiling 1000 |
| **mouth-to-ear (p95)**   |        — |    _TBD_ | target ≤1200, ceiling 2000 |

## Expected finding (to CONFIRM before Phase 1, per §3)

> 60–80% of the total sits in **endpoint wait** and **time-to-first-audio**.

On this stack that maps to: the **fixed capture window** (dead time before we
even start) plus **non-streaming STT→LLM→TTS** (each stage waits for the full
previous artefact). Confirm with the table above before optimising.

_Populated: PENDING a live 30-turn run on the Pi._
