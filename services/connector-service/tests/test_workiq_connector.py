"""Contract tests — WorkIQConnector with mocked MSAL + httpx."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from connector_service.connectors.errors import ConnectorAuthError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings():
    """Build a ConnectorServiceSettings instance with test values."""
    from shared_config import ConnectorServiceSettings
    return ConnectorServiceSettings(
        azure_client_id="fake-client-id",
        azure_client_secret="fake-secret",
        azure_tenant_id="fake-tenant",
    )


def _mock_msal_app(token: str = "fake-obo-token") -> MagicMock:
    """Return a mock MSAL ConfidentialClientApplication that returns a valid token."""
    app = MagicMock()
    app.acquire_token_on_behalf_of.return_value = {"access_token": token}
    return app


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_connector(obo_token: str = "fake-obo-token"):  # -> WorkIQConnector (lazy import below)
    from connector_service.connectors.workiq import WorkIQConnector
    with patch("msal.ConfidentialClientApplication", return_value=_mock_msal_app(obo_token)):
        return WorkIQConnector(
            settings=_fake_settings(),
            identity_url="http://fake-identity:8006",
            user_id="test-user",
        )


# ---------------------------------------------------------------------------
# ConnectorRegistry builds WorkIQConnector for enabled connectors
# ---------------------------------------------------------------------------

def test_registry_includes_m365_when_enabled(monkeypatch):
    monkeypatch.setenv("AZURE_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("AZURE_TENANT_ID", "fake-tenant")
    monkeypatch.setenv("ENABLED_CONNECTORS", "m365")

    from connector_service.registry import ConnectorRegistry, ConnectorStatus
    from shared_config import ConnectorServiceSettings

    settings = ConnectorServiceSettings(
        azure_client_id="fake-client-id",
        azure_client_secret="fake-secret",
        azure_tenant_id="fake-tenant",
        enabled_connectors="m365",
        m365_connector="workiq",
    )

    with patch("msal.ConfidentialClientApplication", return_value=_mock_msal_app()):
        registry = ConnectorRegistry(settings)
        registry.build()

    connector = registry.get("m365")
    assert connector is not None
    assert registry.health()["m365"] == ConnectorStatus.OK

    from connector_service.connectors.workiq import WorkIQConnector
    assert isinstance(connector, WorkIQConnector)


def test_registry_marks_unauthenticated_when_creds_missing(monkeypatch):
    """Missing Azure creds → UNAUTHENTICATED, not a crash."""
    from connector_service.registry import ConnectorRegistry, ConnectorStatus
    from shared_config import ConnectorServiceSettings

    settings = ConnectorServiceSettings(enabled_connectors="m365", m365_connector="workiq")
    registry = ConnectorRegistry(settings)
    registry.build()

    # Connector is not available (no creds) but registry still tracks it
    assert registry.health().get("m365") == ConnectorStatus.UNAUTHENTICATED
    assert registry.get("m365") is None  # connector itself is None when unauthenticated


# ---------------------------------------------------------------------------
# WorkIQConnector auth
# ---------------------------------------------------------------------------

def test_workiq_raises_connector_auth_error_on_msal_failure():
    bad_app = MagicMock()
    bad_app.acquire_token_on_behalf_of.return_value = {
        "error": "invalid_grant",
        "error_description": "Credentials are invalid",
    }

    from connector_service.connectors.workiq import WorkIQConnector
    with patch("msal.ConfidentialClientApplication", return_value=bad_app):
        connector = WorkIQConnector(
            settings=_fake_settings(),
            identity_url="http://fake-identity:8006",
            user_id="test-user",
        )

    with pytest.raises(ConnectorAuthError, match="MSAL OBO failed"):
        connector._acquire_obo_token("fake-user-token")


# ---------------------------------------------------------------------------
# list_calendar_events_today (MSAL + httpx mocked)
# ---------------------------------------------------------------------------

async def test_workiq_list_calendar_events(monkeypatch):
    fake_obo_token = "fake-obo-token"  # privacy-ok
    fake_user_token = "fake-user-token"  # privacy-ok

    fake_events = [
        {
            "event_id": str(uuid.uuid4()),
            "subject": "Stand-up",
            "start": _now_iso(),
            "end": _now_iso(),
            "location": "",
            "organizer": "",
        }
    ]

    # Mock identity-service response
    id_response = MagicMock()
    id_response.status_code = 200
    id_response.json.return_value = {"access_token": fake_user_token}
    id_response.raise_for_status = MagicMock()

    # Mock Work IQ MCP response
    workiq_response = MagicMock()
    workiq_response.is_success = True
    workiq_response.json.return_value = fake_events
    workiq_response.raise_for_status = MagicMock()

    mock_id_client = AsyncMock()
    mock_id_client.get = AsyncMock(return_value=id_response)
    mock_id_client.__aenter__ = AsyncMock(return_value=mock_id_client)
    mock_id_client.__aexit__ = AsyncMock(return_value=False)

    mock_workiq_client = AsyncMock()
    mock_workiq_client.get = AsyncMock(return_value=workiq_response)
    mock_workiq_client.__aenter__ = AsyncMock(return_value=mock_workiq_client)
    mock_workiq_client.__aexit__ = AsyncMock(return_value=False)

    connector = _make_connector(fake_obo_token)

    # Patch _get_user_token and _acquire_obo_token directly
    with patch.object(connector, "_get_user_token", AsyncMock(return_value=fake_user_token)), \
         patch.object(connector, "_acquire_obo_token", return_value=fake_obo_token), \
         patch("httpx.AsyncClient", return_value=mock_workiq_client):
        events = await connector.list_calendar_events_today()

    assert len(events) == 1
    assert events[0].subject == "Stand-up"


# ---------------------------------------------------------------------------
# send_mail — token must not appear in log output
# ---------------------------------------------------------------------------

async def test_workiq_token_not_in_logs(caplog):
    import logging

    fake_obo_token = "super-secret-bearer-token-xyz"  # privacy-ok
    fake_user_token = "fake-user-token"  # privacy-ok

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    connector = _make_connector(fake_obo_token)

    with caplog.at_level(logging.DEBUG), \
         patch.object(connector, "_get_user_token", AsyncMock(return_value=fake_user_token)), \
         patch.object(connector, "_acquire_obo_token", return_value=fake_obo_token), \
         patch("httpx.AsyncClient", return_value=mock_client):
        await connector.send_mail(to="bob@contoso.com", subject="Hi", body="Hello")

    for record in caplog.records:
        assert fake_obo_token not in record.getMessage(), (
            f"Bearer token leaked into log: {record.getMessage()!r}"
        )
