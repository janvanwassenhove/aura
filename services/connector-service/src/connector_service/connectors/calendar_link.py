"""U298: a calendar connected by pasting its sharing link.

Asked as "app-ids is enige manier? er niks gebruiksvriendelijker?". The answer
for the calendar half is yes: Outlook, Google and Apple all publish a private
.ics subscription URL. Paste it and he can read today's agenda — no Azure app,
no consent screen, no sign-in, and nothing that can be revoked by an admin
somewhere.

Deliberately read-only. It cannot send mail, post to Teams or create a task,
and says so plainly instead of failing at the moment somebody counts on it.
The full account is still the better connector; this is the one that works in
thirty seconds.

The URL is a secret in the sense that anyone holding it can read the calendar,
so it lives in the settings store with the other configuration and is never
logged — only its host is, when a fetch fails.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from urllib.parse import urlsplit

import httpx
from shared_config import ConnectorServiceSettings
from shared_schemas.m365.connector import M365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage

from connector_service.connectors.errors import ConnectorUnavailableError
from connector_service.ics import events_on

logger = logging.getLogger(__name__)

#: A feed of a busy shared calendar is a few hundred kB; well past that it is
#: not a calendar, and reading it would stall the answer.
_MAX_BYTES = 8 * 1024 * 1024
_TIMEOUT = 10.0


def normalise(url: str) -> str:
    """`webcal://` is the same feed over https — that is what the OS handler
    does, and pasting the link Outlook shows should just work."""
    url = url.strip()
    if url.lower().startswith("webcal://"):
        return "https://" + url[len("webcal://"):]
    return url


class CalendarLinkConnector(M365Connector):
    """Today's agenda, read from a published iCalendar feed."""

    def __init__(
        self,
        settings: ConnectorServiceSettings,
        url: str = "",
        timezone: str = "",
        today: date | None = None,
    ) -> None:
        self._url = normalise(url or getattr(settings, "calendar_ics_url", ""))
        self._timezone = timezone or getattr(settings, "calendar_timezone", "")
        self._today = today   # tests pin the day; production asks the clock

    @property
    def _host(self) -> str:
        """The bit of the URL that is safe to put in a log line."""
        return urlsplit(self._url).netloc or "the calendar link"

    async def _fetch(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT,
                                         follow_redirects=True) as client:
                resp = await client.get(self._url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            # Never the URL itself: it is the whole credential.
            logger.warning("calendar feed at %s could not be read: %s",
                           self._host, type(exc).__name__)
            raise ConnectorUnavailableError(
                f"The calendar link at {self._host} did not answer. "
                "If it was regenerated, paste the new one in Settings."
            ) from exc
        if len(resp.content) > _MAX_BYTES:
            raise ConnectorUnavailableError(
                f"The calendar at {self._host} is too large to read.")
        return resp.text

    async def list_calendar_events_today(self) -> list[CalendarEvent]:
        if not self._url:
            raise ConnectorUnavailableError("No calendar link has been pasted yet.")
        day = self._today or datetime.now().astimezone().date()
        return [
            CalendarEvent(
                event_id=occ.uid,
                subject=occ.summary,
                start=occ.start,
                end=occ.end,
                location=occ.location,
                organizer=occ.organizer,
            )
            for occ in events_on(await self._fetch(), day, self._timezone)
        ]

    # ------------------------------------------------------------------
    # M365Connector ABC — a link is read-only, and says so
    # ------------------------------------------------------------------

    _READ_ONLY = ("A shared calendar link can only read the calendar. "
                  "Connect the account itself for {what}.")

    async def get_unread_mail(self, limit: int = 10) -> list[MailItem]:
        raise ConnectorUnavailableError(self._READ_ONLY.format(what="mail"))

    async def send_mail(self, to: str, subject: str, body: str) -> None:
        raise ConnectorUnavailableError(self._READ_ONLY.format(what="sending mail"))

    async def post_teams_message(self, channel: str, content: str) -> TeamsMessage:
        raise ConnectorUnavailableError(self._READ_ONLY.format(what="chat"))

    async def list_tasks(self, plan_id: str = "") -> list[Task]:
        raise ConnectorUnavailableError(self._READ_ONLY.format(what="tasks"))

    async def create_task(self, title: str, plan_id: str = "",
                          due_date: str = "") -> Task:
        raise ConnectorUnavailableError(self._READ_ONLY.format(what="tasks"))
