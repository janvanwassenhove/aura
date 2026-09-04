"""U254: one honest answer about every connector AURA can speak.

The console showed four rows — Microsoft 365, Google, GitHub, Slack — each
with a Connect button and the word `unknown`. Measured on a live install, that
word was hiding three completely different situations:

  * Google, GitHub and Slack were **not enabled at all**. ENABLED_CONNECTORS
    defaults to "m365", so the registry never built them and never reported
    them. Their rows said `unknown` because nothing had an opinion, and their
    Connect button led to a sign-in for a connector that would not exist
    afterwards either.
  * Microsoft 365 was running **canned data** (the mock), which the health
    endpoint did say — but only for the connectors it happened to build.
  * Nothing anywhere distinguished "you never registered an OAuth app" from
    "you registered one but have not signed in yet", although the first needs
    ten minutes in a browser on Azure and the second needs one click.

`unknown` is the only status that tells the owner nothing they can act on. So
this module answers for EVERY connector the code knows how to build, whether
or not it is switched on, and always with the next step attached.

Nothing here talks to a network. State is derived from configuration and from
the registry that has already been built, so it is cheap enough to ask on
every health poll and can never itself be the reason a page hangs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from shared_config import ConnectorServiceSettings

if TYPE_CHECKING:  # pragma: no cover — typing only
    from connector_service.registry import ConnectorRegistry

# The states, in the order a connector travels through them. Each is a
# DIFFERENT job for the owner, which is the whole reason they are separate.
NOT_ENABLED = "not_enabled"        # implemented, switched off
NO_CREDENTIALS = "no_credentials"  # switched on, but no OAuth app registered
UNAUTHENTICATED = "unauthenticated"  # ready, waiting for a sign-in
MOCK = "mock"                      # answering, with canned data
OK = "ok"                          # answering, with the real account
UNAVAILABLE = "unavailable"        # enabled and configured, but it failed to build

#: Statuses in which the connector can actually answer a question.
LIVE = frozenset({MOCK, OK})


@dataclass(frozen=True)
class ConnectorInfo:
    """Everything the console and the brain need to know about one connector."""

    key: str
    label: str
    #: What it can answer — used to decide which TOOLS make sense (U254).
    domains: tuple[str, ...]
    status: str
    #: Plain sentence: what is true right now.
    detail: str
    #: Plain sentence: what the owner would do next. Empty when nothing to do.
    next_step: str = ""
    #: Environment variables that are missing, when status is NO_CREDENTIALS.
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def live(self) -> bool:
        return self.status in LIVE

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "domains": list(self.domains),
            "status": self.status,
            "detail": self.detail,
            "next_step": self.next_step,
            "missing": list(self.missing),
            "live": self.live,
        }


@dataclass(frozen=True)
class _Known:
    """A connector this codebase can build, and what it needs to do so."""

    key: str
    label: str
    domains: tuple[str, ...]
    #: Settings attributes that must be non-empty before a sign-in is possible.
    requires: tuple[tuple[str, str], ...] = ()   # (settings attr, env var name)
    #: Where the owner registers the OAuth app, when credentials are missing.
    register_at: str = ""
    #: U298: the missing-credentials sentence, when "a one-time app ID" is the
    #: wrong noun. A calendar link is not an app registration, and telling
    #: somebody to register an app for it would send them the long way round
    #: past the very thing this connector exists to avoid.
    missing_copy: tuple[str, str] = ()  # type: ignore[assignment]
    #: U254b: the cheapest READ that proves this connector really works, and
    #: the noun to count in the answer. It MUST be a call the connector
    #: actually implements: the probe used to ask everything for today's
    #: calendar, so GitHub and Slack — which deliberately refuse calendar and
    #: do repos and channels instead — could never pass their own Test button.
    probe: tuple[str, str] = ("list_calendar_events_today", "calendar event")
    #: U298: how a sign-in is actually done for THIS connector. GitHub does
    #: not need an app registration at all — a personal access token is one
    #: click — but the panel was pointing at github.com/settings/developers,
    #: the ten-minute route to the same place.
    signin_step: str = "Press Connect and complete the device-code sign-in."
    #: True when the credential is only fetched at CALL time (a keyring token,
    #: an identity lookup) rather than needed to construct the connector. Such
    #: a connector builds happily with no account at all, so "it constructed"
    #: says nothing — and reporting that as `connected` is the exact lie this
    #: section's own header warns against ("a green badge means a real call
    #: worked"). For these, green has to be EARNED by a successful probe.
    verifies_at_call_time: bool = False


# Registered here rather than discovered, because "which connectors exist" is
# a product decision: an owner should see Slack listed and switched off, not
# be left wondering whether AURA has heard of it.
KNOWN: tuple[_Known, ...] = (
    _Known(
        # U298: asked as "app-ids is enige manier? er niks gebruiksvriendelijker?"
        # Outlook, Google and Apple all publish a private .ics link for a
        # calendar. Pasting it needs no app, no consent screen and no sign-in.
        key="calendar_link", label="Calendar by link",
        domains=("calendar",),
        requires=(("calendar_ics_url", "CALENDAR_ICS_URL"),),
        missing_copy=(
            "Not connected yet. This is the quick one: paste the sharing link "
            "from your calendar and he can read your agenda — nothing to "
            "register, nothing to sign in to.",
            "In Outlook or Google Calendar, publish the calendar and copy the "
            "link ending in .ics, then paste it here. It only lets him READ "
            "the calendar.",
        ),
    ),
    _Known(
        key="m365", label="Microsoft 365",
        domains=("mail", "calendar", "tasks", "chat", "files"),
        requires=(("azure_client_id", "AZURE_CLIENT_ID"),
                  ("azure_tenant_id", "AZURE_TENANT_ID")),
        register_at="https://portal.azure.com → App registrations",
    ),
    _Known(
        key="google", label="Google",
        domains=("mail", "calendar"),
        requires=(("google_client_secrets_file", "GOOGLE_CLIENT_SECRETS_FILE"),),
        register_at="https://console.cloud.google.com → APIs & Services → Credentials",
    ),
    _Known(
        key="github", label="GitHub",
        domains=("repos",),
        register_at="https://github.com/settings/developers",
        signin_step=("Create a token at https://github.com/settings/tokens and "
                     "paste it here — no app to register."),
        probe=("list_assigned_issues", "assigned issue"),
        verifies_at_call_time=True,
    ),
    _Known(
        key="slack", label="Slack",
        domains=("chat",),
        register_at="https://api.slack.com/apps",
        probe=("list_channels", "channel"),
        verifies_at_call_time=True,
    ),
)

_BY_KEY = {k.key: k for k in KNOWN}


def _mock_m365(settings: ConnectorServiceSettings) -> bool:
    return getattr(settings, "m365_connector", "mock") == "mock"


def probe_for(key: str) -> tuple[str, str] | None:
    """(method name, noun) that proves this connector works, or None."""
    known = _BY_KEY.get(key)
    return known.probe if known else None


def describe(
    settings: ConnectorServiceSettings | None = None,
    registry: ConnectorRegistry | None = None,
    enabled: set[str] | None = None,
    signed_in: set[str] | None = None,
) -> list[ConnectorInfo]:
    """Describe every known connector, enabled or not.

    `enabled` overrides the configured list — that is how the owner's own
    choice (persisted, see `connector_prefs`) reaches this without the
    environment having to be rewritten and the process restarted.
    """
    s = settings or ConnectorServiceSettings()
    on = enabled if enabled is not None else set(s.enabled_connector_list)
    built = registry.health() if registry is not None else {}

    out: list[ConnectorInfo] = []
    for known in KNOWN:
        out.append(_describe_one(known, s, on, built, signed_in))
    return out


def _describe_one(
    known: _Known,
    s: ConnectorServiceSettings,
    on: set[str],
    built: dict[str, str],
    signed_in: set[str] | None = None,
) -> ConnectorInfo:
    def info(status: str, detail: str, next_step: str = "",
             missing: tuple[str, ...] = ()) -> ConnectorInfo:
        return ConnectorInfo(
            key=known.key, label=known.label, domains=known.domains,
            status=status, detail=detail, next_step=next_step, missing=missing,
        )

    if known.key not in on:
        return info(
            NOT_ENABLED,
            "Switched off — AURA will not use it and never asks it anything.",
            "Switch it on here; that is enough to start the sign-in.",
        )

    # m365 has a mock that needs no credentials at all, so it is checked before
    # the credential gate — otherwise the demo setup would report itself broken.
    if known.key == "m365" and _mock_m365(s):
        # U295: this used to read "Set M365_CONNECTOR=workiq and register an
        # Azure app for the real one" — an environment variable, in a panel
        # meant for the person who owns the household. Asked as "don't we have
        # more user friendly ways to connect? this is really dev like".
        return info(
            MOCK,
            "Showing example data, not your real mail or calendar.",
            "Connect your Microsoft account to see the real thing.",
        )

    missing = tuple(env for attr, env in known.requires if not getattr(s, attr, ""))
    if missing:
        # U295: the same fact, without the environment-variable names. What
        # the owner needs to know is that signing in is not possible yet and
        # that one value fixes it; WHICH variable holds it is our business,
        # and still travels in `missing` for anyone debugging.
        if known.missing_copy:
            return info(NO_CREDENTIALS, *known.missing_copy, missing=missing)
        return info(
            NO_CREDENTIALS,
            f"{known.label} needs a one-time app ID before you can sign in. "
            f"It is free, and you only do it once.",
            f"Create one at {known.register_at}, then paste it in the field here."
            if known.register_at else "One setting is still missing.",
            missing,
        )

    status = built.get(known.key)
    # U254b: a connector whose credential is only read at call time constructs
    # fine with no account whatsoever, so "it built" proves nothing. GitHub and
    # Slack both reported `connected — real calls are going out` while holding
    # no token at all. Ask whether a token actually exists; when we cannot ask,
    # say "not signed in" rather than claim a connection.
    if status == OK and known.verifies_at_call_time:
        if signed_in is None or known.key not in signed_in:
            return info(
                UNAUTHENTICATED,
                "Switched on, but no token is stored — so there is no account "
                "to ask.",
                known.signin_step,
            )
    if status in (OK, MOCK):
        return info(
            status,
            "Connected — real calls are going out."
            if status == OK else "Answering with canned data.",
        )
    if status == UNAVAILABLE:
        return info(
            UNAVAILABLE,
            "Configured, but it failed to start. The app log says why.",
            "Check the app log in Activity.",
        )
    return info(
        UNAUTHENTICATED,
        "Ready, but nobody has signed in yet — so there is no account to ask.",
        known.signin_step,
    )


def live_domains(infos: list[ConnectorInfo]) -> set[str]:
    """Which domains AURA can actually serve right now.

    This is what makes an enabled connection real to the assistant: the tool
    layer asks this before offering mail or calendar tools, so a connector
    that is switched on and signed in CHANGES WHAT HE CAN DO, and one that is
    off does not leave him promising mail he cannot read.
    """
    out: set[str] = set()
    for info in infos:
        if info.live:
            out.update(info.domains)
    return out


def known_keys() -> tuple[str, ...]:
    return tuple(k.key for k in KNOWN)


def label_for(key: str) -> str:
    known = _BY_KEY.get(key)
    return known.label if known else key
