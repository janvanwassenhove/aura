"""M365 connector domain models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    event_id: str
    subject: str
    start: datetime
    end: datetime
    location: str = ""
    organizer: str = ""


class MailItem(BaseModel):
    message_id: str
    subject: str
    sender: str
    received_at: datetime
    body_preview: str = ""
    is_read: bool = False


class Task(BaseModel):
    task_id: str
    title: str
    is_complete: bool = False
    due_date: datetime | None = None
    plan_id: str = ""


class TeamsMessage(BaseModel):
    message_id: str
    channel: str
    team: str = ""
    content: str
    sent_at: datetime
