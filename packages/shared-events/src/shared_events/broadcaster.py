"""WebSocketBroadcaster — fans out bus events to WebSocket clients.

Not literally all of them, whatever the first line of this file used to say.
`_ALL_EVENT_TYPES` is a hand-written list, and an event that is not on it never
reaches a console however carefully the console handles it. U384 found seven
had fallen off — `SpeechAudioReady` among them, so U364's laptop audio was
synthesized, held and never played. Every exported event is now either on the
list or in `NOT_FOR_THE_CONSOLE` with the reason, and
`tests/test_broadcaster_coverage.py` fails on one that is neither.
"""

from __future__ import annotations

import logging

from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from shared_schemas.events import (
    AgentRoundCompleted,
    AgentRoundStarted,
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    AudioInputStarted,
    AuthRequiredEvent,
    BackendHeartbeatFailed,
    BackendHeartbeatOk,
    BaseEvent,
    BehaviorPlanned,
    BehaviorStateChanged,
    ComputerControlEnded,
    ComputerControlStarted,
    GestureDetected,
    IntentRecognized,
    MaintenanceReport,
    MotionCompleted,
    MotionFailed,
    MotionStarted,
    OfflineQueueSyncCompleted,
    OfflineQueueSyncStarted,
    OfflineRequestQueued,
    PersonRecognized,
    PresentationBeatFired,
    PresentationCueReceived,
    PresentationOverlayChanged,
    PresentationSubtitle,
    ReminderTriggered,
    ResponseDrafted,
    RobotConnected,
    RobotDisconnected,
    RobotModeChanged,
    SpeechAudioReady,
    SpeechAudioStopped,
    SpeechLineStarted,
    SpeechPlaybackCompleted,
    SpeechPlaybackStarted,
    ToolCallFailed,
    ToolCallRequested,
    ToolCallSucceeded,
    TranscriptUpdated,
    TurnLatencyMeasured,
    UserSpeechDetected,
)
from starlette.websockets import WebSocketDisconnect

from shared_events.bus import AsyncEventBus

logger = logging.getLogger(__name__)

_ALL_EVENT_TYPES: tuple[type[BaseEvent], ...] = (
    RobotConnected,
    RobotDisconnected,
    RobotModeChanged,
    AudioInputStarted,
    UserSpeechDetected,
    TranscriptUpdated,
    IntentRecognized,
    ResponseDrafted,
    ToolCallRequested,
    ToolCallSucceeded,
    ToolCallFailed,
    ApprovalRequested,
    ApprovalGranted,
    ApprovalDenied,
    BehaviorStateChanged,
    BehaviorPlanned,
    SpeechPlaybackStarted,
    SpeechPlaybackCompleted,
    MotionStarted,
    MotionCompleted,
    MotionFailed,
    BackendHeartbeatOk,
    BackendHeartbeatFailed,
    OfflineRequestQueued,
    OfflineQueueSyncStarted,
    OfflineQueueSyncCompleted,
    ReminderTriggered,
    PresentationBeatFired,
    PresentationCueReceived,
    TurnLatencyMeasured,
    PersonRecognized,
    GestureDetected,
    MaintenanceReport,
    # U384: U364's laptop audio. The console fetches the line it names; without
    # this it was held in the brain and nobody was ever told to fetch it.
    SpeechAudioReady,
    # U385: Stop has to reach the laptop too, or it keeps talking.
    SpeechAudioStopped,
    # U391: he is driving the owner's mouse or keyboard — the cursor ring,
    # the banner and the Stop button. Withheld until U391, so none appeared.
    ComputerControlStarted,
    ComputerControlEnded,
    # U384: U352's overlay switch. The overlay also polls every 1.5 s, which is
    # why this was never missed — but the push was designed in, and without it
    # a scenario's "hide the overlay" lands up to a second and a half late.
    PresentationOverlayChanged,
    # U400: a talk's line as he starts saying it, and the laptop saying it has
    # started one — what keeps the projector's subtitles on his voice.
    PresentationSubtitle,
    SpeechLineStarted,
)

# Exported events that deliberately do NOT go to the console, and why. A new
# event has to land in one of the two — the coverage test refuses a third
# state, because "nobody decided" is how SpeechAudioReady went missing.
NOT_FOR_THE_CONSOLE: dict[type[BaseEvent], str] = {
    AuthRequiredEvent: (
        "An orchestrator-internal signal to start a re-authentication flow. "
        "The console has no handler for it and nothing publishes it today."
    ),
    # The two below have console handlers that have never once received an
    # event: an agent-round counter on the Talk screen. Turning it on changes
    # what the screen shows, so it waits for the owner (U384). The
    # screen-control pair that sat here was turned on in U391.
    AgentRoundStarted: (
        "Pending the owner's decision (U384): would light up the Talk screen's "
        "agent-round counter, which has never run in production."
    ),
    AgentRoundCompleted: (
        "Pending the owner's decision (U384): the closing half of the "
        "agent-round counter; enabled together with AgentRoundStarted."
    ),
}


class WebSocketBroadcaster:
    """Broadcasts all AURA events to connected WebSocket clients as JSON.

    Usage (FastAPI)::

        broadcaster = WebSocketBroadcaster(bus)

        @app.websocket("/ws/events")
        async def ws_events(websocket: WebSocket):
            await broadcaster.connect(websocket)
            try:
                await websocket.receive_text()
            finally:
                broadcaster.disconnect(websocket)
    """

    def __init__(self, bus: AsyncEventBus) -> None:
        self._bus = bus
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        for event_type in _ALL_EVENT_TYPES:
            self._bus.subscribe(event_type, self._broadcast)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)
        if not self._connections:
            for event_type in _ALL_EVENT_TYPES:
                self._bus.unsubscribe(event_type, self._broadcast)

    async def broadcast_raw(self, payload: str) -> None:
        """Send a pre-serialized event JSON to all clients.

        Used by bridges that relay events from ANOTHER process's bus (e.g. the
        brain forwarding robot-runtime events to the console) without
        re-validating them against local schemas.
        """
        await self._send_all(payload)

    async def _broadcast(self, event: BaseEvent) -> None:
        await self._send_all(event.model_dump_json())

    async def _send_all(self, payload: str) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            if ws.client_state == WebSocketState.DISCONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_text(payload)
            except WebSocketDisconnect:
                dead.append(ws)
            except Exception:
                logger.exception("Error broadcasting event to WebSocket client")
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)
