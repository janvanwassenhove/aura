"""M365 package exports."""

from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

__all__ = ["M365Connector", "CalendarEvent", "MailItem", "Task", "TeamsMessage"]
