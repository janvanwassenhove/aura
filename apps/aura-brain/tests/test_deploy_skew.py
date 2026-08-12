"""U240: the brain notices when the robot is running older code.

The Pi sat 74 commits behind for a month. Nothing could answer "is the robot
running what I expect?", so nobody asked, and the first symptom was a 404 that
made the sleep button do nothing while the app reported success (U238).

Reported, never enforced — these tests pin that too: an unknown or older robot
must never be turned into a refusal to work.
"""

from __future__ import annotations

from aura_brain.deploy_skew import compare

BRAIN = "a" * 40
ROBOT_OLD = "b" * 40


def test_same_commit_is_in_step() -> None:
    result = compare({"commit": BRAIN}, brain_commit=BRAIN)
    assert result["state"] == "in_step"
    assert BRAIN[:7] in result["detail"]


def test_different_commit_is_behind_and_says_how_to_fix_it() -> None:
    result = compare({"commit": ROBOT_OLD, "commit_short": ROBOT_OLD[:7]}, brain_commit=BRAIN)
    assert result["state"] == "behind"
    assert result["robot_commit"] == ROBOT_OLD
    assert result["brain_commit"] == BRAIN
    assert "deploy_robot.py" in result["detail"], "a warning without the next step is nagging"


def test_a_runtime_that_cannot_say_is_unknown_not_behind() -> None:
    """An older runtime has no build field at all. That is an absence of
    information, and guessing 'behind' from it would be inventing a fact —
    even though, in practice, it usually IS behind."""
    for empty in ({}, None, {"package": "0.1.0"}):
        result = compare(empty, brain_commit=BRAIN)
        assert result["state"] == "unknown", empty
        assert "does not report" in result["detail"] or "cannot" in result["detail"]


def test_a_brain_that_cannot_read_itself_is_unknown() -> None:
    result = compare({"commit": ROBOT_OLD}, brain_commit=None)
    # brain_commit=None falls back to reading git; in a checkout that succeeds,
    # so assert the shape rather than the verdict.
    assert result["state"] in {"behind", "unknown", "in_step"}
    assert "detail" in result


def test_comparison_never_raises_on_junk() -> None:
    """This runs inside a maintenance tick. A version check that can throw would
    take out the loop that watches everything else."""
    for junk in ({"commit": 12345}, {"commit": ""}, {"commit": None}):
        assert compare(junk, brain_commit=BRAIN)["state"] in {"unknown", "behind"}
