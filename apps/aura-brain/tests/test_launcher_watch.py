"""U396: a brain does not outlive the app that started it.

Found while making everything work on the robot (translated: *"make sure
everything works on the robot too, and is tested"*): the robot's runtime log
showed the laptop listening and moving him all evening, while no AURA window
was open. The brain answering was started the night before. The desktop app
that started it was gone; the brain was not.

The app stops its brain on `quit` (`taskkill /T` on the tree it spawned). A
shell that never gets to `quit` — killed, crashed, or replaced by its own
updater — leaves the brain running, with no parent and no window, still
listening to the room and still driving the robot, on code from whenever it
was started. Start the app again and U234 gives the new brain the next free
port: two brains, one robot, both answering.

So the brain now watches the app: the shell passes its own pid as
`AURA_PARENT_PID`, and the brain stops itself once that process is gone. A
brain started by hand — a developer, a throwaway stack, CI — is given no pid
and is watched by nobody.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest
from aura_brain import launcher_watch


def _sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def test_a_brain_started_by_hand_is_watched_by_nobody(monkeypatch) -> None:
    monkeypatch.delenv("AURA_PARENT_PID", raising=False)
    assert launcher_watch.start_from_env() is None


@pytest.mark.parametrize("value", ["", "electron", "-4", "0"])
def test_a_pid_that_is_not_one_is_ignored(monkeypatch, value) -> None:
    monkeypatch.setenv("AURA_PARENT_PID", value)
    assert launcher_watch.start_from_env() is None


async def test_while_the_app_lives_the_brain_carries_on() -> None:
    app = _sleeper()
    gone = asyncio.Event()
    task = asyncio.ensure_future(launcher_watch.watch(app.pid, every=0.05, on_gone=gone.set))
    try:
        await asyncio.sleep(0.4)
        assert not gone.is_set()
    finally:
        task.cancel()
        app.kill()
        app.wait()


async def test_when_the_app_is_gone_the_brain_stops() -> None:
    app = _sleeper()
    gone = asyncio.Event()
    task = asyncio.ensure_future(launcher_watch.watch(app.pid, every=0.05, on_gone=gone.set))
    try:
        await asyncio.sleep(0.2)
        app.kill()
        app.wait()
        await asyncio.wait_for(gone.wait(), 5)
    finally:
        task.cancel()


async def test_an_app_that_is_already_gone_is_noticed_at_once() -> None:
    app = subprocess.Popen([sys.executable, "-c", "pass"])
    app.wait()
    gone = asyncio.Event()
    await asyncio.wait_for(launcher_watch.watch(app.pid, every=0.05, on_gone=gone.set), 5)
    assert gone.is_set()


async def test_the_brain_starts_the_watch_when_the_app_launched_it(monkeypatch, tmp_path) -> None:
    """Through the real lifespan, which is the only place it can be started."""
    started: list[int] = []

    def _start(pid=None):
        started.append(1)
        return None

    for k, v in {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "LLM_PROVIDER": "echo", "STT_PROVIDER": "null",
        "KNOWLEDGE_DB_PATH": str(tmp_path / "k.db"),
        "RECOGNITION_DB_PATH": str(tmp_path / "r.db"),
        "MODE_POLICY_PATH": str(tmp_path / "mode.json"),
        "SKILLS_DIR": str(tmp_path / "skills"),
        "CONNECTOR_PREFS_PATH": str(tmp_path / "conn.json"),
        "MCP_SERVERS_PATH": str(tmp_path / "mcp.json"),
        "AURA_ENV_FILE": str(tmp_path / "dev.env"),
        "ROBOT_AUTOFIND": "false", "ROBOT_RUNTIME_URL": "http://127.0.0.1:9",
        "VOICE_MODE": "off",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(launcher_watch, "start_from_env", _start)
    import aura_brain.main as brain_main

    monkeypatch.setattr(brain_main, "ctx", brain_main.BrainContext())
    app = brain_main.create_app()
    async with app.router.lifespan_context(app):
        pass
    assert started == [1]
