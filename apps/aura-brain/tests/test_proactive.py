"""U110: proactive Richie — voice reminders + a daily briefing on his own
initiative, gated by enable/sleep/quiet-hours."""

from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.proactive import ProactiveEngine, _in_quiet_hours
from shared_schemas.events.conversation import ResponseDrafted


class _Bus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event) -> None:
        self.published.append(event)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("PROACTIVE_ENABLED", "ROBOT_ASLEEP", "PROACTIVE_QUIET_START",
              "PROACTIVE_QUIET_END", "PROACTIVE_BRIEFING_TIME"):
        monkeypatch.delenv(k, raising=False)


def _at(h, m=0):
    return datetime(2026, 7, 16, h, m)


# -- gating ------------------------------------------------------------

def test_quiet_hours_wrap_midnight() -> None:
    assert _in_quiet_hours(_at(23), "22:00", "08:00") is True
    assert _in_quiet_hours(_at(3), "22:00", "08:00") is True
    assert _in_quiet_hours(_at(12), "22:00", "08:00") is False


def test_should_speak_respects_switches(monkeypatch) -> None:
    eng = ProactiveEngine(_Bus(), "s", now_fn=lambda: _at(12))
    assert eng.should_speak() is True
    monkeypatch.setenv("PROACTIVE_ENABLED", "false")
    assert eng.should_speak() is False
    monkeypatch.setenv("PROACTIVE_ENABLED", "true")
    monkeypatch.setenv("ROBOT_ASLEEP", "true")
    assert eng.should_speak() is False


def test_should_speak_quiet_hours(monkeypatch) -> None:
    monkeypatch.setenv("PROACTIVE_QUIET_START", "22:00")
    monkeypatch.setenv("PROACTIVE_QUIET_END", "08:00")
    assert ProactiveEngine(_Bus(), "s", now_fn=lambda: _at(23)).should_speak() is False
    assert ProactiveEngine(_Bus(), "s", now_fn=lambda: _at(10)).should_speak() is True


# -- announcing --------------------------------------------------------

async def test_announce_publishes_response_drafted() -> None:
    bus = _Bus()
    eng = ProactiveEngine(bus, "s", now_fn=lambda: _at(12))
    assert await eng.announce("Tijd voor je meeting") is True
    assert len(bus.published) == 1
    assert isinstance(bus.published[0], ResponseDrafted)
    assert "meeting" in bus.published[0].response_text


async def test_announce_suppressed_when_asleep(monkeypatch) -> None:
    monkeypatch.setenv("ROBOT_ASLEEP", "true")
    bus = _Bus()
    assert await ProactiveEngine(bus, "s", now_fn=lambda: _at(12)).announce("hi") is False
    assert bus.published == []


async def test_on_reminder_voices_message() -> None:
    bus = _Bus()
    eng = ProactiveEngine(bus, "s", now_fn=lambda: _at(12))

    class _Ev:
        message = "bel de tandarts"

    await eng.on_reminder(_Ev())
    assert "tandarts" in bus.published[0].response_text


# -- daily briefing ----------------------------------------------------

def test_briefing_due_once_per_day(monkeypatch) -> None:
    monkeypatch.setenv("PROACTIVE_BRIEFING_TIME", "08:00")
    clock = {"t": _at(8, 1)}
    eng = ProactiveEngine(_Bus(), "s", now_fn=lambda: clock["t"])
    assert eng.briefing_due() is True    # first time past 08:00
    assert eng.briefing_due() is False   # already fired today
    # Before the time → not due.
    eng2 = ProactiveEngine(_Bus(), "s", now_fn=lambda: _at(7, 59))
    monkeypatch.setenv("PROACTIVE_BRIEFING_TIME", "08:00")
    assert eng2.briefing_due() is False


def test_briefing_off_when_unset() -> None:
    assert ProactiveEngine(_Bus(), "s", now_fn=lambda: _at(8)).briefing_due() is False


async def test_maybe_briefing_speaks(monkeypatch) -> None:
    monkeypatch.setenv("PROACTIVE_BRIEFING_TIME", "08:00")
    bus = _Bus()
    eng = ProactiveEngine(bus, "s", now_fn=lambda: _at(8, 0))

    async def _brief():
        return "Goedemorgen! Drie afspraken vandaag."

    assert await eng.maybe_briefing(_brief) is True
    assert "Goedemorgen" in bus.published[0].response_text
