"""Contract tests — MockM365Connector must satisfy M365Connector interface."""

from __future__ import annotations

import pytest

from connector_service.connectors.mock import MockM365Connector
from shared_schemas.m365.models import CalendarEvent, MailItem, Task, TeamsMessage


@pytest.fixture
def connector() -> MockM365Connector:
    return MockM365Connector()


# --------------------------------------------------------------------------- #
# list_calendar_events_today
# --------------------------------------------------------------------------- #

async def test_list_calendar_events_returns_calendar_events(connector):
    events = await connector.list_calendar_events_today()
    assert len(events) >= 1
    for ev in events:
        assert isinstance(ev, CalendarEvent)
        assert ev.event_id
        assert ev.subject
        assert ev.start < ev.end


# --------------------------------------------------------------------------- #
# get_unread_mail
# --------------------------------------------------------------------------- #

async def test_get_unread_mail_returns_mail_items(connector):
    items = await connector.get_unread_mail()
    assert len(items) >= 1
    for item in items:
        assert isinstance(item, MailItem)
        assert item.message_id
        assert item.sender
        assert item.subject
        assert item.received_at is not None


async def test_get_unread_mail_respects_limit(connector):
    # Mock returns 1 item regardless, but the method must accept the param
    items = await connector.get_unread_mail(limit=5)
    assert isinstance(items, list)


# --------------------------------------------------------------------------- #
# post_teams_message
# --------------------------------------------------------------------------- #

async def test_post_teams_message_returns_teams_message(connector):
    msg = await connector.post_teams_message(channel="general", content="Hello team!")
    assert isinstance(msg, TeamsMessage)
    assert msg.channel == "general"
    assert msg.content == "Hello team!"
    assert msg.message_id
    assert msg.sent_at is not None


# --------------------------------------------------------------------------- #
# send_mail
# --------------------------------------------------------------------------- #

async def test_send_mail_succeeds(connector):
    # Must not raise; returns None
    result = await connector.send_mail(
        to="alice@contoso.com",
        subject="Test",
        body="Hello",
    )
    assert result is None


# --------------------------------------------------------------------------- #
# list_tasks
# --------------------------------------------------------------------------- #

async def test_list_tasks_returns_tasks(connector):
    tasks = await connector.list_tasks()
    assert len(tasks) >= 1
    for task in tasks:
        assert isinstance(task, Task)
        assert task.task_id
        assert task.title


async def test_list_tasks_with_plan_id(connector):
    tasks = await connector.list_tasks(plan_id="plan-123")
    assert isinstance(tasks, list)


# --------------------------------------------------------------------------- #
# create_task
# --------------------------------------------------------------------------- #

async def test_create_task_returns_task(connector):
    task = await connector.create_task(title="Write tests")
    assert isinstance(task, Task)
    assert task.title == "Write tests"
    assert task.task_id
    assert task.is_complete is False


async def test_create_task_with_due_date(connector):
    task = await connector.create_task(
        title="Deploy to prod",
        plan_id="plan-xyz",
        due_date="2026-05-01",
    )
    assert task.due_date is not None
    assert task.plan_id == "plan-xyz"
