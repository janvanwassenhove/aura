"""U295: the Connections panel is for the person who owns the household.

Reported as "don't we have more user friendly ways to connect? this is really
dev like", with a screenshot of the Microsoft 365 row reading:

    Set M365_CONNECTOR=workiq and register an Azure app for the real one.
    Microsoft OAuth app not configured. Set AZURE_CLIENT_ID or register the
    default AURA dev app.

Two environment variable names and an Azure app registration, in the panel a
family uses to see their calendar. The facts were right; the audience was not.

`missing` still carries the variable names, because a diagnostic that drops
them helps nobody — it is the visible SENTENCE that had to change.
"""

from __future__ import annotations

import re

from connector_service.connector_state import describe

# ALL_CAPS_WITH_UNDERSCORES — how an env var looks, and nothing a person says.
_ENV_VAR = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")


def _visible(info) -> str:
    return f"{info.detail} {info.next_step}"


def test_no_environment_variable_names_are_shown_to_the_owner() -> None:
    for info in describe():
        found = _ENV_VAR.findall(_visible(info))
        assert not found, f"{info.label}: {found} in {_visible(info)!r}"


def test_the_missing_list_still_names_them_for_diagnosis() -> None:
    """Plain language on screen, precise data underneath — the console uses
    `missing` to decide whether to offer the app-ID field at all."""
    withs = [i for i in describe() if i.missing]
    if withs:
        assert all(v.isupper() for i in withs for v in i.missing)


def test_a_missing_app_id_says_it_is_one_time_and_free() -> None:
    """What follows is real work; saying so up front is the difference between
    a task and a wall."""
    for info in describe():
        if not info.missing:
            continue
        text = _visible(info).lower()
        assert "once" in text, info.label


def test_the_step_points_at_a_page_that_can_be_opened() -> None:
    """The console turns a URL in this sentence into a link, so there has to
    be one — "register an app" with nowhere to go is not an instruction."""
    for info in describe():
        if not info.missing:
            continue
        assert "http" in info.next_step, info.label


def test_the_easy_connection_is_offered_before_the_hard_ones() -> None:
    """U298: "app-ids is enige manier? er niks gebruiksvriendelijker?"

    A calendar link needs no app, no consent screen and no sign-in. Listing it
    after two connectors that each want an Azure registration would bury the
    only one most households ever need."""
    keys = [i.key for i in describe()]
    assert keys[0] == "calendar_link"


def test_the_calendar_link_is_never_described_as_an_app_id() -> None:
    """It is a URL you copy out of Outlook. Calling it an app ID would send
    somebody to portal.azure.com for the connector that exists to avoid it."""
    (info,) = [i for i in describe(enabled={"calendar_link"})
               if i.key == "calendar_link"]
    text = _visible(info).lower()
    assert "app id" not in text
    assert ".ics" in text
    assert "read" in text, "and it must say it is read-only"


def test_github_is_not_sent_to_register_an_oauth_app() -> None:
    """U298: a personal access token is one click; registering an OAuth App is
    ten minutes for the same result. The panel pointed at the ten minutes."""
    (info,) = [i for i in describe(enabled={"github"}) if i.key == "github"]
    assert "settings/tokens" in info.next_step
    assert "settings/developers" not in info.next_step


# ── U314: the one manual step, made small ──────────────────────────────────

def test_every_connector_that_needs_something_says_how_to_get_it() -> None:
    """Spec 014 is blocked on three app registrations only the owner can do.
    The step that remains must be followable without knowing what OAuth is."""
    for info in describe(enabled={"m365", "google", "github", "slack",
                                  "calendar_link"}):
        if info.status in ("no_credentials", "unauthenticated"):
            assert info.setup_steps, info.label


def test_the_steps_open_the_exact_page_not_a_portal_front_door() -> None:
    for info in describe(enabled={"m365", "google", "github", "slack"}):
        if not info.setup_steps:
            continue
        assert info.register_url.startswith("https://"), info.label
        # A link to portal.azure.com's home page is a research project, not a
        # step: the owner then has to find "App registrations" themselves.
        assert len(info.register_url.rstrip("/").split("/")) > 3, info.label


def test_a_pasted_calendar_link_needs_no_page_to_open() -> None:
    """It is obtained inside the owner's own calendar app, so there is
    nothing for us to link to — but there are still steps."""
    (info,) = [i for i in describe(enabled={"calendar_link"})
               if i.key == "calendar_link"]
    assert info.setup_steps
    assert info.register_url == ""
    assert any("outlook" in s.lower() for s in info.setup_steps)
    assert any("google" in s.lower() for s in info.setup_steps)


def test_the_microsoft_steps_name_the_choice_that_is_easy_to_get_wrong() -> None:
    """Picking a single-tenant account type is the one mistake that makes a
    home Microsoft account unable to sign in, and the portal defaults to it."""
    (info,) = [i for i in describe(enabled={"m365"}) if i.key == "m365"]
    joined = " ".join(info.setup_steps).lower()
    assert "personal microsoft account" in joined
    assert "organizational directory" in joined


def test_a_connected_connector_is_not_handed_a_walkthrough() -> None:
    """Instructions for something already done are noise.

    `mock` is deliberately NOT in that set: showing example data is precisely
    the state where "how do I connect the real one?" is the next question."""
    for info in describe(enabled={"m365"}, registry=None):
        if info.status == "ok":
            assert not info.setup_steps, info.label
