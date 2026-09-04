"""U298: the iCalendar parser behind "connect a calendar with a link".

Every case here came from a real subscription feed's habits: Outlook writes
TZID zones, Google writes UTC with a Z, all-day events use an exclusive DTEND
that puts a one-day event on two days if you believe it, and a household
calendar is mostly recurring events — which is exactly the part a naive parser
gets wrong and still looks like it works.
"""

from __future__ import annotations

from datetime import date

from connector_service.ics import events_on, unfold


def _cal(*events: str) -> str:
    body = "\n".join(events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{body}\nEND:VCALENDAR\n"


def _event(**props: str) -> str:
    lines = "\n".join(f"{k.replace('_', '-')}:{v}" for k, v in props.items())
    return f"BEGIN:VEVENT\n{lines}\nEND:VEVENT"


DAY = date(2026, 9, 4)


def test_a_plain_timed_event_on_the_day() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Standup", LOCATION="Kitchen",
                      DTSTART="20260904T090000", DTEND="20260904T091500"))
    (event,) = events_on(cal, DAY)
    assert event.summary == "Standup"
    assert event.location == "Kitchen"
    assert event.start.hour == 9
    assert event.end.minute == 15


def test_another_day_is_not_today() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Nope", DTSTART="20260905T090000",
                      DTEND="20260905T091500"))
    assert events_on(cal, DAY) == []


def test_utc_is_converted_to_the_household_zone() -> None:
    """Google writes 07:00Z; in Brussels that is 09:00, and the answer a
    person hears has to be the one on their own clock."""
    cal = _cal(_event(UID="1", SUMMARY="Standup",
                      DTSTART="20260904T070000Z", DTEND="20260904T071500Z"))
    (event,) = events_on(cal, DAY, timezone="Europe/Brussels")
    assert event.start.hour == 9


def test_a_tzid_from_outlook_is_honoured() -> None:
    cal = _cal("BEGIN:VEVENT\nUID:1\nSUMMARY:Call\n"
               "DTSTART;TZID=Europe/Brussels:20260904T140000\n"
               "DTEND;TZID=Europe/Brussels:20260904T150000\nEND:VEVENT")
    (event,) = events_on(cal, DAY, timezone="Europe/Brussels")
    assert event.start.hour == 14


def test_an_all_day_event_lands_on_one_day_not_two() -> None:
    """DTEND is EXCLUSIVE. Believing it puts every all-day event on the day
    after as well — the single most common way to be wrong about a feed."""
    cal = _cal("BEGIN:VEVENT\nUID:1\nSUMMARY:Holiday\n"
               "DTSTART;VALUE=DATE:20260904\nDTEND;VALUE=DATE:20260905\nEND:VEVENT")
    assert [e.summary for e in events_on(cal, DAY)] == ["Holiday"]
    assert events_on(cal, date(2026, 9, 5)) == []
    assert events_on(cal, DAY)[0].all_day is True


def test_a_multi_day_event_shows_on_every_day_it_covers() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Conference",
                      DTSTART="20260903T090000", DTEND="20260905T170000"))
    for day in (date(2026, 9, 3), DAY, date(2026, 9, 5)):
        assert [e.summary for e in events_on(cal, day)] == ["Conference"], day
    assert events_on(cal, date(2026, 9, 6)) == []


def test_a_weekly_event_from_last_year_still_shows_today() -> None:
    """A household calendar is mostly this, and a parser that ignores RRULE
    answers "nothing today" every week with total confidence."""
    cal = _cal(_event(UID="1", SUMMARY="Piano", DTSTART="20250905T170000",
                      DTEND="20250905T180000", RRULE="FREQ=WEEKLY"))
    assert [e.summary for e in events_on(cal, DAY)] == ["Piano"]   # a Friday
    assert events_on(cal, date(2026, 9, 3)) == []                  # a Thursday


def test_byday_fires_on_each_named_weekday() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Gym", DTSTART="20260803T070000",
                      DTEND="20260803T080000", RRULE="FREQ=WEEKLY;BYDAY=MO,FR"))
    assert events_on(cal, DAY)                      # Friday
    assert events_on(cal, date(2026, 9, 7))         # Monday
    assert events_on(cal, date(2026, 9, 8)) == []   # Tuesday


