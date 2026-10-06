# ADR-019: A talk's line is recorded once, and played on its cue

**Status**: **Accepted — implemented in U409** (2026-10-06); **extended in
U410**: the takes are sent to the robot ahead of their cues (see the addendum).
**Date**: 2026-10-06
**Owner**: aura-brain / recordings, presentation_api
**Related**: [spec 011](../../.specify/specs/011-presentation-copilot/spec.md)
(FR-126, FR-127), [ADR-012](ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md),
[ADR-014](ADR-014-the-laptop-plays-his-voice-not-its-own.md), U269, U349, U360, U409

---

## Context

The owner asked to direct how a line is spoken — *"powerful, short,
emotional, …"* — and reported, translated, that the same line on the same
slide *"sounds different on every run, and starts with a delay"*.

Both had one cause. Every firing synthesized the line afresh. The default TTS
model, `gpt-4o-mini-tts`, is generative: each call is a new performance, and a
direction makes that more true, not less. And the call is a network round-trip
made at the cue — on a phone hotspot at a conference, that alone is longer than
SC-002's 500 ms.

## Decision

1. **A fixed line is recorded when the talk is loaded**, in the background,
   three at a time, one take per persona stretch, and **played** on its cue.
   Improvised lines are not recorded: they do not exist until they fire.
2. **A take is known by what shapes it**: text, voice, speed, direction and TTS
   model, hashed. Same inputs, same take — across reloads, End/Run again and
   restarts. Any change is a new take; nothing has to decide when a recording
   went stale.
3. **Kept in memory and on disk**, next to the saved scenarios, the 400 most
   recently used — so a restart between rehearsal and the talk keeps the
   rehearsed take.
4. **The presenter can ask for another take** of a line, or all of them; the
   new one is kept from then on.
5. **The status is honest**: ready / total / failed per line; a failed take is
   retried at the cue and the beat still says when he was not heard (U269).

## Why not the alternatives

- **A seed or `temperature` for the TTS.** The speech endpoint has neither; a
  "deterministic" call does not exist to be made.
- **Caching at the cue only** (synthesize on first firing, then keep). The
  first run of the talk — the one that matters — still pays the round-trip and
  still gets an unrehearsed take.
- **Storing the audio in the scenario file.** The file is text the owner edits
  and shares; base64 audio makes it unreadable, and editing a line would leave
  a recording of the old one sitting next to the new words.
- **Recording at save time.** A talk can be started without being saved (the
  builder, an imported YAML), and a saved one can be edited by hand; load is the
  one moment every path passes through.
- **Rendering everything at once.** Forty lines would open forty connections on
  a hotspot and starve the very cue that comes first.

## Consequences

- A rehearsed talk sounds the same on stage, and a line plays on its cue
  without the TTS service in the loop — a slide cue's delay is now the robot's
  playback, plus moving the audio to it when it is the speaker.
- Starting a talk costs one TTS call per line once; restarting or running it
  again costs nothing until something changes.
- Changing `TTS_MODEL` re-records everything on the next start. Takes on disk
  that no talk uses any more are dropped only by age.
- Moving a take to the robot still happens at the cue when the robot is the
  speaker; on a slow link that transfer is what is left (a separate step:
  sending takes to the robot ahead).

## Addendum — U410: the robot holds the takes

Asked (translated): *"can we add preloading to decrease delay/latency of e.g.
wifi hotspot?"* — the consequence this ADR left open. With the robot as the
speaker each line still crossed the Wi-Fi at its cue.

**Decision.** Once a line is recorded, the brain sends it to the robot in the
background (one at a time, only what he lacks), and the cue names it.

- **Named by its audio**, a hash of the joined line. A name from the takes'
  inputs was the first version, and it let a re-recorded take — same words,
  voice and direction — keep the old take's name, so the robot would have
  played the take the presenter had just replaced.
- **Only to a robot that has said it keeps takes.** An older runtime ignores
  `take` and answers a speak with no audio by playing nothing and saying ok —
  the exact silence U269 was about. A 404 on `held` marks him older for good.
- **A 409 is answered in the same cue**: the line goes with its audio and is
  sent again for next time. The room never waits for the fallback to be
  decided elsewhere.

**Rejected**: compressing the audio (Opus) instead — smaller at the cue, still
at the cue, and a decoder on the Pi in the playback path; streaming the line
to the robot as it plays — the round-trip is the cost, not the bandwidth alone;
the robot synthesizing — it holds no keys and must not.

