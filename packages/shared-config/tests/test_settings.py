"""U374 (audit T8): the settings every connector reads, tested for the first time.

`shared-config` is 233 lines that every connector and the identity service
read at start-up: which connectors are on, which keyring backend holds the
tokens, where the calendar link is. It had no tests. What can go wrong here is
quiet — a secret that prints, a connector list that keeps an empty entry, a
`.env.local` on the developer's machine leaking into a test — and quiet is the
kind this audit is about.
"""

from __future__ import annotations

import pytest
from shared_config.connector import (
    CalendarLinkSettings,
    ConnectorServiceSettings,
    KeyringSettings,
)
from shared_config.identity import IdentityServiceSettings


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    """A developer's `.env.local` must not be what these tests measure."""
    for name in ("KEYRING_BACKEND", "KEYRING_PASSPHRASE", "ENABLED_CONNECTORS",
                 "CALENDAR_ICS_URL", "AZURE_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


def _connectors(**kw) -> ConnectorServiceSettings:
    return ConnectorServiceSettings(_env_file=None, **kw)


# ── which connectors are on ────────────────────────────────────────────────

def test_the_enabled_list_is_parsed_and_trimmed() -> None:
    s = _connectors(enabled_connectors=" m365, google ,github ")
    assert s.enabled_connector_list == ["m365", "google", "github"]


def test_an_empty_entry_is_not_a_connector() -> None:
    """`"m365,,"` from a hand-edited env must not enable a connector called ""."""
    assert _connectors(enabled_connectors="m365,,").enabled_connector_list == ["m365"]
    assert _connectors(enabled_connectors="").enabled_connector_list == []


def test_the_default_is_m365_alone() -> None:
    assert _connectors().enabled_connector_list == ["m365"]


def test_the_list_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("ENABLED_CONNECTORS", "github,slack")
    assert _connectors().enabled_connector_list == ["github", "slack"]


# ── the keyring ────────────────────────────────────────────────────────────

def test_the_keyring_defaults_to_the_os_native_store() -> None:
    assert KeyringSettings(_env_file=None).keyring_backend == "auto"


def test_the_backend_is_chosen_by_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("KEYRING_BACKEND", "cryptfile")
    assert KeyringSettings(_env_file=None).keyring_backend == "cryptfile"


def test_an_unknown_backend_is_refused_not_guessed(monkeypatch) -> None:
    monkeypatch.setenv("KEYRING_BACKEND", "plaintext")
    with pytest.raises(ValueError):
        KeyringSettings(_env_file=None)


def test_the_passphrase_never_prints(monkeypatch) -> None:
    """A settings object ends up in logs, tracebacks and debug dumps. The
    passphrase in it must not."""
    monkeypatch.setenv("KEYRING_PASSPHRASE", "hunter2-not-real")
    s = KeyringSettings(_env_file=None)
    assert s.keyring_passphrase.get_secret_value() == "hunter2-not-real"
    for rendering in (repr(s), str(s), str(s.model_dump())):
        assert "hunter2-not-real" not in rendering


def test_identity_secrets_never_print_either(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "az-secret-not-real")
    s = IdentityServiceSettings(_env_file=None)
    assert s.azure_client_secret.get_secret_value() == "az-secret-not-real"
    assert "az-secret-not-real" not in repr(s)
    assert "az-secret-not-real" not in str(s.model_dump())


# ── the calendar link ──────────────────────────────────────────────────────

def test_the_calendar_link_is_empty_until_the_owner_pastes_one() -> None:
    s = CalendarLinkSettings(_env_file=None)
    assert s.calendar_ics_url == "" and s.calendar_timezone == ""


def test_the_calendar_link_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("CALENDAR_ICS_URL", "https://example.invalid/basic.ics")
    assert CalendarLinkSettings(_env_file=None).calendar_ics_url == "https://example.invalid/basic.ics"


def test_unknown_environment_keys_are_ignored_not_fatal(monkeypatch) -> None:
    """Every AURA env file carries keys these classes do not know; `extra`
    must stay `ignore` or the first stray variable stops the service."""
    monkeypatch.setenv("SOMETHING_NOBODY_DECLARED", "1")
    assert _connectors().port == 8004
