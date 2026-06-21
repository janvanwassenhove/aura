"""Gateway models — GatewayCommand, AuditEntry, WebhookRegistration."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl


class GatewayAction(StrEnum):
    SPEAK = "speak"
    MOTION = "motion"
    SEND_MAIL = "send_mail"
    POST_TEAMS = "post_teams_message"
    LIST_TASKS = "list_tasks"
    CREATE_TASK = "create_task"


SENSITIVE_ACTIONS: frozenset[GatewayAction] = frozenset(
    {
        GatewayAction.SEND_MAIL,
        GatewayAction.POST_TEAMS,
        GatewayAction.CREATE_TASK,
    }
)


class CommandPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class GatewayCommand(BaseModel):
    """An inbound command from an external agent."""

    action: GatewayAction
    payload: dict = Field(default_factory=dict)
    priority: CommandPriority = CommandPriority.NORMAL
    # api_key_id and received_at are set by the gateway, not the caller
    api_key_id: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommandStatus(StrEnum):
    RECEIVED = "received"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"
    QUEUED = "queued"


class AuditEntry(BaseModel):
    """Audit log record for a gateway command.

    SECURITY: payload content MUST NOT be stored here — only metadata.
    """

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: str
    key_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: CommandStatus = CommandStatus.RECEIVED
    mode_at_time: str = ""
    is_sensitive: bool = False


class WebhookRegistration(BaseModel):
    """A registered external callback URL."""

    webhook_id: str = Field(default_factory=lambda: str(uuid4()))
    url: str  # validated as str; HttpUrl coercion causes issues in tests
    events: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    failure_count: int = 0
