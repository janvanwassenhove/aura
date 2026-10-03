"""U391: when he drives the screen, the owner can see it — and stop it.

Agreed after U384 found it, in the owner's words (translated): *"OK for this
safety one."*

U75 built the warning: a glowing ring around the cursor, a banner saying
"AURA controls the screen — press Esc to abort", and a *Stop screen control*
button on the Talk screen. All three are switched on by `ComputerControlStarted`
and off by `ComputerControlEnded`. The pipeline published both; the broadcaster
never forwarded them, so none of it ever appeared — he could move the mouse
with nothing on screen saying so and no button to stop him.

Two more gaps came with turning it on:

- the U378 desktop rung types and presses shortcuts in the owner's apps and
  announced nothing at all;
- the overlay captures **Esc system-wide** while it is up. One missed "Ended"
  — a dropped WebSocket, a reloaded console — would leave it stealing Esc,
  which ends a PowerPoint slideshow. So the state is also kept in one place in
  the brain and can be ASKED for, and the console clears a stale overlay
  against it (CLAUDE.md: state that must survive a missed event is polled).
"""

from __future__ import annotations

import asyncio
import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import desktop as _desktop  # noqa: E402
from orchestrator import mode_policy  # noqa: E402
from orchestrator.approval_manager import ApprovalManager  # noqa: E402
from orchestrator.context_builder import ContextBuilder  # noqa: E402
from orchestrator.intent_router import IntentRouter  # noqa: E402
from orchestrator.persona_manager import PersonaManager  # noqa: E402
from orchestrator.pipeline import OrchestratorPipeline  # noqa: E402
from shared_events.bus import AsyncEventBus  # noqa: E402
from shared_schemas.events.orchestrator import (  # noqa: E402
    ComputerControlEnded,
    ComputerControlStarted,
)


@pytest.fixture
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture(autouse=True)
def _no_gate(monkeypatch):
    """The approval gate is not what is under test here."""
    monkeypatch.setattr(mode_policy, "requires_approval", lambda *a, **k: False)


def _pipeline(bus) -> OrchestratorPipeline:
    return OrchestratorPipeline(bus, IntentRouter(mode="work"),
                                ApprovalManager(bus, session_id="t"),
                                ContextBuilder(), PersonaManager())


def _record(bus) -> list[str]:
    seen: list[str] = []

    async def started(e):
        seen.append(f"started:{e.goal}")

    async def ended(e):
        seen.append("ended")

    bus.subscribe(ComputerControlStarted, started)
    bus.subscribe(ComputerControlEnded, ended)
    return seen


async def _call(p: OrchestratorPipeline, tool: str, args: dict) -> None:
    import json

    await p._run_tool_round(
        [{"id": "c1", "name": tool, "arguments": json.dumps(args)}], "s", {"tool_ms": 0.0})
    await asyncio.sleep(0.05)              # bus handlers run as tasks


class _ComputerUse:
    def __init__(self, pipeline, *, crash: bool = False) -> None:
        self.pipeline = pipeline
        self.crash = crash
        self.active_while_running: bool | None = None

    async def run(self, goal, session_id):
        self.active_while_running = self.pipeline.screen_control_status()["active"]
        if self.crash:
            raise RuntimeError("vision model fell over")
        return "opened the mail"


async def test_using_the_computer_is_announced_and_can_be_asked_about(bus) -> None:
    p = _pipeline(bus)
    seen = _record(bus)
    p._computer_use = agent = _ComputerUse(p)

    await _call(p, "use_computer", {"goal": "open the mail"})

    assert seen == ["started:open the mail", "ended"]
    assert agent.active_while_running is True
    assert p.screen_control_status()["active"] is False


async def test_the_end_is_announced_even_when_the_run_crashes(bus) -> None:
    """A banner that stays up after a crash keeps Esc captured."""
    p = _pipeline(bus)
    seen = _record(bus)
    p._computer_use = _ComputerUse(p, crash=True)

    # The crash itself still propagates, as it always did; what matters here
    # is that the warning comes down on the way out.
    with pytest.raises(RuntimeError):
        await _call(p, "use_computer", {"goal": "open the mail"})
    await asyncio.sleep(0.05)

    assert seen[-1] == "ended"
    assert p.screen_control_status()["active"] is False


@pytest.mark.parametrize("tool", ["send_keys", "type_into"])
async def test_typing_in_the_owners_apps_is_announced(bus, monkeypatch, tool) -> None:
    p = _pipeline(bus)
    seen = _record(bus)
    during: list[bool] = []

    async def fake(arguments):
        during.append(p.screen_control_status()["active"])
        return "done"

    monkeypatch.setitem(_desktop.DESKTOP_TOOLS, tool, fake)
    await _call(p, tool, {"app": "Outlook", "keys": "ctrl+n", "text": "hi"})

    assert len(seen) == 2 and seen[0].startswith("started:") and "Outlook" in seen[0]
    assert seen[1] == "ended"
    assert during == [True]


@pytest.mark.parametrize("tool", ["find_app", "list_windows"])
async def test_looking_is_not_driving(bus, monkeypatch, tool) -> None:
    """A banner on every read-only lookup would teach the owner to ignore it."""
    p = _pipeline(bus)
    seen = _record(bus)

    async def fake(arguments):
        return "[]"

    monkeypatch.setitem(_desktop.DESKTOP_TOOLS, tool, fake)
    await _call(p, tool, {"name": "x"})
    assert seen == []


async def test_the_state_can_be_asked_for_over_http(bus) -> None:
    from orchestrator import routes

    p = _pipeline(bus)
    routes._pipeline = p
    try:
        body = (await routes.computeruse_status()).body
        assert b'"active":false' in body
    finally:
        routes._pipeline = None
