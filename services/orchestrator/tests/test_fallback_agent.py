"""Tests for FallbackAgent — offline pattern-matching command handler."""

from __future__ import annotations

import pytest
from orchestrator.fallback_agent import FallbackAgent


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://localhost:9999")
    return FallbackAgent()


async def test_time_query(agent):
    reply = await agent.handle("What time is it?", "s1")
    assert "time" in reply.lower()
    # Should contain something like "12:34 PM"
    import re
    assert re.search(r"\d{1,2}:\d{2}", reply)


async def test_time_alternate_phrasing(agent):
    reply = await agent.handle("What's the current time", "s1")
    assert "time" in reply.lower()


async def test_reminder_offline(agent):
    """FallbackAgent acknowledges the reminder even if memory service is down."""
    reply = await agent.handle("Remind me to call Alice at 3pm", "s1")
    assert "reminder" in reply.lower() or "noted" in reply.lower() or "remind" in reply.lower()


async def test_status_query(agent):
    reply = await agent.handle("What's your status?", "s1")
    assert "offline" in reply.lower() or "degraded" in reply.lower()


async def test_calendar_offline(agent):
    reply = await agent.handle("What meetings do I have today?", "s1")
    assert "offline" in reply.lower() or "cannot" in reply.lower()


async def test_comms_offline(agent):
    reply = await agent.handle("Send an email to bob@example.com", "s1")
    assert "offline" in reply.lower() or "cannot" in reply.lower()


async def test_unknown_falls_back_gracefully(agent):
    reply = await agent.handle("Play some jazz music", "s1")
    assert len(reply) > 0
    assert "offline" in reply.lower() or "limited" in reply.lower()


async def test_timer_offline(agent):
    reply = await agent.handle("Set a timer for 5 minutes", "s1")
    assert "offline" in reply.lower() or "cannot" in reply.lower() or "timer" in reply.lower()
