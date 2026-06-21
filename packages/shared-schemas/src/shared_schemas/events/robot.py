"""Robot lifecycle events."""

from __future__ import annotations

from typing import Literal

from shared_schemas.events.base import BaseEvent
from shared_schemas.robot.models import RobotMode


class RobotConnected(BaseEvent):
    event_type: Literal["RobotConnected"] = "RobotConnected"
    session_id: str = ""
    adapter_name: str


class RobotDisconnected(BaseEvent):
    event_type: Literal["RobotDisconnected"] = "RobotDisconnected"
    session_id: str = ""
    reason: str = "graceful"


class RobotModeChanged(BaseEvent):
    event_type: Literal["RobotModeChanged"] = "RobotModeChanged"
    session_id: str = ""
    from_mode: RobotMode
    to_mode: RobotMode
