# ADR-014: The laptop plays his voice, not its own

**Status**: **Accepted — implemented in U364** (2026-10-02).
**Date**: 2026-10-02
**Owner**: aura-brain / speech_out, operator-console / playback
**Related**: [ADR-005](ADR-005-voice-pipeline.md) (the speech paths),
[ADR-009](ADR-009-honest-state.md) (honest state),
[ADR-012](ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md)
(a line is one utterance),
[spec 017](../../.specify/specs/017-voice-and-language/spec.md),
U209, U349, U364

---

## Context

Asked for as: *"can we add option that audio can go via laptop (so default
robot, but we can also choose to go via audio of laptop?"*.

Half of it already existed, and it was the wrong half. The Present panel has had
a **Laptop audio** switch since U209, and its own docstring is honest about what
it does: it hands the *text* to the browser's `speechSynthesis` and a Windows
voice reads it out.

That is a different product. It throws away the character's voice and speed
(spec 017 FR-018, spec 011 FR-107), and a line that changes persona halfway
(FR-108, [ADR-012](ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md))
cannot survive it at all — by the time the browser sees the line it is text
again and the markers are gone. ADR-012 went to some trouble to make a
multi-voice line arrive as one utterance; `speechSynthesis` un-does that in one
hop.

The brain already synthesizes the real audio before it ever reaches the robot.
So the question was never *how do we make sound on the laptop*. It was **where
that one piece of audio gets played**, and how it crosses from the brain to the
console.

## Decision

**`AUDIO_OUTPUT` chooses the speaker, never the voice.** `robot` (the default,
and what every install has had) or `laptop`; anything unrecognised is `robot`,
because a typo in an env var must never be the reason a room hears nothing.
Synthesis is unchanged and happens once either way, so the character, the speed
and a mid-line persona switch all survive.

**One place decides.** `speech_out.deliver()` is the only code that chooses; the
call sites hand it the line and the audio.

**The audio crosses as a hand-over, not a stream.** `SpeechAudioReady` carries an
**id**; the console fetches the WAV from `GET /speech/{id}.wav`. And it is
served exactly **once** — the brain 404s a line it has already handed over, and
the console keeps its own set of ids it has played.

Unfetched lines age out at a cap of eight.

## Why not the obvious alternatives

**Put the bytes on the event bus.** This is the shortest diff: the event already
exists, just give it an `audio_b64` field. It makes every subscriber pay a few
hundred kilobytes per line, it puts audio in anything that logs events, and the
console would still have to turn base64 PCM into something playable. The id is
smaller than the thing it stands for, which is the whole point of an id.

**Send raw PCM and decode it in the browser.** The robot takes PCM s16le mono at
24 kHz, so sending exactly that looks tidy. But it commits the console to the
Web Audio API — build an `AudioContext`, construct a buffer, schedule it, manage
teardown — where a 44-byte WAV header lets the same bytes become an `<audio>`
`src` the browser already knows how to play, pause and finish. The header is
written in the brain, where the sample rate is a fact rather than an assumption.

**Serve each line as often as it is asked for.** Idempotent GETs are the normal
instinct and it would make retries trivial. But a second GET for a line that
already played is not a retry — it is a replay, and the room hears the previous
sentence over the current one. During a talk that is worse than silence. Serving
once makes the failure mode *missing*, which is audible as nothing, instead of
*wrong*, which is audible as confusion.

**Keep every line until the console asks.** A console that is closed, asleep or
reloading would then catch up. But this is a hand-over between two processes on
one machine, not a store; holding every line of a 45-minute talk is how a long
session turns into a memory leak and a pile of recorded speech. Eight is enough
to cover a slow fetch and nothing like enough to be an archive.

**Reuse U209's `speechSynthesis` switch.** Covered above: it is a different
voice. It stays where it is, because it is the only option that needs no robot
at all, and that is worth keeping for a laptop-only rehearsal.

## Consequences

- A bigger room can hear him through the laptop without losing his character.
- The console must be running and connected: the event *is* the delivery, so
  with no bus `deliver()` reports **not delivered** rather than holding audio
  nobody will fetch (ADR-009 — constructing is not connecting).
- Every speaking path honours the setting — the two reply paths, the
  presentation runner, and `/robot/say`, which is what the console's quick
  actions use. A gesture sent with `/robot/say` still plays on the robot: only
  the voice moves.
- **The realtime/live path is the exception.** `voice_loop.py` streams audio
  from the provider rather than going through `voice.synthesize_b64`, so it has
  no single buffer to hand over and still speaks to the robot. Routing it is a
  different job with a different shape, and bundling it in would have been a
  second unit wearing this one's name.
- Nothing here has been verified **by ear**. The tests assert the bytes offered
  to the laptop are identical to the bytes the robot would have received, which
  is the part a test can hold; that they come out of a speaker is not.
