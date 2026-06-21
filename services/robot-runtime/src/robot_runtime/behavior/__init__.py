"""behavior package — state guards and timeline helpers."""

from robot_runtime.behavior.states import (
    VALID_TRANSITIONS,
    TransitionBlockedError,
    is_valid_transition,
)
from robot_runtime.behavior.timeline_builder import (
    create_idle_timeline,
    create_speaking_timeline,
)

__all__ = [
    "VALID_TRANSITIONS",
    "TransitionBlockedError",
    "is_valid_transition",
    "create_idle_timeline",
    "create_speaking_timeline",
]
