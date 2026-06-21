"""Route integration tests — FastAPI routes with mock connector."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from connector_service.connectors.mock import MockM365Connector
from connector_service import routes
from connector_service.main import create_app


@pytest.fixture
def client() -> TestClient:
    routes.set_connector(MockM365Connector())
    app = create_app()
    # Override lifespan: connector is already set
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

def test_health(client):
    resp = client.get("/connector/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #

def test_calendar_today(client):
    resp = client.get("/connector/calendar/today")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert "event_id" in first
    assert "subject" in first
    assert "start" in first
    assert "end" in first


# --------------------------------------------------------------------------- #
# Mail
# --------------------------------------------------------------------------- #

def test_unread_mail(client):
    resp = client.get("/connector/mail/unread")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first = data[0]
    assert "message_id" in first
    assert "sender" in first
    assert "subject" in first


def test_send_mail(client):
    resp = client.post(
        "/connector/mail/send",
        json={"to": "alice@contoso.com", "subject": "Hello", "body": "Hi there"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# --------------------------------------------------------------------------- #
# Teams
# --------------------------------------------------------------------------- #

def test_post_teams_message(client):
    resp = client.post(
        "/connector/teams/message",
        json={"channel": "general", "content": "Hello team!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["channel"] == "general"
    assert data["content"] == "Hello team!"
    assert "message_id" in data
    assert "sent_at" in data


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #

def test_list_tasks(client):
    resp = client.get("/connector/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "task_id" in data[0]
    assert "title" in data[0]
    assert "is_complete" in data[0]


def test_create_task(client):
    resp = client.post(
        "/connector/tasks",
        json={"title": "Write docs", "plan_id": "plan-001", "due_date": "2026-06-01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Write docs"
    assert data["task_id"]
    assert data["is_complete"] is False


def test_create_task_minimal(client):
    resp = client.post("/connector/tasks", json={"title": "Quick task"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Quick task"


# --------------------------------------------------------------------------- #
# Log safety — mock connector must not log sensitive content
# --------------------------------------------------------------------------- #

def test_send_mail_no_body_in_logs(client, caplog):
    import logging
    secret_body = "this-is-very-sensitive-content-xyz"
    with caplog.at_level(logging.DEBUG):
        resp = client.post(
            "/connector/mail/send",
            json={"to": "a@b.com", "subject": "Test", "body": secret_body},
        )
    assert resp.status_code == 200
    for record in caplog.records:
        assert secret_body not in record.getMessage(), (
            f"Mail body leaked into log: {record.getMessage()!r}"
        )
