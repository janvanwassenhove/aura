"""U393: the wander planner — what he does when nobody asked him for anything.

Asked for as (translated): *"can we add a 'wandering' mode — the robot wanders
around, following people, moving the antennas, moving towards sound or
people"*. Reachy Mini does not drive, so wandering is done where he stands:
he looks around by himself, follows the people he sees, and turns towards
voices.

The planner is pure — no hardware, no clock, no randomness of its own — so
every rule below is tested without a robot. The adapter asks it each tick and
carries the answer out.
"""

from __future__ import annotations

import math
import random

from robot_runtime.wander import (
    BODY_YAW_MAX,
    HEAD_YAW_MAX,
    WanderPlanner,
    doa_to_yaw,
    split_yaw,
)

LEFT, FRONT, RIGHT = 0.0, math.pi / 2, math.pi


def _planner(seed: int = 7) -> WanderPlanner:
    return WanderPlanner(random.Random(seed))


# --- the microphone array's angle ------------------------------------------

def test_a_voice_on_the_left_turns_him_left_and_on_the_right_right() -> None:
    assert doa_to_yaw(LEFT) > 0          # positive yaw = turn left
    assert doa_to_yaw(RIGHT) < 0


def test_straight_ahead_is_not_a_reason_to_turn() -> None:
    """The array reports front and back as the same angle, so a voice there is
    either in front of him already or behind him, where he cannot know."""
    assert doa_to_yaw(FRONT) is None
    assert doa_to_yaw(FRONT + 0.2) is None


def test_a_wide_turn_is_shared_between_head_and_body() -> None:
    head, body = split_yaw(1.4)
    assert abs(head) <= HEAD_YAW_MAX
    assert body is not None and abs(body) <= BODY_YAW_MAX
    head, body = split_yaw(0.3)
    assert body is None, "a small turn is the head's alone"


# --- what he does ------------------------------------------------------------

def test_someone_speaking_beside_him_makes_him_turn_to_them() -> None:
    p = _planner()
    act = p.decide(100.0, face_visible=False, doa=(LEFT, True))
    assert act is not None and act.reason == "sound"
    assert act.head_yaw > 0


def test_a_noise_that_is_not_speech_does_not_turn_him() -> None:
    p = _planner()
    act = p.decide(100.0, face_visible=False, doa=(LEFT, False))
    assert act is None or act.reason != "sound"


def test_he_does_not_jerk_from_voice_to_voice() -> None:
    p = _planner()
    assert p.decide(100.0, face_visible=False, doa=(LEFT, True)).reason == "sound"
    again = p.decide(101.0, face_visible=False, doa=(RIGHT, True))
    assert again is None or again.reason != "sound"


def test_with_someone_in_view_he_keeps_looking_at_them() -> None:
    """The face tracker has the head; a glance away, or a turn to a voice
    elsewhere, would look like losing interest in the person in front of him."""
    p = _planner()
    for t in range(0, 120, 2):
        act = p.decide(float(t), face_visible=True, doa=(LEFT, True))
        assert act is None or act.head_yaw is None, f"looked away at t={t}"


def test_with_nobody_around_he_looks_around_now_and_then() -> None:
    p = _planner()
    glances = [p.decide(float(t), face_visible=False, doa=None) for t in range(0, 120)]
    looks = [a for a in glances if a is not None and a.reason == "look-around"]
    assert 4 <= len(looks) <= 25, f"{len(looks)} glances in two minutes"
    assert all(abs(a.head_yaw) <= HEAD_YAW_MAX for a in looks)


def test_his_antennas_move_too() -> None:
    p = _planner()
    acts = [p.decide(float(t), face_visible=t % 40 < 20, doa=None) for t in range(0, 180)]
    assert any(a is not None and a.antennas != (0.0, 0.0) for a in acts)


def test_now_and_then_the_whole_body_turns() -> None:
    p = _planner()
    acts = [p.decide(float(t), face_visible=False, doa=None) for t in range(0, 600)]
    assert any(a is not None and a.body_yaw is not None for a in acts)


def test_the_same_seed_plans_the_same_wander() -> None:
    a = [_planner(3).decide(float(t), face_visible=False, doa=None) for t in range(60)]
    b = [_planner(3).decide(float(t), face_visible=False, doa=None) for t in range(60)]
    assert a == b
