# ADR-012: A line is one utterance, however many voices are in it

**Status**: **Accepted — implemented in U349** (2026-09-13).
**Date**: 2026-09-13
**Owner**: aura-brain / voice, orchestrator / presentation
**Related**: [ADR-005](ADR-005-voice-pipeline.md) (the speech paths),
[ADR-009](ADR-009-honest-state.md) (honest state),
[spec 011](../../.specify/specs/011-presentation-copilot/spec.md),
[spec 017](../../.specify/specs/017-voice-and-language/spec.md),
U153, U329, U349

---

## Context

U349 lets a scenario hand a beat to another character, and lets a *single* line
hand over mid-sentence:

```yaml
text: "Misschien. [persona:kids_companion]Of iets veel leukers![persona] De rest typ ik wel."
```

Each stretch needs its own voice and speed, so one line is now several TTS
calls. The question this ADR settles is what happens to the pieces afterwards,
because the app already has a mechanism that looks like the obvious answer.

`streaming.stream_speech` (U24/U54) splits a reply into chunks, synthesizes
chunk N+1 while chunk N plays, and sends each to `POST /robot/speak/segment`.
It exists, it is tested, and reaching for it here is the first thing anybody
would try — the pieces are already cut, they just need playing in order.

## Decision

**The segments are concatenated into one PCM buffer in the brain and sent as a
single `POST /robot/speak`.** The streaming segment path is not used for a
multi-voice line.

A short silence (120 ms) is inserted between segments so the hand-over sounds
deliberate rather than spliced. It is never added at the ends: a leading gap is
latency, a trailing one delays the next beat.

The segments are synthesized **concurrently**, not one after another, so a
three-voice line costs roughly one round-trip rather than three — a
slide-triggered beat has 500 ms to start speaking (SC-002), and a flourish must
not spend that budget.

## Why

**Loudness is decided per utterance, and a character change must not also be a
volume change.** This is the whole argument. The robot peak-normalises a
whole-utterance `speak` to 0.95; the streamed path instead takes **one gain per
utterance, decided on its first segment and never raised afterwards** (U153,
U329, FR-019) — where "an utterance" is detected as a gap in the segment
stream. Two voices sent as two `speak` calls are two separate normalisation
decisions, so the quieter of the two TTS voices would be pulled up to match the
louder one and the hand-over would land as a volume step. Sending them as
consecutive `speak/segment` calls would get the gain right, but at the cost of
everything below. Concatenating gets it right *by construction*: there is only
one utterance, so there is only one decision, and the relative loudness the TTS
produced survives.

**It adds no new brain→runtime call.** `/robot/speak` is the call this path
already makes. `/robot/speak/segment` would be a second one, on a Pi that is
older than the app — a 404 there would mean a beat that plays nothing, and the
rule for a new runtime call is its own `try` and a reported degradation, which
is a lot of machinery to buy a worse outcome.

**It keeps the behaviour engine.** `/robot/speak/segment` deliberately bypasses
it (that is correct for realtime streaming: per-segment gestures and paired
playback events would spam the console many times per reply). But a beat is one
utterance with one gesture, and routing it around the engine would cost the
`SpeechPlaybackStarted`/`Completed` pair and the speaking timeline for no gain.

**There is no latency to win here.** The path being replaced already did one
blocking synthesis of the whole line before anything played, so concurrent
synthesis of the parts is a small improvement over what was there, not a
regression against the streamed ideal. Streaming's advantage — first audio
before the whole reply exists — does not apply to a line that is already
written down in the scenario.

## What makes this safe to do

Every piece comes from the same provider, the same model and the same sample
rate — PCM s16le mono @ 24 kHz — so joining is byte concatenation, not
resampling. `voice.join_pcm_b64` decodes, joins, re-encodes, and short-circuits
a single segment to its own input untouched. If that ever stops being true (a
second TTS provider, a per-character sample rate), this decision has to be
revisited rather than patched: mixing rates in one buffer would play as noise.

## Rejected alternatives

| Alternative | Why not |
|---|---|
| `stream_speech` → `/robot/speak/segment` per voice | Gets the gain right, but adds a runtime call the Pi may not have, loses the playback events and the gesture timeline, and buys a latency benefit that a written-out line cannot use. |
| One `/robot/speak` per segment | Two normalisation decisions, so the character change is audible as a volume change (FR-019). The failure is subtle on a laptop and obvious in a room. |
| Keep the whole line in one voice; let only whole beats switch | Half the feature, and the half that was asked for second — "also in one text so it can switch to different kind of vocals". |
| SSML-style voice tags passed to the provider | gpt-4o-mini-tts takes one voice per request. There is no tag to pass. |
| Speak the markers' text as-is when a persona is unknown | A typo would be read out loud on stage. The marker is stripped, the line is spoken in the fallback voice, and the status says which persona it could not find. |

## Consequences

- A multi-voice line cannot start playing before all of its parts are
  synthesized. For a scripted beat that is the existing behaviour; for anything
  long and generated it would be the wrong trade, so improvised beats keep one
  persona for the whole line.
- One failed segment fails the whole line rather than playing the rest. This is
  deliberate: a sentence quietly missing from the middle of a talk is harder to
  notice than a beat that reports it could not speak.
- `join_pcm_b64` assumes one format. The assumption is written at its call site
  and in this file, and it is the thing to check first if a second TTS provider
  is ever added.
