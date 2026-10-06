# ADR-018: He moves with the voice the room hears, wherever it comes out

**Status**: **Accepted — implemented in U407** (2026-10-06).
**Date**: 2026-10-06
**Owner**: robot-runtime / reachy adapter, aura-brain / speech_out
**Related**: [spec 016](../../.specify/specs/016-embodiment-and-presence/spec.md)
(FR-011b), [spec 011](../../.specify/specs/011-presentation-copilot/spec.md)
(FR-125), [ADR-014](ADR-014-the-laptop-plays-his-voice-not-its-own.md),
U157, U158, U364, U400, U407

---

## Context

The owner asked, of Present: *"when the robot has to say anything (following
the scenario) -> ensure while talking antenna's are moving and head moving up &
down while looking to audience (as if actually talking)"*.

He did not, on either speaker:

- **On his own speaker** a talk's line is one whole utterance. Playing it
  holds the motion lock, so no gesture can cut the line, and the U157 antenna
  loop stood down whenever the lock was held — besides only ever being started
  by the streamed path. The head had the SDK's audio-reactive sway and nothing
  else moved.
- **On the laptop** (U364, ADR-014) nothing was sent to the robot at all. At a
  talk with the PA as his speaker, the room heard him and saw a robot standing
  perfectly still.

## Decision

1. **A line he plays himself keeps his antennae moving** for as long as it
   lasts. The lock is held by his own voice, and antennae cannot cut a voice,
   so they move through it; a gesture holding the lock still keeps them out.
2. **A talk's line that the laptop plays is handed to the robot too — to move
   along with, never to play** (`POST /robot/speak/along`, the same base64 PCM).
   The brain sends it when the window playing the line reports that it has
   started (U400's start), which is when the room begins to hear it.
3. **The head nods through the daemon's speech offsets**, computed by the SDK's
   own speech tapper (`SwayRollRT`) from that audio and sent one per 50 ms hop
   for the line's length, then zeroed. The daemon composes those offsets with
   the face tracker's aim before IK — the exact channel the SDK's sway uses
   when he speaks from his own speaker. So both speakers produce the same
   motion from the same analysis, with U158's tamed yaw, and the nod is laid
   over wherever follow-me points him rather than replacing it.

## Why not the alternatives

- **A loudness envelope computed in the brain** and sent instead of the audio.
  Smaller on the wire, but it is a second analysis of speech next to the SDK's,
  and two analyses make two robots: one that nods one way from his speaker and
  another from the laptop. The audio is a few hundred kilobytes a line, already
  the size of what the robot-speaker path sends for every line.
- **Nodding with head targets** (`goto_target`). It takes the head away from the
  tracker for every nod — his eyes leave the face follow-me found, which is the
  opposite of "looking to the audience" — and it competes for the motion lock
  with the very gestures a beat asks for.
- **The SDK's `HeadWobbler`.** It schedules on a GLib main loop the runtime
  does not own. The runtime schedules the same hops itself on its own loop.
- **Starting the motion when the line is offered to the console.** That is
  before anyone hears it; the console may fetch late, or not at all. The
  window's own start is the moment, and U400 already reports it.
- **The console telling the robot.** The console never talks to the robot; the
  brain holds the robot's address and secret.

## Consequences

- A talk looks the same from either speaker: antennae going, head moving with
  the voice, still looking where follow-me points him. For eyes on the
  audience rather than the presenter, a beat says `follow_me: off` and he faces
  forward.
- Measured on the robot (wandering on, Stand): a 3 s line from the laptop
  moved his head pitch over 0.115 rad and his antennae over 0.40 rad, against
  0.001 and 0 in the 1.5 s before it. A line on his own speaker swung the
  antennae to +0.50/+0.34 rad and back while it played.
- A robot older than the app answers 404. The line plays regardless; the
  brain logs that he stands still because the robot is older, and the start
  report says so.
- **Not done here**: an ordinary reply on the laptop still does not move him —
  this unit is the talk, which is what was asked. And the persona's speaking
  gestures (`create_speaking_timeline`) still queue behind a whole line's lock
  and play after it, as they did before; they are a separate question from
  moving *while* he talks.
