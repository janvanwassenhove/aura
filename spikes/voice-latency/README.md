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

### What this tells us to do next (feeds Phase 3.5)

1. **Measure the OpenAI Realtime API (speech-to-speech).** It is designed to
   eliminate exactly this text-LLM→TTS hop by emitting audio directly — the most
   likely way to get first-audio under target. This is the next experiment.
2. **Compare a lower-first-byte TTS** (local Piper/Kokoro on the laptop, or a
   streaming TTS with faster TTFB) behind the same harness.
3. Then add the **mic→Pi→laptop** legs (`--mode audio`) and re-measure on the
   real **Reachy Mini Wireless** over the LAN — network adds to every number
   above, so the cloud-vs-local decision must be made on *on-device* numbers.

## Caveats

- Numbers are from one dev laptop's network; absolute values will differ on your
  setup. The **breakdown** (LLM cheap, TTS expensive) is the durable signal.
- Audio-mode STT here is a single transcription call (buffered), not yet true
  streaming STT — swap in the Realtime API for the real streaming-STT number.
- This is a spike: no error handling, no tests, not wired to anything. Delete
  after the go/no-go decision is recorded.
