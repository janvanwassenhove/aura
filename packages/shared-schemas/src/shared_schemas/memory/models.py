"""Memory store domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Turn(BaseModel):
    turn_id: UUID = Field(default_factory=uuid4)
    session_id: str
    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Todo(BaseModel):
    todo_id: UUID = Field(default_factory=uuid4)
    text: str
    done: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Reminder(BaseModel):
    reminder_id: UUID = Field(default_factory=uuid4)
    text: str
    due_at: datetime
    fired: bool = False
