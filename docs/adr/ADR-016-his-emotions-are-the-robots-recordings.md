# ADR-016: His emotions are the robot's own recordings, played by the daemon

**Status**: **Accepted — implemented in U395** (2026-10-03).
**Date**: 2026-10-03
**Owner**: robot-runtime / adapters, aura-brain / wander
**Related**: [spec 023](../../.specify/specs/023-wandering/spec.md),
[ADR-014](ADR-014-the-laptop-plays-his-voice-not-its-own.md),
[ADR-015](ADR-015-wandering-is-a-layer-not-a-setting.md), U256, U334, U393, U395

---

## Context

The owner asked for a sound level between silence and talking while he wanders
(translated): *"maybe provide variations, e.g. just a hmm or giggling — emotion
sounds, besides actually conversing"*.

Pollen publishes an emotions library for Reachy Mini
(`pollen-robotics/reachy-mini-emotions-library`): 85 recorded movements, each
with a sound recorded for it — laughing, a *hmm* and a nod, a yawn, an *oops*.
The daemon on the robot already has the library on disk and plays a recording
by name (`POST /api/move/play/recorded-move-dataset/{dataset}/{move}`): the
movement, and the sound through the robot's speaker. It answers at once with a
move id, and reports which moves are still running.

Three questions had more than one reasonable answer.

## Decision

1. **The daemon plays them, from Pollen's library.** Not the SDK's client-side
   `play_move` in the robot runtime, and not sounds synthesised on the laptop.
2. **So the sound comes from the robot, whichever speaker he talks on.** With
   *Where he speaks* set to this laptop (ADR-014), his words come from the
   laptop and his emotions from the robot.
3. **Quiet stops the emotions he starts, not the ones he answers with.** In the
   *emotions* level a reply becomes an emotion; that is answering, which Quiet
   has never touched (U256). A greeting or a sigh of his own is starting.
4. **The motion lock is held until the daemon says the move has finished.** The
   runtime answers as soon as the daemon has accepted the move and holds the
   lock — with follow-me paused — from a task that polls the running moves.
   His own voice stops a playing emotion.

## Why not the alternatives

- **Client-side `play_move`** streams every frame of the recording from the
  robot runtime to the daemon and plays the sound through the runtime's own
  media path, which is the one his speech uses. Two pipelines writing the same
  speaker is the problem U156 solved; the daemon already plays sounds next to
  speech (the wake-up chime) and does the timing between movement and sound
  itself.
- **Sounds on the laptop** would separate the giggle from the body that
  giggles. The recordings were made for those movements, and the laptop may be
  across the room.
- **Quiet silencing all emotions** would make the *emotions* level answer
  nothing at all under Quiet, while the *talk* level still answers in words: a
  quieter setting that is less responsive than a louder one.
- **Waiting inside the HTTP call** would make every caller — the reply path,
  the wander loop — wait up to twenty seconds for a movement it has no reason
  to wait for. **Not holding the lock** would let the face tracker and the
  wander loop pull the head back mid-recording. On the robot, an emotion
  played with follow-me left on made the daemon log *"IK error: collision
  detected or head pose not achievable"*; with follow-me paused it did not.

## Consequences

- Only emotions in the daemon's library exist; a name the library does not have
  is a 404, said as such.
- The library is on the robot's disk; nothing is fetched at runtime.
- An emotion cannot be heard through the laptop. That is stated in the user
  guides, not left to be discovered.
- The robot cannot know about Quiet, a talk on stage or the owner's sound
  level, so the brain tells it whether spontaneous emotions are allowed, and
  tells it again whenever any of those changes.