def test_an_interval_is_respected() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Retro", DTSTART="20260904T100000",
                      DTEND="20260904T110000", RRULE="FREQ=WEEKLY;INTERVAL=2"))
    assert events_on(cal, DAY)
    assert events_on(cal, date(2026, 9, 11)) == []
    assert events_on(cal, date(2026, 9, 18))


def test_a_finished_series_stops() -> None:
    ended = _cal(_event(UID="1", SUMMARY="Course", DTSTART="20260801T100000",
                        DTEND="20260801T110000",
                        RRULE="FREQ=WEEKLY;UNTIL=20260815T000000Z"))
    assert events_on(ended, DAY) == []

    counted = _cal(_event(UID="2", SUMMARY="Course", DTSTART="20260821T100000",
                          DTEND="20260821T110000", RRULE="FREQ=WEEKLY;COUNT=2"))
    assert events_on(counted, date(2026, 8, 28))
    assert events_on(counted, DAY) == []


def test_monthly_skips_a_month_that_has_no_such_day() -> None:
    """RFC 5545 skips rather than clamping: the 31st does not become the 28th,
    and inventing an appointment is worse than missing one."""
    cal = _cal(_event(UID="1", SUMMARY="Rent", DTSTART="20260131T090000",
                      DTEND="20260131T093000", RRULE="FREQ=MONTHLY"))
    assert events_on(cal, date(2026, 3, 31))
    assert events_on(cal, date(2026, 2, 28)) == []


def test_yearly_comes_back_once_a_year() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Birthday", DTSTART="20200904T000000",
                      DTEND="20200904T235900", RRULE="FREQ=YEARLY"))
    assert [e.summary for e in events_on(cal, DAY)] == ["Birthday"]


def test_a_cancelled_occurrence_is_gone() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Piano", DTSTART="20260828T170000",
                      DTEND="20260828T180000", RRULE="FREQ=WEEKLY",
                      EXDATE="20260904T170000"))
    assert events_on(cal, date(2026, 8, 28))
    assert events_on(cal, DAY) == []


def test_events_come_back_in_time_order() -> None:
    cal = _cal(
        _event(UID="2", SUMMARY="Lunch", DTSTART="20260904T120000", DTEND="20260904T130000"),
        _event(UID="1", SUMMARY="Standup", DTSTART="20260904T090000", DTEND="20260904T091500"),
    )
    assert [e.summary for e in events_on(cal, DAY)] == ["Standup", "Lunch"]


def test_a_folded_line_is_one_value() -> None:
    """Feeds wrap at 75 octets mid-word; unfolding wrong truncates titles."""
    assert unfold("SUMMARY:Parent-teacher\n  evening") == ["SUMMARY:Parent-teacher evening"]
    cal = _cal("BEGIN:VEVENT\nUID:1\nSUMMARY:Parent-teacher\n  evening\n"
               "DTSTART:20260904T190000\nDTEND:20260904T200000\nEND:VEVENT")
    assert events_on(cal, DAY)[0].summary == "Parent-teacher evening"


def test_escapes_are_markup_not_words() -> None:
    cal = _cal(_event(UID="1", SUMMARY=r"Dinner\, then\; drinks",
                      DTSTART="20260904T190000", DTEND="20260904T200000"))
    assert events_on(cal, DAY)[0].summary == "Dinner, then; drinks"


def test_junk_never_raises() -> None:
    """A feed that 404s into an HTML page must give an empty day, not a 500."""
    assert events_on("<html>Not found</html>", DAY) == []
    assert events_on("", DAY) == []
    assert events_on("BEGIN:VEVENT\nSUMMARY:no start\nEND:VEVENT", DAY) == []
    assert events_on("BEGIN:VEVENT\nDTSTART:nonsense\nEND:VEVENT", DAY) == []


def test_an_event_with_no_end_still_appears() -> None:
    cal = _cal(_event(UID="1", SUMMARY="Reminder", DTSTART="20260904T110000"))
    (event,) = events_on(cal, DAY)
    assert event.end.hour == 12   # an hour, rather than nothing at all
