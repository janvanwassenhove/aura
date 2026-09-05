"""U314: the shipped OAuth ids are either complete or absent — never half.

Spec 014 ("zero-config OAuth") is blocked on registering three apps, which
needs somebody's actual accounts. The code side is finished and waiting: the
moment the ids in `defaults.py` are filled in, Connect becomes one click for
every install.

The failure mode this guards is the one in between. A client id pasted without
its tenant, or a Google id without its secret, does not read as "not configured
yet" — it reaches the provider and comes back as an opaque error, to an owner
standing in a living room. Constitution XI: report the absence, or report a
working value; never something in between.
"""

from __future__ import annotations

import re

from identity_service import defaults

# A GUID, which is what Azure and the Google/GitHub ids are shaped like.
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                   r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def test_microsoft_is_complete_or_absent() -> None:
    if defaults.MICROSOFT_CLIENT_ID:
        assert _GUID.match(defaults.MICROSOFT_CLIENT_ID), (
            "an Azure Application (client) ID is a GUID — this looks like "
            "something else was pasted")
        assert defaults.MICROSOFT_TENANT_ID, (
            "a client id without a tenant cannot start a device-code flow")


def test_google_is_complete_or_absent() -> None:
    """The device-code token exchange needs both halves; one is not usable."""
    assert bool(defaults.GOOGLE_CLIENT_ID) == bool(defaults.GOOGLE_CLIENT_SECRET), (
        "Google needs the client id AND the secret, or neither")
    if defaults.GOOGLE_CLIENT_ID:
        assert defaults.GOOGLE_CLIENT_ID.endswith(".apps.googleusercontent.com")


def test_github_looks_like_an_oauth_app_id() -> None:
    if defaults.GITHUB_CLIENT_ID:
        assert defaults.GITHUB_CLIENT_ID.startswith(("Iv1.", "Ov23")), (
            "a GitHub OAuth App client id starts with Iv1. or Ov23 — a "
            "personal access token pasted here would never work")


def test_shipped_reports_only_complete_providers() -> None:
    """The console asks this to decide between "press Connect" and "paste an
    id first", so a half-filled provider must report False."""
    state = defaults.shipped()
    assert set(state) == {"microsoft", "google", "github"}
    assert state["microsoft"] is bool(
        defaults.MICROSOFT_CLIENT_ID and defaults.MICROSOFT_TENANT_ID)
    assert state["google"] is bool(
        defaults.GOOGLE_CLIENT_ID and defaults.GOOGLE_CLIENT_SECRET)


def test_the_tenant_default_admits_home_accounts() -> None:
    """"common" is what lets a personal Microsoft account sign in at all. A
    single tenant id here would lock out every household that is not a
    company, silently."""
    assert defaults.MICROSOFT_TENANT_ID == "common" or _GUID.match(
        defaults.MICROSOFT_TENANT_ID)


def test_the_header_still_explains_how_to_fill_them_in() -> None:
    """This docstring is the whole handover for the one task that unblocks
    spec 014. If it is ever trimmed away, the blocker becomes folklore."""
    doc = defaults.__doc__ or ""
    assert "portal.azure.com" in doc
    assert "Allow public client flows" in doc, "the step everybody forgets"
    assert "TVs and Limited Input devices" in doc
    assert "Device Flow" in doc
