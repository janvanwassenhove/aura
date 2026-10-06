"""Timeline builder — creates MotionTimeline from text and persona config."""

from __future__ import annotations

import random

from shared_personas.models import GestureProfile, PersonaConfig
from shared_schemas.robot.models import MotionCue, MotionTimeline

#: U408: a gesture starts at least this long before the line ends, so it
#: finishes inside the sentence it belongs to.
GESTURE_MARGIN_MS = 600
#: U408: words a second, for a line that reaches the robot as audio only.
WORDS_PER_S = 2.5


def create_speaking_timeline(text: str, persona_config: PersonaConfig,
                             duration_ms: int | None = None) -> MotionTimeline:
    """Build the gestures that go with saying *text*.

    - The line's length is `duration_ms` when it is known — the audio's — and
      otherwise estimated at 250 ms a word. A line with no words (one the
      laptop plays reaches the robot as audio only) counts 2.5 words a second.
    - At most ``max(1, words // 8)`` cues, never closer than ``inter_cue_ms``.
    - Spread over the line: each cue lands in the middle of its share of it,
      and none starts later than ``GESTURE_MARGIN_MS`` before its end.
    - Each cue's ``offset_ms`` is its wait from the cue before it, which is
      what ``MotionCue`` promises (U408). This used to write times from the
      start of the line, which the engine then waited one after another, so
      the cues ran later and later — and, queued behind his voice, after it.
    - Empty for a persona with no gestures (``silent_desk``).
    """
    profile: GestureProfile = persona_config.gesture_profile
    if not profile.motion_ids:
        return MotionTimeline(cues=[])

    words = len(text.split())
    if duration_ms is not None and duration_ms > 0:
        total_ms = int(duration_ms)
        if not words:
            words = round(total_ms / 1000 * WORDS_PER_S)
    else:
        total_ms = max(1, words) * 250
    words = max(1, words)
    usable = max(0, total_ms - GESTURE_MARGIN_MS)
    count = max(1, words // 8)
    if profile.inter_cue_ms > 0:
        count = min(count, max(1, usable // profile.inter_cue_ms))
    share = usable / count

    cues: list[MotionCue] = []
    previous = 0
    for i in range(count):
        at = int(share * i + share * random.uniform(0.25, 0.75)) if usable else 0
        at = max(previous, min(at, usable))
        cues.append(
            MotionCue(
                offset_ms=at - previous,
                motion_id=random.choice(profile.motion_ids),
                speed=0.5,
                amplitude=profile.amplitude,
            )
        )
        previous = at

    return MotionTimeline(cues=cues)


def create_idle_timeline(persona_config: PersonaConfig) -> MotionTimeline:
    """Build a subdued idle-fidget timeline (2 gentle cues).

    Returns an empty timeline for ``silent_desk`` persona.
    """
    profile: GestureProfile = persona_config.gesture_profile
    if not profile.motion_ids:
        return MotionTimeline(cues=[])

    amplitude = profile.amplitude * 0.3
    # Curiosity: about a third of idle moments the robot looks around the room
    # instead of fidgeting in place (U36d).
    if random.random() < 0.35:
        return MotionTimeline(cues=[
            MotionCue(offset_ms=0, motion_id="look_around", speed=0.3, amplitude=amplitude),
        ])
    motion_id = random.choice(profile.motion_ids)
    cues = [
        MotionCue(offset_ms=0, motion_id=motion_id, speed=0.3, amplitude=amplitude),
        MotionCue(offset_ms=1500, motion_id=motion_id, speed=0.3, amplitude=amplitude),
    ]
    return MotionTimeline(cues=cues)
