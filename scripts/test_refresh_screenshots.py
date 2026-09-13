"""U330: the screenshot stack must be unable to read anything real.

The pictures in the README are only publishable because the stack behind them
holds one fictional profile and nothing else. That property lives in a handful
of environment variables, and every one of them defaults to `./data` — a real
knowledge store on the machine of whoever runs this. So it is checked here
rather than remembered.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from refresh_screenshots import (  # noqa: E402
    OWNER_STATE,
    REPO,
    check_isolated,
    demo_env,
    free_port,
)


def test_every_owner_path_lands_in_the_throwaway_directory(tmp_path) -> None:
    env = demo_env(tmp_path, brain_port=1, robot_port=2)
    for key in OWNER_STATE:
        # A database URL spells its path with forward slashes even on Windows,
        # so compare the way a path compares, not the way a string does.
        value = env[key].replace("\\", "/")
        assert tmp_path.as_posix() in value, \
            f"{key} escaped the throwaway directory: {value}"


def test_the_run_refuses_when_a_path_points_into_the_repository(tmp_path) -> None:
    """The failure this prevents: `./data` in a developer's checkout is a real
    store, and a screenshot of it is a published family."""
    env = demo_env(tmp_path, brain_port=1, robot_port=2)
    assert check_isolated(env) == []

    env["KNOWLEDGE_DB_PATH"] = str(REPO / "data" / "knowledge.enc.json")
    offenders = check_isolated(env)
    assert any("KNOWLEDGE_DB_PATH" in o for o in offenders), offenders


def test_an_unset_path_is_an_offender_too(tmp_path) -> None:
    """Unset does not mean harmless — it means the default, which is ./data."""
    env = demo_env(tmp_path, brain_port=1, robot_port=2)
    env["MODE_POLICY_PATH"] = ""
    assert any("MODE_POLICY_PATH" in o for o in check_isolated(env))


def test_the_stack_has_no_keys_and_no_senses(tmp_path) -> None:
    """No model to call, no camera, no microphone, and nothing that speaks on
    its own initiative in the middle of a capture."""
    env = demo_env(tmp_path, brain_port=1, robot_port=2)
    assert env["LLM_PROVIDER"] == "echo"
    assert env["OPENAI_API_KEY"] == "" and env["ANTHROPIC_API_KEY"] == ""
    assert env["RECOGNITION_ENABLED"] == "false"
    assert env["GESTURES_ENABLED"] == "false"
    assert env["VOICE_MODE"] == "off"
    assert env["PROACTIVE_ENABLED"] == "false"
    assert env["DEMO_PERSONA"] == "true"


def test_ports_are_taken_free_rather_than_assumed() -> None:
    """8020 is the brain the owner is using while this runs; a demo stack that
    assumed it would either fail to bind or, far worse, be captured."""
    ports = {free_port() for _ in range(5)}
    assert all(1024 < p < 65536 for p in ports)
    assert 8020 not in ports or len(ports) > 1   # never a fixed, well-known port
