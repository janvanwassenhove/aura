"""U298: the calendar you connect by pasting a link.

The point of this connector is that it asks nothing of the owner beyond one
URL, so the things worth pinning are the promises that make that safe: it is
read-only, it never puts the link (which IS the credential) in a log or an
error, and a feed that has gone stale says so in a sentence a person can act
on instead of failing somewhere deep in a turn.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from connector_service.connectors.calendar_link import CalendarLinkConnector, normalise
from connector_service.connectors.errors import ConnectorUnavailableError
from shared_config import ConnectorServiceSettings

FEED = (
    "BEGIN:VCALENDAR\nVERSION:2.0\n"
    "BEGIN:VEVENT\nUID:1\nSUMMARY:Piano lesson\nLOCATION:Music school\n"
    "DTSTART:20260904T170000\nDTEND:20260904T180000\nEND:VEVENT\n"
    "END:VCALENDAR\n"
)
DAY = date(2026, 9, 4)


def _connector(monkeypatch, handler) -> CalendarLinkConnector:
    """A connector whose HTTP goes to `handler` instead of the network."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    return CalendarLinkConnector(
        settings=ConnectorServiceSettings(),
        url="https://outlook.office365.com/owa/calendar/secret/reachcalendar.ics",
        today=DAY,
    )


async def test_it_reads_todays_agenda_from_the_feed(monkeypatch) -> None:
    conn = _connector(monkeypatch, lambda r: httpx.Response(200, text=FEED))
    (event,) = await conn.list_calendar_events_today()
    assert event.subject == "Piano lesson"
    assert event.location == "Music school"
    assert event.start.hour == 17


async def test_webcal_links_work_because_that_is_what_outlook_shows() -> None:
    assert normalise("webcal://example.com/a.ics") == "https://example.com/a.ics"
    assert normalise("  https://example.com/a.ics ") == "https://example.com/a.ics"


async def test_a_dead_link_says_what_to_do_about_it(monkeypatch) -> None:
    conn = _connector(monkeypatch, lambda r: httpx.Response(404))
    with pytest.raises(ConnectorUnavailableError) as err:
        await conn.list_calendar_events_today()
    assert "paste the new one" in str(err.value).lower()


async def test_the_link_itself_never_appears_in_an_error(monkeypatch) -> None:
    """Anyone holding this URL can read the calendar, so it is a credential —
    and an error message is the easiest place for one to end up in a log."""
    conn = _connector(monkeypatch, lambda r: httpx.Response(500))
    with pytest.raises(ConnectorUnavailableError) as err:
        await conn.list_calendar_events_today()
    assert "secret" not in str(err.value)
    assert "reachcalendar.ics" not in str(err.value)
    assert "outlook.office365.com" in str(err.value), "the host is fine, and helps"


async def test_nothing_pasted_yet_is_not_a_crash() -> None:
    conn = CalendarLinkConnector(settings=ConnectorServiceSettings(), url="")
    with pytest.raises(ConnectorUnavailableError) as err:
        await conn.list_calendar_events_today()
    assert "no calendar link" in str(err.value).lower()


async def test_it_refuses_the_things_a_link_cannot_do(monkeypatch) -> None:
    """A shared link is read-only. Saying that plainly is what keeps him from
    promising to send a mail he has no way of sending."""
    conn = _connector(monkeypatch, lambda r: httpx.Response(200, text=FEED))
    for call in (
        conn.get_unread_mail(),
        conn.send_mail("a@b.c", "hi", "hello"),
        conn.post_teams_message("general", "hi"),
        conn.list_tasks(),
        conn.create_task("something"),
    ):
        with pytest.raises(ConnectorUnavailableError) as err:
            await call
        assert "only read the calendar" in str(err.value)


async def test_an_empty_day_is_an_empty_list(monkeypatch) -> None:
    conn = _connector(monkeypatch, lambda r: httpx.Response(
        200, text="BEGIN:VCALENDAR\nEND:VCALENDAR\n"))
    assert await conn.list_calendar_events_today() == []
