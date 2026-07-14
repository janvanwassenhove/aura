"""Orchestrator tool call and approval events."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from shared_schemas.events.base import BaseEvent

_MAX_RESULT_LEN = 500


class ToolCallRequested(BaseEvent):
    event_type: Literal["ToolCallRequested"] = "ToolCallRequested"
    tool_name: str
    approval_id: UUID | None = None


class ToolCallSucceeded(BaseEvent):
    event_type: Literal["ToolCallSucceeded"] = "ToolCallSucceeded"
    tool_name: str
    result_summary: Annotated[str, Field(max_length=_MAX_RESULT_LEN)] = ""

    @field_validator("result_summary", mode="before")
    @classmethod
    def truncate_result(cls, v: str) -> str:
        if isinstance(v, str) and len(v) > _MAX_RESULT_LEN:
            return v[:_MAX_RESULT_LEN]
        return v


class ToolCallFailed(BaseEvent):
    event_type: Literal["ToolCallFailed"] = "ToolCallFailed"
    tool_name: str
    error_code: str


class ApprovalRequested(BaseEvent):
    event_type: Literal["ApprovalRequested"] = "ApprovalRequested"
    approval_id: UUID
    tool_name: str
    arguments_summary: str = ""


class ApprovalGranted(BaseEvent):
    event_type: Literal["ApprovalGranted"] = "ApprovalGranted"
    approval_id: UUID
    tool_name: str = ""


class ApprovalDenied(BaseEvent):
    event_type: Literal["ApprovalDenied"] = "ApprovalDenied"
    approval_id: UUID
    tool_name: str = ""


class AuthRequiredEvent(BaseEvent):
    """Emitted when a connector token cannot be silently refreshed.

    The orchestrator listens for this event and initiates a Device Code /
    OAuth re-authentication flow for the affected user and provider.
    """

    event_type: Literal["AuthRequired"] = "AuthRequired"
    user_id: str
    provider: str  # e.g. "m365", "google", "github"
    reason: str = ""  # e.g. "refresh_token_expired"


class AgentRoundStarted(BaseEvent):
    """U57: one reasoning round of the agentic loop began."""

    event_type: Literal["AgentRoundStarted"] = "AgentRoundStarted"
    round_no: int
    max_rounds: int


class AgentRoundCompleted(BaseEvent):
    """U57: a round finished — which tools ran and whether the loop is done."""

    event_type: Literal["AgentRoundCompleted"] = "AgentRoundCompleted"
    round_no: int
    tool_names: list[str] = []
    done: bool = False
