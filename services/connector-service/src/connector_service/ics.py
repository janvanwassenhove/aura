"""U298: reading a calendar from a link, with nothing to register.

Asked as "app-ids is enige manier? er niks gebruiksvriendelijker?" — and no,
an app ID is not the only way. Outlook, Google Calendar and Apple Calendar can
each hand out a private subscription link: one URL, ending in .ics, that
returns the agenda as text. Pasting that is a thirty-second job with no app
registration, no consent screen and no sign-in.

It buys less than a real account — read-only, calendar only, no mail and no
sending — but "what is on today" is the question a household actually asks,
and this answers it without sending anybody to portal.azure.com.

Parsed here rather than with a library on purpose: `uv sync` prunes any extra
that is not requested and this repository has been bitten by that four times
(U179, U213, U246, U266). RFC 5545 is large; the part a subscription feed uses
is small and stable, and stdlib `zoneinfo` covers the hard bit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# RFC 5545 weekday codes, in Python's Monday=0 order.
_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

#: How many repeats of a rule are walked before giving up. A daily event that
#: started ten years ago is ~3650; past this it is a feed that would hang the
#: answer, and one missing row beats a stalled reply.
_MAX_STEPS = 6000

# stdlib UTC, not ZoneInfo("UTC"): on Windows there is no system zone
# database, so every named zone needs the `tzdata` package — and the one
# zone that must never depend on a package is the one every feed uses.
_UTC = UTC


@dataclass(frozen=True)
class Occurrence:
    """One event on one day — a recurring event yields one of these per day."""

    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str = ""
    organizer: str = ""
    all_day: bool = False


def unfold(text: str) -> list[str]:
    """Join RFC 5545 continuation lines (a line starting with space or tab)."""
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _prop(line: str) -> tuple[str, dict[str, str], str] | None:
    """Split `NAME;PARAM=value:the value` into name, params and value."""
    head, sep, value = line.partition(":")
    if not sep:
        return None
    name, *raw_params = head.split(";")
    params: dict[str, str] = {}
    for p in raw_params:
        k, _, v = p.partition("=")
        params[k.strip().upper()] = v.strip().strip('"')
    return name.strip().upper(), params, value


def _zone(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        # A feed naming a zone this machine does not carry is no reason to drop
        # the whole calendar; that event just floats, like a naive one.
        logger.debug("unknown TZID %r in calendar feed", name)
        return None


def _parse_dt(value: str, params: dict[str, str]) -> tuple[datetime, bool] | None:
    """A DTSTART/DTEND value → (datetime, is_all_day)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and "T" not in value):
        try:
            return datetime.strptime(value, "%Y%m%d"), True  # noqa: DTZ007
        except ValueError:
            return None
    utc = value.endswith("Z")
    try:
        dt = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")  # noqa: DTZ007
    except ValueError:
        return None
    if utc:
        return dt.replace(tzinfo=_UTC), False
    zone = _zone(params["TZID"]) if "TZID" in params else None
    return (dt.replace(tzinfo=zone) if zone else dt), False


