"""U384: an event the console listens for has to actually reach it.

Reported as: "activated, but speaks via robot" — Settings said *this laptop*,
and the laptop stayed silent.

The brain half of U364 worked: it synthesized the line, held it, and logged
`speech routed to the laptop`. Then nothing fetched it. `SpeechAudioReady` was
added to `shared_schemas.events` and handled in the console, and never added to
the broadcaster — which does not send "all published events", as spec 003
FR-005 says it does, but a hand-written tuple. Seven events had fallen off that
tuple, and nothing noticed, because every test on either side used a fake bus.

These tests hold the rule the spec states: every exported event is either
broadcast, or excluded on purpose with a reason written down.
"""

from __future__ import annotations

import asyncio
import inspect
import json

import shared_schemas.events as events
from shared_events.broadcaster import _ALL_EVENT_TYPES, NOT_FOR_THE_CONSOLE, WebSocketBroadcaster
from shared_events.bus import AsyncEventBus
from shared_schemas.events.audio import SpeechAudioReady
from shared_schemas.events.base import BaseEvent
from starlette.websockets import WebSocketState


def _exported() -> set[type[BaseEvent]]:
    return {
        c for c in vars(events).values()
        if inspect.isclass(c) and issubclass(c, BaseEvent) and c is not BaseEvent
    }


def test_every_event_is_broadcast_or_excluded_on_purpose() -> None:
    """The rule that would have caught U364: a new event cannot be forgotten,
    only deliberately left out."""
    unclassified = sorted(
        c.__name__ for c in _exported()
        - set(_ALL_EVENT_TYPES) - set(NOT_FOR_THE_CONSOLE)
    )
    assert not unclassified, (
        f"{unclassified} reach no console and nobody decided that. Add each to "
        "_ALL_EVENT_TYPES, or to NOT_FOR_THE_CONSOLE with the reason."
    )


def test_an_event_is_not_both_sent_and_excluded() -> None:
    assert not set(_ALL_EVENT_TYPES) & set(NOT_FOR_THE_CONSOLE)


def test_every_exclusion_says_why() -> None:
    for event_type, why in NOT_FOR_THE_CONSOLE.items():
        assert len(why.strip()) > 30, f"{event_type.__name__}: a reason, not a shrug"


class _Socket:
    """Enough of a WebSocket for the broadcaster: it accepts and it records."""

    client_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_text(self, payload: str) -> None:
        self.sent.append(json.loads(payload))


async def test_the_laptop_is_told_there_is_a_line_to_play() -> None:
    """End to end through the real bus and the real broadcaster: the event the
    brain publishes when the owner chose the laptop arrives at a console."""
    bus = AsyncEventBus()
    await bus.start()
    console = _Socket()
    await WebSocketBroadcaster(bus).connect(console)

    await bus.publish(SpeechAudioReady(
        session_id="default", utterance_id="abc123", text="Goedemorgen."))
    for _ in range(20):                      # handlers run as tasks; let them
        if console.sent:
            break
        await asyncio.sleep(0.01)

    assert [e["event_type"] for e in console.sent] == ["SpeechAudioReady"]
    assert console.sent[0]["utterance_id"] == "abc123"


def test_the_screen_control_warning_reaches_the_console() -> None:
    """U391: the cursor ring, the banner and the Stop button are switched by
    these two. Withheld, he could drive the mouse with nothing on screen."""
    from shared_schemas.events.orchestrator import ComputerControlEnded, ComputerControlStarted

    assert ComputerControlStarted in _ALL_EVENT_TYPES
    assert ComputerControlEnded in _ALL_EVENT_TYPES

