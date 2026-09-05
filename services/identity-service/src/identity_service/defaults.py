"""Shipped OAuth client ids — the "zero-config" half of spec 014.

When these are filled in, connecting is one click for **every** install: press
Connect, sign in with the code, done. When they are empty (the state today), the
owner pastes their own id once per install, guided by the walkthrough in the
Connections panel (U314).

---------------------------------------------------------------------------
FILLING THESE IN — the whole remaining task, once, for the project
---------------------------------------------------------------------------

This is the only thing standing between here and true zero-config, and it needs
somebody's actual accounts, which is why no unit has done it. Each takes a few
minutes.

**MICROSOFT_CLIENT_ID**
  1. https://portal.azure.com → Microsoft Entra ID → App registrations → New
  2. Name: AURA. Supported account types: *"Accounts in any organizational
     directory and personal Microsoft accounts"* — this one matters; the
     single-tenant default locks out every home account.
  3. Leave the redirect URI empty. Register.
  4. Authentication → Advanced settings → **Allow public client flows: Yes**.
     Device code will not work without it.
  5. API permissions → Microsoft Graph → Delegated: `Calendars.Read`,
     `Mail.ReadWrite`, `Mail.Send`, `Tasks.ReadWrite`, `ChannelMessage.Send`,
     `offline_access`.
  6. Copy "Application (client) ID" below.

**GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET**
  1. https://console.cloud.google.com/apis/credentials/oauthclient
  2. Application type: **"TVs and Limited Input devices"** — the device-code
     client. Any other type expects a browser redirect a robot cannot do.
  3. Scopes: `calendar.readonly`, `gmail.readonly`, `gmail.send`.
  4. Copy the client id and secret below.

**GITHUB_CLIENT_ID**
  1. https://github.com/settings/developers → New OAuth App
  2. Enable **Device Flow**. Scopes: `repo`, `read:org`.
  3. Copy the Client ID below. No secret is needed for device flow.

---------------------------------------------------------------------------
SECURITY
---------------------------------------------------------------------------

These are *public* client ids, intended for device-code flows and shipped in
code by the same established pattern the `gh`, Azure and VS Code CLIs use:
possession of the id grants nothing. The Google client secret is required by
the device-code token exchange and is not a secret that grants access on its
own — it only works together with a user consenting to a device code.

A **half-filled** entry is worse than an empty one: it produces an opaque
failure at sign-in rather than the honest "not configured yet" the panel shows.
`tests/test_defaults.py` fails on that, so an incomplete paste is caught here
rather than by an owner in a living room (constitution XI).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Microsoft Azure AD — multi-tenant, public client flows enabled
# ---------------------------------------------------------------------------
MICROSOFT_CLIENT_ID = ""           # a GUID; see the header
MICROSOFT_TENANT_ID = "common"     # "common" = work + personal accounts
MICROSOFT_CLIENT_SECRET = ""       # optional: only for confidential refresh

# ---------------------------------------------------------------------------
# Google — "TVs and Limited Input Devices" OAuth client
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = ""              # ends in .apps.googleusercontent.com
GOOGLE_CLIENT_SECRET = ""          # required by the device-code exchange

# ---------------------------------------------------------------------------
# GitHub — OAuth App with Device Flow enabled
# ---------------------------------------------------------------------------
GITHUB_CLIENT_ID = ""              # starts with "Iv1." or "Ov23"


def shipped() -> dict[str, bool]:
    """Which providers ship a usable default. Used by the setup status so the
    console can say "one click" or "paste an id" without guessing."""
    return {
        "microsoft": bool(MICROSOFT_CLIENT_ID and MICROSOFT_TENANT_ID),
        "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "github": bool(GITHUB_CLIENT_ID),
    }
