"""Tests for GatewayManager, WebhookDispatcher, and gateway routes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.gateway import (
    GatewayActionError,
    GatewayAuthError,
    GatewayManager,
    GatewayModeError,
    GatewayRateLimitError,
)
from orchestrator.webhook_dispatcher import WebhookDispatcher
from shared_events.bus import AsyncEventBus
from shared_schemas.gateway.models import (
    AuditEntry,
    CommandStatus,
    GatewayAction,
    SENSITIVE_ACTIONS,
    WebhookRegistration,
)
from shared_schemas.events.robot import RobotModeChanged


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mgr():
    return GatewayManager(api_keys={"agent1": "secret-key-1", "agent2": "secret-key-2"})


@pytest.fixture
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


# ===========================================================================
# GatewayManager — authentication
# ===========================================================================


def test_valid_key_dispatches_command(mgr):
    cmd, entry = mgr.dispatch("secret-key-1", "speak", {"text": "Hello"})
    assert cmd.action == GatewayAction.SPEAK
    assert entry.key_id == "agent1"
    assert entry.action_type == "speak"


def test_invalid_key_raises_auth_error(mgr):
    with pytest.raises(GatewayAuthError):
        mgr.dispatch("wrong-key", "speak", {})


def test_revoked_key_raises_auth_error(mgr):
    mgr.revoke_key("agent1")
    with pytest.raises(GatewayAuthError):
        mgr.dispatch("secret-key-1", "speak", {})


def test_register_new_key_allows_dispatch(mgr):
    mgr.register_key("agent3", "new-key")
    cmd, entry = mgr.dispatch("new-key", "speak", {})
    assert entry.key_id == "agent3"


# ===========================================================================
# GatewayManager — mode blocking
# ===========================================================================


def test_offline_mode_raises_mode_error(mgr):
    with pytest.raises(GatewayModeError) as exc_info:
        mgr.dispatch("secret-key-1", "speak", {}, current_mode="OFFLINE")
    assert exc_info.value.mode == "OFFLINE"


def test_maintenance_mode_raises_mode_error(mgr):
    with pytest.raises(GatewayModeError):
        mgr.dispatch("secret-key-1", "speak", {}, current_mode="MAINTENANCE")


def test_online_mode_passes(mgr):
    cmd, _ = mgr.dispatch("secret-key-1", "speak", {}, current_mode="ONLINE")
    assert cmd.action == GatewayAction.SPEAK


# ===========================================================================
# GatewayManager — rate limiting
# ===========================================================================


def test_rate_limit_allows_up_to_limit(mgr):
    for _ in range(10):
        mgr.dispatch("secret-key-1", "speak", {})
    # 11th should be rejected
    with pytest.raises(GatewayRateLimitError) as exc_info:
        mgr.dispatch("secret-key-1", "speak", {})
    assert exc_info.value.retry_after >= 0.0


def test_rate_limit_per_key_independent(mgr):
    # Exhaust agent1's quota
    for _ in range(10):
        mgr.dispatch("secret-key-1", "speak", {})
    # agent2 should still work
    cmd, _ = mgr.dispatch("secret-key-2", "speak", {})
    assert cmd.action == GatewayAction.SPEAK


# ===========================================================================
# GatewayManager — action validation
# ===========================================================================


def test_unknown_action_raises_action_error(mgr):
    with pytest.raises(GatewayActionError, match="Unknown action"):
        mgr.dispatch("secret-key-1", "fly_to_moon", {})


def test_known_actions_all_dispatch(mgr):
    # Use a fresh manager to avoid exhausting rate limits from prior tests
    fresh = GatewayManager(api_keys={"x": "xkey"}, rate_limit=20)
    for action in GatewayAction:
        cmd, _ = fresh.dispatch("xkey", action, {})
        assert cmd.action == action


# ===========================================================================
# GatewayManager — audit log
# ===========================================================================


def test_audit_log_records_command(mgr):
    mgr.dispatch("secret-key-1", "speak", {"text": "hi"})
    log = mgr.get_audit_log()
    assert len(log) == 1
    assert log[0].action_type == "speak"
    assert log[0].key_id == "agent1"


def test_audit_sensitive_action_flagged(mgr):
    mgr.dispatch("secret-key-1", "send_mail", {"to": "a@b.com", "subject": "S", "body": "B"})
    log = mgr.get_audit_log()
    assert log[-1].is_sensitive is True


def test_audit_non_sensitive_not_flagged(mgr):
    mgr.dispatch("secret-key-1", "speak", {"text": "hi"})
    log = mgr.get_audit_log()
    assert log[-1].is_sensitive is False


def test_audit_respects_limit(mgr):
    # Use a manager with high rate limit to avoid hitting the rate cap
    large_mgr = GatewayManager(api_keys={"a": "k"}, rate_limit=100)
    for i in range(25):
        large_mgr.dispatch("k", "speak", {})
    log = large_mgr.get_audit_log(limit=5)
    assert len(log) == 5


def test_audit_status_update(mgr):
    _, entry = mgr.dispatch("secret-key-1", "speak", {})
    mgr.update_audit_status(entry.entry_id, CommandStatus.EXECUTED)
    log = mgr.get_audit_log()
    assert log[-1].status == CommandStatus.EXECUTED


# ===========================================================================
# WebhookDispatcher
# ===========================================================================


def test_register_valid_url(bus):
    dispatcher = WebhookDispatcher(bus)
    reg = dispatcher.register("https://example.com/hook", events=["RobotModeChanged"])
    assert reg.active is True
    assert "RobotModeChanged" in reg.events


def test_register_invalid_url_raises(bus):
    dispatcher = WebhookDispatcher(bus)
    with pytest.raises(ValueError, match="http"):
        dispatcher.register("ftp://bad.url", events=[])


def test_deregister_removes_webhook(bus):
    dispatcher = WebhookDispatcher(bus)
    reg = dispatcher.register("https://example.com/hook")
    assert dispatcher.deregister(reg.webhook_id) is True
    assert dispatcher.list_webhooks() == []


async def test_webhook_delivers_matching_event(bus):
    """Webhook subscribed to RobotModeChanged receives the event."""
    delivered = []

    async def fake_post(url, json=None, **kwargs):
        delivered.append((url, json))
        resp = MagicMock()
        resp.is_success = True
        return resp

    mock_client = AsyncMock()
    mock_client.post = fake_post

    dispatcher = WebhookDispatcher(bus, http_client=mock_client)
    dispatcher.register("https://hook.test/cb", events=["RobotModeChanged"])

    await bus.publish(
        RobotModeChanged(session_id="s1", from_mode="online", to_mode="offline")
    )
    await asyncio.sleep(0.05)  # let create_task fire

    assert len(delivered) == 1
    assert delivered[0][0] == "https://hook.test/cb"


async def test_webhook_skips_non_matching_event(bus):
    delivered = []

    async def fake_post(url, json=None, **kwargs):
        delivered.append(url)
        resp = MagicMock()
        resp.is_success = True
        return resp

    mock_client = AsyncMock()
    mock_client.post = fake_post

    dispatcher = WebhookDispatcher(bus, http_client=mock_client)
    # Only subscribe to RobotModeChanged, but publish a different event
    dispatcher.register("https://hook.test/cb", events=["BackendHeartbeatOk"])

    await bus.publish(
        RobotModeChanged(session_id="s1", from_mode="online", to_mode="offline")
    )
    await asyncio.sleep(0.05)
    assert len(delivered) == 0


async def test_webhook_deactivated_after_failures(bus):
    """A webhook that always fails is marked inactive after MAX_RETRIES."""
    from orchestrator import webhook_dispatcher as wd_mod

    original_base = wd_mod._BACKOFF_BASE_S
    wd_mod._BACKOFF_BASE_S = 0.001  # speed up backoff in test

    async def always_fail(url, json=None, **kwargs):
        resp = MagicMock()
        resp.is_success = False
        resp.status_code = 500
        return resp

    mock_client = AsyncMock()
    mock_client.post = always_fail

    dispatcher = WebhookDispatcher(bus, http_client=mock_client)
    reg = dispatcher.register("https://bad.host/hook")

    await bus.publish(
        RobotModeChanged(session_id="s1", from_mode="online", to_mode="offline")
    )
    await asyncio.sleep(0.5)  # give retries time to complete

    # Restore
    wd_mod._BACKOFF_BASE_S = original_base

    assert dispatcher._webhooks[reg.webhook_id].active is False


# ===========================================================================
# Route integration
# ===========================================================================


@pytest.fixture
def gateway_client(bus):
    from orchestrator import routes as r
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.gateway import GatewayManager
    from orchestrator.intent_router import IntentRouter
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from orchestrator.presentation import PresentationManager
    from orchestrator.webhook_dispatcher import WebhookDispatcher

    gw = GatewayManager(api_keys={"test": "test-secret"}, rate_limit=10)
    intent_router = IntentRouter()
    approval_mgr = ApprovalManager(bus, session_id="gw-test")
    ctx = ContextBuilder()
    persona_mgr = PersonaManager()
    pipeline = OrchestratorPipeline(bus, intent_router, approval_mgr, ctx, persona_mgr)
    pres_mgr = PresentationManager(bus)
    wh = WebhookDispatcher(bus)

    r.init(intent_router, approval_mgr, ctx, persona_mgr, pipeline, pres_mgr, gw, wh)

    app = FastAPI()
    app.include_router(r.router)
    return TestClient(app)


def test_route_command_valid_key_returns_ok(gateway_client):
    resp = gateway_client.post(
        "/gateway/command",
        json={"action": "speak", "payload": {"text": "Hi"}},
        headers={"X-Api-Key": "test-secret"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_route_command_invalid_key_returns_401(gateway_client):
    resp = gateway_client.post(
        "/gateway/command",
        json={"action": "speak", "payload": {}},
        headers={"X-Api-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_route_command_unknown_action_returns_422(gateway_client):
    resp = gateway_client.post(
        "/gateway/command",
        json={"action": "teleport", "payload": {}},
        headers={"X-Api-Key": "test-secret"},
    )
    assert resp.status_code == 422


def test_route_audit_returns_entries(gateway_client):
    # Fire a command first
    gateway_client.post(
        "/gateway/command",
        json={"action": "speak", "payload": {}},
        headers={"X-Api-Key": "test-secret"},
    )
    resp = gateway_client.get("/gateway/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    assert body["entries"][0]["action_type"] == "speak"


def test_route_audit_sensitive_no_payload_content(gateway_client):
    """Sensitive action audit must not contain payload body content (FR-007)."""
    gateway_client.post(
        "/gateway/command",
        json={"action": "send_mail", "payload": {"to": "x@y.com", "subject": "S", "body": "TOP SECRET"}},
        headers={"X-Api-Key": "test-secret"},
    )
    resp = gateway_client.get("/gateway/audit")
    entries = resp.json()["entries"]
    sensitive = [e for e in entries if e["action_type"] == "send_mail"]
    assert len(sensitive) >= 1
    # Confirm "TOP SECRET" is NOT in any serialized entry
    import json
    raw = json.dumps(sensitive)
    assert "TOP SECRET" not in raw


def test_route_register_webhook_returns_id(gateway_client):
    resp = gateway_client.post(
        "/gateway/webhooks",
        json={"url": "https://example.com/hook", "events": ["RobotModeChanged"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "webhook_id" in body


def test_route_register_webhook_bad_url_returns_422(gateway_client):
    resp = gateway_client.post(
        "/gateway/webhooks",
        json={"url": "ftp://not-allowed", "events": []},
    )
    assert resp.status_code == 422


def test_route_list_webhooks(gateway_client):
    gateway_client.post(
        "/gateway/webhooks",
        json={"url": "https://example.com/hook1", "events": []},
    )
    gateway_client.post(
        "/gateway/webhooks",
        json={"url": "https://example.com/hook2", "events": []},
    )
    resp = gateway_client.get("/gateway/webhooks")
    assert resp.status_code == 200
    assert len(resp.json()["webhooks"]) >= 2


def test_route_command_rate_limited_returns_429(gateway_client):
    # Exhaust rate limit (10/s)
    for _ in range(10):
        gateway_client.post(
            "/gateway/command",
            json={"action": "speak", "payload": {}},
            headers={"X-Api-Key": "test-secret"},
        )
    resp = gateway_client.post(
        "/gateway/command",
        json={"action": "speak", "payload": {}},
        headers={"X-Api-Key": "test-secret"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
