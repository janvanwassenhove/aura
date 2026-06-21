"""BehaviorState transition table and guard helpers."""

from __future__ import annotations

from shared_schemas.robot.models import BehaviorState

# Valid state transitions: from_state → set of allowed next states
VALID_TRANSITIONS: dict[BehaviorState, frozenset[BehaviorState]] = {
    BehaviorState.IDLE: frozenset({
        BehaviorState.LISTENING,
        BehaviorState.SPEAKING,  # direct speak without listen (e.g. announcement)
    }),
    BehaviorState.LISTENING: frozenset({
        BehaviorState.THINKING,
        BehaviorState.IDLE,  # timeout / interrupt
    }),
    BehaviorState.THINKING: frozenset({
        BehaviorState.SPEAKING,
        BehaviorState.RESPONDING,
        BehaviorState.IDLE,  # interrupt
    }),
    BehaviorState.SPEAKING: frozenset({
        BehaviorState.RESPONDING,
        BehaviorState.IDLE,  # interrupt
    }),
    BehaviorState.RESPONDING: frozenset({
        BehaviorState.IDLE,
        BehaviorState.LISTENING,  # follow-up question
    }),
}

# Any state can always transition to IDLE (interrupt / error recovery)
_ALWAYS_ALLOWED = frozenset({BehaviorState.IDLE})


class TransitionBlockedError(Exception):
    """Raised when an invalid BehaviorState transition is attempted."""

    def __init__(self, from_state: BehaviorState, to_state: BehaviorState) -> None:
        super().__init__(f"Invalid transition: {from_state} → {to_state}")
        self.from_state = from_state
        self.to_state = to_state


def is_valid_transition(from_state: BehaviorState, to_state: BehaviorState) -> bool:
    """Return True if *from_state* → *to_state* is a permitted transition."""
    if to_state in _ALWAYS_ALLOWED:
        return True
    allowed = VALID_TRANSITIONS.get(from_state, frozenset())
    return to_state in allowed
