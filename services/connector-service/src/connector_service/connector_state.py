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


# Registered here rather than discovered, because "which connectors exist" is
# a product decision: an owner should see Slack listed and switched off, not
# be left wondering whether AURA has heard of it.
KNOWN: tuple[_Known, ...] = (
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
    ),
    _Known(
        key="slack", label="Slack",
        domains=("chat",),
        register_at="https://api.slack.com/apps",
    ),
)

_BY_KEY = {k.key: k for k in KNOWN}


def _mock_m365(settings: ConnectorServiceSettings) -> bool:
    return getattr(settings, "m365_connector", "mock") == "mock"


def describe(
    settings: ConnectorServiceSettings | None = None,
    registry: ConnectorRegistry | None = None,
    enabled: set[str] | None = None,
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
        out.append(_describe_one(known, s, on, built))
    return out


def _describe_one(
    known: _Known,
    s: ConnectorServiceSettings,
    on: set[str],
    built: dict[str, str],
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
        return info(
            MOCK,
            "Answering with canned data — a demo account, not your mail.",
            "Set M365_CONNECTOR=workiq and register an Azure app for the real one.",
        )

    missing = tuple(env for attr, env in known.requires if not getattr(s, attr, ""))
    if missing:
        return info(
            NO_CREDENTIALS,
            f"Switched on, but {' and '.join(missing)} is not set, so a sign-in "
            f"cannot even start.",
            f"Register an app at {known.register_at}, then paste its id here."
            if known.register_at else "Set the missing values.",
            missing,
        )

    status = built.get(known.key)
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
        "Press Connect and complete the device-code sign-in.",
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
