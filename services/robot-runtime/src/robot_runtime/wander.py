"""U393: the wander rung — what he does when nobody asked him for anything.

Asked for as (translated): *"can we add a 'wandering' mode — the robot wanders
around, following people, moving the antennas, moving towards sound or
people"*. Reachy Mini does not drive, so he wanders where he stands: he looks
around by himself, follows the people he sees (the daemon's face tracker does
that part), turns towards voices, and moves his antennas.

This module only DECIDES. It holds no hardware, reads no clock and owns no
randomness — the adapter passes `now`, what the camera and the microphone
array report, and a seeded `random.Random` — so every rule is testable
without a robot. The adapter asks it each tick and carries the answer out.

The microphone array (the daemon's `GET /api/state/doa`) reports an angle in
radians — 0 is left, π/2 is straight ahead, π is right — and whether it is
speech. It cannot tell front from back: both read as π/2. So a voice near π/2
is never a reason to turn; it is either in front of him already, or behind
him, where he cannot know.

U395 adds emotion sounds, when the brain allows them: Pollen's emotions
library, a recorded movement with its own sound. He makes one of his own
accord only now and then — greeting someone who arrives, a sigh after a long
while alone — and only short ones, because a fifteen-second yawn at a
visitor is not a greeting.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

FRONT = math.pi / 2
FRONT_DEADZONE = 0.35        # rad either side of straight ahead: no turn
HEAD_YAW_MAX = 0.70          # rad, ±40° — what the neck turns on its own
HEAD_PITCH_MAX = 0.18        # rad — glances stay roughly level
BODY_YAW_MAX = 1.20          # rad, ±69° — the same bound the joystick uses

# U395: emotions, by name in Pollen's library (seconds measured on the robot).
GREETINGS = ("welcoming1", "inquiring2", "cheerful1")    # 3.5, 2.6, 2.8 s
ALONE = ("indifferent1", "tired1")                       # 2.6, 7.4 s
GREET_AFTER_S = 20.0         # out of view this long, and coming back is arriving
ALONE_AFTER_S = 300.0        # no face, no voice this long: a sigh
EMOTION_GAP_S = 45.0         # never two emotions closer than this


@dataclass(frozen=True)
class Look:
    """One thing to do. `head_yaw` None leaves the head to the face tracker;
    `body_yaw` None leaves the torso where it is."""

    head_yaw: float | None
    head_pitch: float
    body_yaw: float | None
    antennas: tuple[float, float]
    reason: str                  # "sound" | "look-around" | "antennas" | "greet" | "alone"
    emotion: str | None = None   # U395: play this instead of moving


def doa_to_yaw(angle: float) -> float | None:
    """The array's angle as a turn (positive = left), or None when the sound
    is straight ahead or straight behind."""
    yaw = FRONT - angle
    if abs(yaw) < FRONT_DEADZONE:
        return None
    return max(-math.pi / 2, min(math.pi / 2, yaw))


def split_yaw(yaw: float) -> tuple[float, float | None]:
    """A turn shared between neck and torso: the head takes up to its own
    range, and only what is left over moves the body."""
    if abs(yaw) <= HEAD_YAW_MAX:
        return yaw, None
    head = math.copysign(HEAD_YAW_MAX, yaw)
    body = max(-BODY_YAW_MAX, min(BODY_YAW_MAX, yaw - head + math.copysign(0.25, yaw)))
    return head, body


class WanderPlanner:
    """Decides, tick by tick, what wandering looks like.

    - someone in view: the face tracker has the head; only the antennas move,
      now and then, so he looks interested rather than frozen;
    - a voice from one side: turn towards it — at most once every few seconds,
      so two people talking do not make him jerk between them;
    - nobody, no voice: a glance somewhere every so often, and now and then the
      whole body turns, so the camera covers the room and the face tracker can
      find someone new.
    """

    def __init__(self, rng: random.Random | None = None, *,
                 glance_every: tuple[float, float] = (6.0, 14.0),
                 body_every: tuple[float, float] = (30.0, 70.0),
                 antennas_every: tuple[float, float] = (8.0, 16.0),
                 sound_cooldown_s: float = 4.0) -> None:
        self._rng = rng or random.Random()
        self._glance_every = glance_every
        self._body_every = body_every
        self._antennas_every = antennas_every
        self._sound_cooldown_s = sound_cooldown_s
        self._next_glance: float | None = None
        self._next_body: float | None = None
        self._next_antennas: float | None = None
        self._last_sound_turn = -1e9
        # U395: when a face was last seen, when he last had company of any
        # kind, and when he last made an emotion.
        self._last_face: float | None = None
        self._company_at: float | None = None
        self._last_emotion = -1e9

    def _after(self, now: float, span: tuple[float, float]) -> float:
        return now + self._rng.uniform(*span)

    def _antenna_pose(self) -> tuple[float, float]:
        a = self._rng.uniform(-0.6, 0.6)
        return (round(a, 3), round(-a * self._rng.uniform(0.4, 1.0), 3))

    def _emote(self, now: float, names: tuple[str, ...], reason: str) -> Look:
        self._last_emotion = now
        return Look(None, 0.0, None, (0.0, 0.0), reason, self._rng.choice(names))

    def decide(self, now: float, *, face_visible: bool,
               doa: tuple[float, bool] | None, emotions: bool = False) -> Look | None:
        if self._next_glance is None:
            self._next_glance = self._after(now, (1.0, 4.0))
            self._next_body = self._after(now, self._body_every)
            self._next_antennas = self._after(now, self._antennas_every)
            # Whoever is there when he starts has not arrived; they were here.
            self._last_face = self._company_at = now

        # U395: arriving is a face after a while without one — not a face
        # that looked away for a moment.
        arriving = face_visible and now - self._last_face >= GREET_AFTER_S
        if face_visible:
            self._last_face = self._company_at = now
        if doa is not None and doa[1]:
            self._company_at = now
        may_emote = emotions and now - self._last_emotion >= EMOTION_GAP_S

        if face_visible:
            if arriving and may_emote:
                return self._emote(now, GREETINGS, "greet")
            # Keep looking at them; postpone the look-around until they leave.
            self._next_glance = max(self._next_glance, self._after(now, (3.0, 6.0)))
            if now >= self._next_antennas:
                self._next_antennas = self._after(now, self._antennas_every)
                return Look(None, 0.0, None, self._antenna_pose(), "antennas")
            return None

        if doa is not None:
            angle, speech = doa
            yaw = doa_to_yaw(angle) if speech else None
            if yaw is not None and now - self._last_sound_turn >= self._sound_cooldown_s:
                self._last_sound_turn = now
                head, body = split_yaw(yaw)
                # Give the face tracker a moment to find whoever spoke.
                self._next_glance = self._after(now, (4.0, 8.0))
                return Look(round(head, 3), 0.05, None if body is None else round(body, 3),
                            self._antenna_pose(), "sound")

        if may_emote and now - self._company_at >= ALONE_AFTER_S:
            self._company_at = now
            return self._emote(now, ALONE, "alone")

        if now >= self._next_glance:
            self._next_glance = self._after(now, self._glance_every)
            body: float | None = None
            if now >= self._next_body:
                self._next_body = self._after(now, self._body_every)
                body = round(self._rng.uniform(-0.8, 0.8), 3)
            return Look(round(self._rng.uniform(-0.6, 0.6), 3),
                        round(self._rng.uniform(-HEAD_PITCH_MAX, HEAD_PITCH_MAX * 0.6), 3),
                        body, self._antenna_pose(), "look-around")

        if now >= self._next_antennas:
            self._next_antennas = self._after(now, self._antennas_every)
            return Look(None, 0.0, None, self._antenna_pose(), "antennas")
        return None
