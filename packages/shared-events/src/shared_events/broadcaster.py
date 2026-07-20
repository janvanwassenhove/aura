"""WebSocketBroadcaster — fans out all bus events to WebSocket clients."""

from __future__ import annotations

import logging

from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from shared_schemas.events import (
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    AudioInputStarted,
    BackendHeartbeatFailed,
    BackendHeartbeatOk,
    BaseEvent,
    BehaviorPlanned,
    BehaviorStateChanged,
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
    PresentationCueReceived,
    ReminderTriggered,
    ResponseDrafted,
    RobotConnected,
    RobotDisconnected,
    RobotModeChanged,
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
    PresentationCueReceived,
    TurnLatencyMeasured,
    PersonRecognized,
    GestureDetected,
    MaintenanceReport,
)


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
