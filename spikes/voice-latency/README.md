# Phase 0 Spike — Voice Latency De-risk

**Throwaway spike.** Goal: produce *measured* first-word-out and full-turn latency
for the streaming voice path, to make the Phase 0 go/no-go decision in
[`docs/reshape-plan.md`](../../docs/reshape-plan.md) **before** investing in the
restructure. Honest numbers > clean code.

## What it measures

The optimized streaming path we want to ship: stream the LLM token-by-token and
start TTS on the **first clause** (don't wait for the full answer), streaming TTS
audio out as it's produced.

```
submit ─► LLM (stream) ─► first clause ─► TTS (stream) ─► first audio byte
                                                          └► "FIRST AUDIO OUT"  ◄ headline
```

- **First audio out** (submit → first TTS byte) = how long until AURA starts
  talking. **Target from the plan: < ~700 ms.**
- Full per-stage breakdown: LLM first token, first clause, LLM completion, full
  turn.

## Run

```bash
cd spikes/voice-latency

# text mode — NO hardware, runnable on the laptop right now
uv run --no-project --with "openai>=1.40" python harness.py --mode text --turns 6

# single prompt
uv run --no-project --with "openai>=1.40" python harness.py --mode text --prompt "What meetings do I have today?"

# audio mode — mic + speaker + barge-in (run on the Reachy/laptop with a mic)
uv add sounddevice numpy
uv run python harness.py --mode audio --turns 5
```

Needs `OPENAI_API_KEY` in the environment.

## Baseline results (2026-06-21, dev laptop, chained streaming)

`--mode text`, `gpt-4o-mini` + `gpt-4o-mini-tts`, n=6, over the dev laptop's
internet link:

| Stage | median | p95 |
|---|---|---|
| LLM first token | 498 ms | 574 ms |
| First clause ready | 583 ms | 640 ms |
| **► First audio out** | **1397 ms** | **2083 ms** |
| LLM full completion | 721 ms | 815 ms |
| Full turn (last audio) | 3301 ms | 3666 ms |

### Interpretation

- **The LLM is not the bottleneck.** First clause is ready in ~580 ms; the model
  streams fast enough to start speaking early.
- **TTS first-byte is the bottleneck.** The ~800 ms gap between *first clause
  ready* (583 ms) and *first audio out* (1397 ms) is almost entirely
  `gpt-4o-mini-tts` time-to-first-audio.
- **Verdict for the chained path: MARGINAL → NO-GO** against the 700 ms target.
  Chaining a text LLM to a separate TTS service structurally pays the TTS
  first-byte penalty on every turn.

## Realtime API results (2026-06-21, dev laptop, speech-to-speech) — GO ✅

`--mode text --engine realtime`, `gpt-realtime` GA model, n=5, same network:

| Stage | median | p95 |
|---|---|---|
| First token (transcript) | 423 ms | 472 ms |
| **► First audio out** | **556 ms** | **598 ms** |
| Full turn (last audio) | 1689 ms | 1793 ms |

### Head-to-head

| Path | First audio (median) | Full turn | Verdict |
|---|---|---|---|
| Chained (LLM → separate TTS) | ~1065 ms | ~3.1 s | ⚠️ marginal |
| **Realtime (speech-to-speech)** | **556 ms** | **~1.7 s** | **✅ GO (< 700 ms)** |

The Realtime API nearly **halves** first-audio and full-turn latency by emitting
audio directly — it removes the ~800 ms TTS-first-byte hop the chained breakdown
exposed. **This is the Phase 0 go/no-go answer: GO, on the speech-to-speech
transport.**

### What this means for the build (feeds Phase 1 + 3.5)

1. **Adopt the OpenAI Realtime API as the default voice transport** in
   `conversation-runtime` (the constitution already names it; the *current code*
   doesn't implement it — it uses batch `whisper-1`/`tts-1`). Realtime does
   STT + reasoning + TTS in one hop and supports **barge-in** and **function
   calling** natively, which also collapses the "two sequential LLM calls"
   problem in the orchestrator.
2. Keep **streaming-local** (Whisper + Piper/Kokoro) behind the same provider ABC
   as the **offline** tier — measure it on the Pi with `--engine chained` +
   local models so the offline fallback has known numbers.
3. Add the **mic→Pi→laptop** legs (`--mode audio`) and re-measure on the real
   **Reachy Mini Wireless** over the LAN before locking the budget — network adds
   to every number above. The cloud Realtime number must be re-confirmed
   on-device.

## Caveats

- Numbers are from one dev laptop's network; absolute values will differ on your
  setup. The **breakdown** (LLM cheap, TTS expensive) is the durable signal.
- Audio-mode STT here is a single transcription call (buffered), not yet true
  streaming STT — swap in the Realtime API for the real streaming-STT number.
- This is a spike: no error handling, no tests, not wired to anything. Delete
  after the go/no-go decision is recorded.
