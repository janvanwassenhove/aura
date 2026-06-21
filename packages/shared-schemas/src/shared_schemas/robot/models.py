"""Robot domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RobotMode(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class BehaviorState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    RESPONDING = "responding"


class RobotState(BaseModel):
    mode: RobotMode = RobotMode.OFFLINE
    behavior_state: BehaviorState = BehaviorState.IDLE
    battery_pct: float = 100.0
    connected: bool = False
    adapter_name: str = "unknown"


class MotionCue(BaseModel):
    offset_ms: int
    motion_id: str
    speed: float = 1.0
    amplitude: float = 0.5


class MotionCommand(BaseModel):
    motion_id: str
    speed: float = 1.0
    amplitude: float = 0.5
    direction: str | None = "forward"


class MotionTimeline(BaseModel):
    cues: list[MotionCue] = Field(default_factory=list)
