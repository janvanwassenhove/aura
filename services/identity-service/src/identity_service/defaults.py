"""Default OAuth app credentials for zero-config development.

These are pre-registered dev OAuth apps owned by the AURA project.
They enable "click Connect and sign in" without any configuration.

Users can override these by setting the corresponding env vars
(AZURE_CLIENT_ID, GOOGLE_CLIENT_ID, GITHUB_CLIENT_ID, etc.).

SECURITY NOTE: These are *public* client_ids intended for device-code flows.
Shipping them in code is an established industry pattern (gh CLI, VS Code,
Azure CLI all do this). The client_secret for Google is required by the
device code token exchange but is NOT a secret that grants access on its own —
it only works in combination with user consent via the device code flow.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Microsoft Azure AD — Multi-tenant app, public client flows enabled
# Permissions: Graph delegated — Calendars.Read, Mail.ReadWrite, Mail.Send,
#              Tasks.ReadWrite, ChannelMessage.Send, offline_access
# ---------------------------------------------------------------------------
MICROSOFT_CLIENT_ID = ""  # TODO: paste after registering Azure app
MICROSOFT_TENANT_ID = "common"  # "common" = multi-tenant + personal accounts
MICROSOFT_CLIENT_SECRET = ""  # needed for token refresh via ConfidentialClientApp

# ---------------------------------------------------------------------------
# Google — "TVs and Limited Input Devices" OAuth client
# Scopes: calendar.readonly, gmail.readonly, gmail.send
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = ""  # TODO: paste after registering Google OAuth client
GOOGLE_CLIENT_SECRET = ""  # required for device code token exchange

# ---------------------------------------------------------------------------
# GitHub — OAuth App with Device Flow enabled
# Scopes: repo, read:org
# No client_secret needed for device code flow.
# ---------------------------------------------------------------------------
GITHUB_CLIENT_ID = ""  # TODO: paste after registering GitHub OAuth App
