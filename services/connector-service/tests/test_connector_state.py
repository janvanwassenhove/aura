"""U254: connections the owner can see, switch on, and feel in what he can do.

Reported with a screenshot of four rows all reading `unknown`, next to Connect
buttons: "deze zijn nog niet geïmplementeerd/niet werkende, en kunnen nog niet
door robot gebruikt worden."

Measured: the connectors WERE implemented (google.py, github.py, slack.py all
exist and speak real APIs), but ENABLED_CONNECTORS defaults to "m365", so the
registry never built them, health never mentioned them, and the console had
nothing to render but `unknown` — the one status an owner cannot act on.
"""

from __future__ import annotations

import pytest
from connector_service import connector_prefs, connector_state
from shared_config import ConnectorServiceSettings


@pytest.fixture(autouse=True)
def _isolated_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("CONNECTOR_PREFS_PATH", str(tmp_path / "prefs.json"))
    connector_prefs.reset_cache_for_tests()
    yield
    connector_prefs.reset_cache_for_tests()


def _s(**kw) -> ConnectorServiceSettings:
    return ConnectorServiceSettings(**kw)


def _by_key(infos):
    return {i.key: i for i in infos}


def test_every_known_connector_is_described_even_when_off() -> None:
    """The console must be able to show Slack as OFF rather than as UNKNOWN.

    "Not enabled" and "not signed in" need completely different actions from
    the owner; one word for both is what made the page useless.
    """
    infos = _by_key(connector_state.describe(_s(enabled_connectors="m365")))
    assert set(infos) == {"m365", "google", "github", "slack"}
    assert infos["slack"].status == connector_state.NOT_ENABLED
    assert infos["slack"].next_step                      # always actionable


def test_a_switched_on_connector_without_an_app_says_exactly_what_is_missing() -> None:
    """Registering an OAuth app is ten minutes of the owner's time and only
    they can do it — so the status has to name the variable and the portal,
    not just fail."""
    infos = _by_key(connector_state.describe(_s(enabled_connectors="m365,google")))
    google = infos["google"]
    assert google.status == connector_state.NO_CREDENTIALS
    assert "GOOGLE_CLIENT_SECRETS_FILE" in google.missing
    assert "console.cloud.google.com" in google.next_step


def test_the_mock_never_claims_to_be_your_account() -> None:
    infos = _by_key(connector_state.describe(_s(enabled_connectors="m365",
                                                m365_connector="mock")))
    assert infos["m365"].status == connector_state.MOCK
    assert "canned data" in infos["m365"].detail


def test_the_owner_can_switch_one_on_and_it_sticks() -> None:
    settings = _s(enabled_connectors="m365")
    assert "github" not in connector_prefs.enabled_keys(settings)

    connector_prefs.set_enabled("github", True)
    connector_prefs.reset_cache_for_tests()          # simulate a restart
    assert "github" in connector_prefs.enabled_keys(settings)


def test_switching_one_off_survives_it_being_in_the_config() -> None:
    """An explicit "off" must beat the configured default, or the switch is a
    lie the next restart tells."""
    settings = _s(enabled_connectors="m365,github")
    connector_prefs.set_enabled("github", False)
    assert "github" not in connector_prefs.enabled_keys(settings)


def test_an_unknown_connector_key_is_refused_not_stored() -> None:
    with pytest.raises(ValueError):
        connector_prefs.set_enabled("myspace", True)


def test_live_domains_are_only_the_ones_that_can_answer() -> None:
    """This set is what the tool policy consumes; a connector that is merely
    switched on must not put mail in it."""
    infos = connector_state.describe(_s(enabled_connectors="m365,google"),
                                     enabled={"m365", "google"})
    domains = connector_state.live_domains(infos)
    assert "mail" in domains          # m365 mock answers mail
    by = _by_key(infos)
    assert by["google"].status == connector_state.NO_CREDENTIALS
    assert "repos" not in domains     # github is off entirely
