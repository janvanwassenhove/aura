---
feature: "017-voice-and-language"
---

# Implementation Plan: Voice and Language

**Prerequisites**: `spec.md`. Retro-written from the code.

## The three paths, and why all three exist

```
                      ┌──────────────── pipeline (voice.py, voice_loop.py)
wake word (local) ────┼──────────────── per-turn realtime (realtime_voice.py)
                      └──────────────── realtime session (realtime_session.py)
                                          (server VAD, continuous)
```

* **Pipeline** is the only path that can call tools, so anything that needs the
  calendar, a skill or the screen goes through it. It is also the cheap one.
* **Per-turn realtime** buys speech-to-speech quality for a single answer, with
  the expensive session opened only after the wake word fires (U129).
* **Session** is the fluid one — you talk, it answers, no wake word per turn —
  and it cannot call tools. That is the trade the owner is choosing between in
  Settings (U132, U203).

**This diagram is the point of the whole spec.** Four language bugs in a row
(U287, U289, U291, U292) were each a correct fix applied to one path while the
others kept the old behaviour. A change here is not done until it is done in
all three, or until the unit says out loud which path it is scoped to.

## Decisions

### Pin the language; do not detect it

U287. Auto-detection cost more than it bought: half-heard Dutch became German,
then Asian scripts, and the model answered confidently in whatever it had
decided. `_stt_language()` resolves one language and passes it to the model;
`_wrong_script()` throws away anything that comes back in a script the
household does not use. `multi` remains for households that genuinely mix
languages inside one sentence — the opt-out is explicit, so nobody gets it by
accident.

### The person in front of the camera outranks the household default

U288. A house is rarely monolingual. U274 already lets the owner say which
language each person is met in; until U288 that only shaped the *reply* while
the microphone kept listening in the language of the house. It is narrowed only
when the room agrees on one language — two recognised people with different
languages fall back to the household default rather than picking a winner.

### The language rule is appended, never composed in

U291. A persona prompt replaced the entire instruction string, taking the
language rule with it. Composition by replacement is fragile in a system where
personas, characters and per-person notes all contribute; `build_instructions()`
therefore **appends** the rule last, unconditionally, and a test fails if a
persona can remove it.

### Never describe machinery to a model that only hears

U292, and the most expensive lesson in this spec. My U291 text mentioned
fetching a transcript. The model, which hears audio directly and has no such
step, took the description as something it was supposed to be doing, and the
apology I had written for it — *"één momentje, ik haal de transcriptie op"* —
was a ready-made sentence to say while doing it. It said it about twenty times.

Two rules, in code comments and in tests: describe nothing the model cannot
reach, and never hand it a sentence it can hide behind.

### Local wake word, with a fallback that cannot break the loop

U128. Transcribing every audio window over the network to hear a name is slow,
unreliable (Whisper drops short names) and costs a round-trip per window.
openWakeWord runs on the CPU. When the package or model is missing,
`build_detector()` returns `None` and the loop keeps the old path — the
fallback is a returned `None`, never an exception, because an exception here
takes the microphone down.

### Realtime degrades, loudly

U133, U141, U142, U143. A hung Realtime call is indistinguishable from a broken
robot, so: a timeout, a circuit breaker that falls back to the pipeline, a
self-check the owner can run, and candidate-model detection for when the model
name goes stale. Every failure names its reason.

## Verification

Always with the keys unset:

```
OPENAI_API_KEY= ANTHROPIC_API_KEY= uv run --package aura-brain --extra dev pytest
```

U283: three tests depended on `OPENAI_API_KEY` being present in a developer
shell. CI has no keys, so it was red for six hours while the local run was
green.

## Files

| Path | Role |
|---|---|
| `apps/aura-brain/src/aura_brain/voice.py` | STT/TTS, language resolution, script guard |
| `apps/aura-brain/src/aura_brain/voice_loop.py` | The pipeline loop |
| `apps/aura-brain/src/aura_brain/realtime_voice.py` | Per-turn realtime |
| `apps/aura-brain/src/aura_brain/realtime_session.py` | Continuous session, server VAD |
| `apps/aura-brain/src/aura_brain/voice_context.py` | Instruction assembly + the language rule |
| `apps/aura-brain/src/aura_brain/wakeword.py` | Local detection, with a silent fallback |
| `apps/aura-brain/src/aura_brain/voice_api.py` | Routes the console uses |
