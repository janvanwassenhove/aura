"""M365Connector abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage


class M365Connector(ABC):
    """Contract for Microsoft 365 connectors.

    Implementations: MockM365Connector, WorkIQConnector.

    SECURITY: Auth tokens must NEVER appear in any log output.
    The WorkIQConnector passes tokens via httpx.AsyncClient(headers=...) only.
    """

    @abstractmethod
    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        """Return today's calendar events."""

    @abstractmethod
    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        """Return the most recent unread mail items."""

    @abstractmethod
    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        """Post a message to a Teams channel."""

    @abstractmethod
    async def send_mail(self, to: str, subject: str, body: str) -> None:
        """Send an email. 'to' is a single recipient address."""

    @abstractmethod
    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        """List tasks, optionally filtered by plan."""

    @abstractmethod
    async def create_task(self, title: str, plan_id: str = "", due_date: str = "") -> Task:
        """Create a new task. due_date must be an ISO-8601 date string or empty."""
