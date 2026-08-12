"""U243: greet people when they arrive, not every two minutes while they sit there.

The reported symptom: "Hoi hoi! Zullen we iets leuks doen?" spoken aloud five
times in nine minutes, at 120s, 146s, 121s and 166s apart — the floor being
exactly GREET_COOLDOWN_S. Nobody had gone anywhere; the face detector kept
losing and re-finding the same child, and a cooldown answers the wrong
question.
"""

from __future__ import annotations

from aura_brain.greeting_policy import GreetingPolicy

MINUTE = 60.0


def policy(**kw) -> GreetingPolicy:
    return GreetingPolicy(absence_s=10 * MINUTE, min_gap_s=2 * MINUTE, **kw)


def test_greets_someone_it_has_not_seen() -> None:
    p = policy()
    assert p.should_greet("mila", 0.0) is True


def test_does_not_greet_again_while_they_are_still_there() -> None:
    """The actual bug. Recognition fires repeatedly — the detector blinks — and
    none of it means anyone arrived."""
    p = policy()
    assert p.should_greet("mila", 0.0) is True

    # nine minutes of being in the room, re-detected every ~30 seconds
    greetings = sum(p.should_greet("mila", t) for t in range(30, 9 * 60, 30))
    assert greetings == 0, "sitting in the room is not arriving"


def test_the_old_cooldown_pattern_would_have_greeted_five_times() -> None:
    """Pin the difference. At the reported cadence the old rule fired every
    time the cooldown expired; the new one fires once."""
    p = policy()
    reported = [0, 120, 266, 387, 553]  # the timestamps from the screenshot
    fired = [t for t in reported if p.should_greet("mila", float(t))]
    assert fired == [0], f"expected one greeting, got {len(fired)}"


def test_greets_again_after_a_real_absence() -> None:
    p = policy()
    assert p.should_greet("mila", 0.0) is True
    assert p.should_greet("mila", 60.0) is False          # still around
    assert p.should_greet("mila", 60.0 + 11 * MINUTE) is True, "came back after leaving"


def test_a_gap_just_under_the_threshold_is_the_detector_blinking() -> None:
    p = policy()
    p.should_greet("mila", 0.0)
    assert p.should_greet("mila", 9 * MINUTE) is False
    # and that sighting refreshes presence, so the clock runs from the last look
    assert p.should_greet("mila", 9 * MINUTE + 9 * MINUTE) is False


def test_people_are_tracked_separately() -> None:
    p = policy()
    assert p.should_greet("mila", 0.0) is True
    assert p.should_greet("noor", 5.0) is True, "a second person still gets a hello"
    assert p.should_greet("mila", 10.0) is False


def test_sightings_while_suppressed_do_not_count_as_absence() -> None:
    """Asleep, or in a quiet persona: the robot still SEES you. Without this,
    an hour of silence would look like an hour of absence and it would greet
    the moment greetings came back on — the same bug wearing a hat."""
    p = policy()
    assert p.should_greet("mila", 0.0) is True
    for t in range(60, 60 * 60, 60):
        p.seen("mila", float(t))
    assert p.should_greet("mila", 60 * 60 + 1) is False


def test_a_floor_still_applies_to_pathological_flicker() -> None:
    """A camera that oscillates on a period longer than the absence threshold
    must not become a slow metronome either."""
    p = GreetingPolicy(absence_s=1.0, min_gap_s=5 * MINUTE)
    assert p.should_greet("mila", 0.0) is True
    assert p.should_greet("mila", 2.0) is False, "absence satisfied, but the floor holds"
    assert p.should_greet("mila", 6 * MINUTE) is True


def test_forget_resets_someone() -> None:
    p = policy()
    assert p.should_greet("guest-1", 0.0) is True
    p.forget("guest-1")
    assert p.should_greet("guest-1", 1.0) is True
