"""MockM365Connector — in-memory stub for dev/test without Microsoft 365 licenses."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

logger = logging.getLogger(__name__)


class MockM365Connector(M365Connector):
    """Returns realistic-looking fake data. No network calls."""

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        now = datetime.now(UTC)
        return [
            CalendarEvent(
                event_id=str(uuid.uuid4()),
                subject="Daily Standup",
                start=now.replace(hour=9, minute=0, second=0, microsecond=0),
                end=now.replace(hour=9, minute=30, second=0, microsecond=0),
                location="Teams",
                organizer="alice@contoso.com",
            ),
            CalendarEvent(
                event_id=str(uuid.uuid4()),
                subject="Sprint Review",
                start=now.replace(hour=14, minute=0, second=0, microsecond=0),
                end=now.replace(hour=15, minute=0, second=0, microsecond=0),
                location="Board Room",
                organizer="bob@contoso.com",
            ),
        ]

    async def list_onedrive_files(self) -> list[dict]:
        """Mock OneDrive listing (no Microsoft account needed)."""
        now = datetime.now(UTC)
        return [
            {"name": "Q3 Report.docx", "size_kb": 148, "modified": (now - timedelta(days=1)).isoformat(), "folder": "Documents"},
            {"name": "Roadmap.xlsx", "size_kb": 92, "modified": (now - timedelta(days=3)).isoformat(), "folder": "Documents"},
            {"name": "Team Photo.jpg", "size_kb": 2048, "modified": (now - timedelta(days=10)).isoformat(), "folder": "Pictures"},
            {"name": "Budget 2026.xlsx", "size_kb": 64, "modified": (now - timedelta(hours=6)).isoformat(), "folder": "Finance"},
        ]

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        return [
            MailItem(
                message_id=str(uuid.uuid4()),
                subject="[MOCK] Quarterly Report",
                sender="cfo@contoso.com",
                received_at=datetime.now(UTC) - timedelta(hours=1),
                body_preview="Please review the attached Q3 figures...",
                is_read=False,
            )
        ]

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        logger.info("MockM365Connector.post_teams_message channel=%r length=%d", channel, len(content))
        return TeamsMessage(
            message_id=str(uuid.uuid4()),
            channel=channel,
            content=content,
            sent_at=datetime.now(UTC),
        )

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        logger.info("MockM365Connector.send_mail to=%r subject_length=%d", to, len(subject))

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        return [
            Task(
                task_id=str(uuid.uuid4()),
                title="Review pull requests",
                is_complete=False,
                due_date=datetime.now(UTC) + timedelta(days=1),
                plan_id=plan_id,
            )
        ]

    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        from datetime import date
        parsed_due: datetime | None = None
        if due_date:
            parsed_due = datetime.fromisoformat(due_date).replace(tzinfo=UTC)
        return Task(
            task_id=str(uuid.uuid4()),
            title=title,
            is_complete=False,
            due_date=parsed_due,
            plan_id=plan_id,
        )
