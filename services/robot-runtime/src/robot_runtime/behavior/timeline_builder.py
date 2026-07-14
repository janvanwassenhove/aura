"""Timeline builder — creates MotionTimeline from text and persona config."""

from __future__ import annotations

import random

from shared_personas.models import GestureProfile, PersonaConfig
from shared_schemas.robot.models import MotionCue, MotionTimeline


def create_speaking_timeline(text: str, persona_config: PersonaConfig) -> MotionTimeline:
    """Build a motion timeline synchronised to the speech duration of *text*.

    Algorithm:
    - Estimate duration as ``word_count * 250 ms`` (≈240 wpm reading pace).
    - Place cues every ``inter_cue_ms ± 100 ms`` until duration is covered.
    - Cap at ``max(1, word_count // 8)`` cues to avoid over-gesturing.
    - Returns an empty timeline for ``silent_desk`` persona (no motion_ids).
    """
    profile: GestureProfile = persona_config.gesture_profile
    if not profile.motion_ids:
        return MotionTimeline(cues=[])

    word_count = max(1, len(text.split()))
    total_ms = word_count * 250
    max_cues = max(1, word_count // 8)

    cues: list[MotionCue] = []
    offset_ms = 0
    while offset_ms < total_ms and len(cues) < max_cues:
        motion_id = random.choice(profile.motion_ids)
        cues.append(
            MotionCue(
                offset_ms=offset_ms,
                motion_id=motion_id,
                speed=0.5,
                amplitude=profile.amplitude,
            )
        )
        offset_ms += profile.inter_cue_ms + random.randint(0, 100)

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