def _rrule(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in value.split(";"):
        k, _, v = part.partition("=")
        if k:
            out[k.strip().upper()] = v.strip()
    return out


def _int(rule: dict[str, str], key: str, default: int | None = None) -> int | None:
    try:
        return int(rule[key]) if key in rule else default
    except ValueError:
        return default


def _add_months(d: date, n: int) -> date | None:
    """`d` plus n months, or None when the target month has no such day.

    RFC 5545 skips those rather than clamping: a rule on the 31st simply does
    not fire in February.
    """
    m = d.month - 1 + n
    try:
        return date(d.year + m // 12, m % 12 + 1, d.day)
    except ValueError:
        return None


def _starts(dtstart: datetime, rule: dict[str, str],
            since: date, until_day: date) -> list[date]:
    """The dates this rule starts an event on, within [since, until_day]."""
    freq = rule.get("FREQ", "").upper()
    first = dtstart.date()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return [first]

    interval = max(1, _int(rule, "INTERVAL", 1) or 1)
    count = _int(rule, "COUNT")
    until: date | None = None
    if "UNTIL" in rule:
        parsed = _parse_dt(rule["UNTIL"], {})
        until = parsed[0].date() if parsed else None
    byday = sorted({_WEEKDAYS[d[-2:].upper()] for d in rule.get("BYDAY", "").split(",")
                    if d[-2:].upper() in _WEEKDAYS})

    out: list[date] = []
    seen = 0

    def take(day: date) -> bool:
        """Record one occurrence. False means the rule is exhausted."""
        nonlocal seen
        if day < first:
            return True
        if until is not None and day > until:
            return False
        seen += 1
        if count is not None and seen > count:
            return False
        if since <= day <= until_day:
            out.append(day)
        return True

    for i in range(_MAX_STEPS):
        if freq == "WEEKLY" and byday:
            # A weekly rule with BYDAY fires on several weekdays per period, so
            # each step is a WEEK that fans out into its days.
            monday = first - timedelta(days=first.weekday()) + timedelta(weeks=i * interval)
            days = [monday + timedelta(days=wd) for wd in byday]
        elif freq == "DAILY":
            days = [first + timedelta(days=i * interval)]
        elif freq == "WEEKLY":
            days = [first + timedelta(weeks=i * interval)]
        elif freq == "MONTHLY":
            got = _add_months(first, i * interval)
            days = [got] if got else []
        else:  # YEARLY
            got = _add_months(first, i * interval * 12)
            days = [got] if got else []

        for day in days:
            if not take(day):
                return out
        if days and min(days) > until_day:
            return out
    return out


def _covers(start: datetime, end: datetime, day: date, all_day: bool) -> bool:
    """Does an event running start→end fall on `day`?"""
    last = end.date()
    # DTEND is exclusive: an all-day event on the 4th ends on the 5th, and a
    # timed one ending at midnight belongs to the day before.
    if end > start and (all_day or end.time() == time(0, 0)):
        last = (end - timedelta(seconds=1)).date()
    return start.date() <= day <= max(last, start.date())


def _local(dt: datetime, zone: tzinfo | None) -> datetime:
    """Move an aware datetime into the household's zone; leave floating ones."""
    if zone is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(zone)


def _unescape(value: str) -> str:
    r"""RFC 5545 escapes: \n, \, and \; are markup, not part of the words."""
    return (value.replace("\\n", " ").replace("\\N", " ")
            .replace("\\,", ",").replace("\\;", ";")
            .replace("\\\\", "\\").strip())


def _expand(fields: dict[str, tuple[dict[str, str], str]], rrule: str,
            excluded: set[date], day: date, zone: tzinfo | None) -> list[Occurrence]:
    """One VEVENT → the occurrences of it that land on `day`."""
    if "DTSTART" not in fields:
        return []
    params, value = fields["DTSTART"]
    got = _parse_dt(value, params)
    if got is None:
        return []
    start, all_day = got

    end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    if "DTEND" in fields:
        end_params, end_value = fields["DTEND"]
        got_end = _parse_dt(end_value, end_params)
        if got_end is not None:
            end = got_end[0]
    span = max(end - start, timedelta(0))

    summary = _unescape(fields.get("SUMMARY", ({}, ""))[1]) or "(no title)"
    location = _unescape(fields.get("LOCATION", ({}, ""))[1])
    organizer = _unescape(fields.get("ORGANIZER", ({}, ""))[1]).replace("mailto:", "")
    uid = fields.get("UID", ({}, ""))[1] or summary

    if rrule:
        # An event that began yesterday and runs into today still counts, so
        # the window reaches back by its own length.
        since = day - timedelta(days=span.days + 1)
        starts = _starts(start, _rrule(rrule), since, day)
    else:
        starts = [start.date()]

    out: list[Occurrence] = []
    for on in starts:
        occ = start.replace(year=on.year, month=on.month, day=on.day)
        local_start, local_end = _local(occ, zone), _local(occ + span, zone)
        if local_start.date() in excluded:
            continue
        if not _covers(local_start, local_end, day, all_day):
            continue
        out.append(Occurrence(
            uid=f"{uid}@{on.isoformat()}" if rrule else uid,
            summary=summary, start=local_start, end=local_end,
            location=location, organizer=organizer, all_day=all_day,
        ))
    return out


def events_on(text: str, day: date, timezone: str = "") -> list[Occurrence]:
    """Every event in an iCalendar feed that falls on `day`, earliest first."""
    zone = _zone(timezone) if timezone else None
    out: list[Occurrence] = []

    in_event = False
    fields: dict[str, tuple[dict[str, str], str]] = {}
    excluded: set[date] = set()
    rrule = ""

    for line in unfold(text):
        stripped = line.strip()
        upper = stripped.upper()
        if upper == "BEGIN:VEVENT":
            in_event, fields, excluded, rrule = True, {}, set(), ""
            continue
        if upper == "END:VEVENT":
            if in_event:
                out.extend(_expand(fields, rrule, excluded, day, zone))
            in_event = False
            continue
        if not in_event:
            continue
        parsed = _prop(stripped)
        if parsed is None:
            continue
        name, params, value = parsed
        if name == "RRULE":
            rrule = value
        elif name == "EXDATE":
            for one in value.split(","):
                got = _parse_dt(one, params)
                if got:
                    excluded.add(_local(got[0], zone).date())
        elif name not in fields:
            # First wins: a VEVENT with two DTSTARTs is malformed, and taking
            # the later one silently moves the appointment.
            fields[name] = (params, value)

    out.sort(key=lambda o: (o.start.replace(tzinfo=None), o.summary))
    return out
