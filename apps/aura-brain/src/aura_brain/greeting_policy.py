"""When should the assistant greet someone? — U243.

The old rule was a cooldown: greet, then refuse for two minutes, then allow it
again. For someone who walks past, that reads as "do not greet twice". For
someone who sits in the room, it is a metronome — the robot said "Hoi hoi!
Zullen we iets leuks doen?" every two minutes, out loud, to a child who had not
gone anywhere.

The mistake is what the timer measured. A cooldown answers "how long since I
last greeted you", when the question is "have you just arrived". Those are the
same thing only if people leave.

So the rule is presence, not rate:

  * greet on ARRIVAL — the first sighting after a real absence,
  * treat a gap shorter than the absence threshold as the detector blinking,
    because faces are lost by looking away, by a dropped frame, by turning
    round; none of those are leaving the room,
  * and keep a floor cooldown as a backstop against a pathological flicker.

Pure functions on the outside, so the policy can be tested without a robot,
a camera, or two minutes of waiting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class GreetingPolicy:
    """Decides whether a recognized person should be greeted aloud.

    `absence_s` is the one that matters: how long someone must be out of sight
    before coming back counts as arriving. Ten minutes by default — long enough
    that looking away, walking behind the sofa, or a camera hiccup does not
    re-trigger it, short enough that leaving the room and returning does.
    """

    absence_s: float = field(default_factory=lambda: _env_float("GREET_ABSENCE_S", 600.0))
    min_gap_s: float = field(default_factory=lambda: _env_float("GREET_COOLDOWN_S", 120.0))
    _last_seen: dict[str, float] = field(default_factory=dict)
    _last_greeted: dict[str, float] = field(default_factory=dict)

    def should_greet(self, person_id: str, now: float) -> bool:
        """Call on EVERY recognition — it also records the sighting."""
        last_seen = self._last_seen.get(person_id)
        last_greeted = self._last_greeted.get(person_id)
        self._last_seen[person_id] = now

        # Never met in this session: they just arrived by definition.
        if last_seen is None:
            self._last_greeted[person_id] = now
            return True

        # Seen recently → they never left; the detector merely blinked.
        if now - last_seen < self.absence_s:
            return False

        # A real absence. Still respect the floor, so a camera that oscillates
        # on a long period cannot turn into a slow metronome either.
        if last_greeted is not None and now - last_greeted < self.min_gap_s:
            return False

        self._last_greeted[person_id] = now
        return True

    def seen(self, person_id: str, now: float) -> None:
        """Record a sighting without considering a greeting — for paths that
        recognize someone while greetings are suppressed (asleep, quiet mode).
        Without this, being asleep for an hour would count as an absence and the
        robot would greet the moment it woke."""
        self._last_seen[person_id] = now

    def forget(self, person_id: str) -> None:
        self._last_seen.pop(person_id, None)
        self._last_greeted.pop(person_id, None)
