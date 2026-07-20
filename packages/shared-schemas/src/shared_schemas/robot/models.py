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
    tracking: bool = False  # U126: follow-me head tracking currently active?
    # U165: is the daemon's face tracker actually SEEING someone right now?
    # "Follow is on" and "it has a face to follow" are different things, and
    # only the second explains why the head is or isn't moving. None = unknown
    # (adapter can't report it).
    face_visible: bool | None = None


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
    # U137: a MANUAL motion (quick action from the panel) pauses follow-me so
    # the move is fully visible; reply gestures keep tracking for eye contact.
    manual: bool = False


class MotionTimeline(BaseModel):
    cues: list[MotionCue] = Field(default_factory=list)
