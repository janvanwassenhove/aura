---
feature: "014-zero-config-oauth"
status: "in-progress"
owner: "identity-service"
priority: P1
risk: Low
created: "2026-05-01"
---

# Feature Specification: Zero-Config OAuth Connections

**Feature Branch**: `014-zero-config-oauth`
**Created**: 2026-05-01
**Status**: In Progress
**Owner**: identity-service
**Priority**: P1
**Risk**: Low

## User Scenarios & Testing

### User Story 1 — Connect to Microsoft M365 with One Click (Priority: P1)

The operator clicks "Connect" on the Microsoft M365 card, sees a device code and verification URL, signs in on any browser, and the connection is established — without ever editing a config file or registering an Azure app.

**Why this priority**: Primary work connector. Currently requires manual Azure App registration + `.env` editing — a 15-minute multi-portal workflow that blocks first-time setup.

**Independent Test**: Start with blank AZURE env vars; call `POST /identity/auth/microsoft/start`; assert a device code and verification URI are returned (using the shipped default client_id).

**Acceptance Scenarios**:

1. **Given** no AZURE_CLIENT_ID in env, **When** `POST /identity/auth/microsoft/start` is called, **Then** the default dev client_id is used and a device code response is returned (no 503).
2. **Given** a device code flow is started, **When** the user completes sign-in at the verification URL, **Then** `POST /identity/auth/microsoft/poll` returns success and the token is stored.
3. **Given** `AZURE_CLIENT_ID` is set in env to a custom value, **When** `POST /identity/auth/microsoft/start` is called, **Then** the custom client_id is used (enterprise override).
4. **Given** a stored Microsoft token, **When** the identity-service container restarts, **Then** the token is still available (persisted in `/data` volume).

---

### User Story 2 — Connect to Google Workspace with One Click (Priority: P1)

The operator clicks "Connect" on the Google card, sees a device code and verification URL (google.com/device), signs in, and the connection is established — without uploading a client_secrets.json file.

**Why this priority**: Eliminates the most complex setup step (downloading JSON, mounting into container, setting env var path).

**Independent Test**: Start with blank GOOGLE env vars; call `POST /identity/auth/google/start`; assert a device code and verification URI are returned.

**Acceptance Scenarios**:

1. **Given** no GOOGLE_CLIENT_SECRETS_FILE in env, **When** `POST /identity/auth/google/start` is called, **Then** the default dev client_id/secret is used and a device code response is returned.
2. **Given** a device code flow is started, **When** the user completes sign-in at google.com/device, **Then** `POST /identity/auth/google/poll` returns success and the token is stored.
3. **Given** Google auth completed, **When** `GET /identity/token/{user}/google` is called, **Then** a valid access token is returned.
4. **Given** a Google token near expiry, **When** `GET /identity/token/{user}/google` is called, **Then** the token is silently refreshed using the stored refresh_token.

---

### User Story 3 — Connect to GitHub with One Click (Priority: P1)

The operator clicks "Connect" on the GitHub card, sees a code and github.com/login/device URL, authorizes there, and the connection is established — without generating a Personal Access Token.

**Why this priority**: PAT workflow requires navigating GitHub settings, choosing scopes manually, and pasting. Device Code is much simpler.

**Independent Test**: Call `POST /identity/auth/github/start`; assert an 8-char user code and `https://github.com/login/device` verification URI are returned.

**Acceptance Scenarios**:

1. **Given** default config, **When** `POST /identity/auth/github/start` is called, **Then** a device code response with user_code and verification_uri is returned.
2. **Given** a device code flow is started, **When** the user authorizes at github.com/login/device, **Then** `POST /identity/auth/github/poll` returns success and the token is stored.
3. **Given** GitHub auth completed, **When** `GET /identity/token/{user}/github` is called, **Then** the access token is returned.
4. **Given** the user prefers a PAT, **When** `PUT /identity/token/{user}/github` is called with a token, **Then** the PAT is stored (fallback path preserved).

---

### User Story 4 — Slack Connection (Keep Current UX) (Priority: P3)

Slack bot tokens cannot be obtained via OAuth Device Code. The current "paste bot token" UX remains, with improved inline help.

**Acceptance Scenarios**:

1. **Given** the Connections tab, **When** the user pastes a `xoxb-…` token and clicks Save, **Then** the token is stored and status shows "Connected".

---

### Edge Cases

- What happens when the default OAuth app is rate-limited? → User sees clear error message suggesting retry.
- What happens when Google Device Code scopes are insufficient for a future feature? → Existing tokens remain valid; new scopes require re-auth.
- What happens when the user's org blocks device code flow? → Error message suggests using env var override with a custom app.
- What happens when the device code expires before user signs in? → Error "Code expired — click Connect to try again."

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST ship default OAuth app client_ids that work without any user configuration.
- **FR-002**: System MUST use Device Code flow for Microsoft, Google, and GitHub.
- **FR-003**: System MUST allow env var overrides for all OAuth credentials (enterprise support).
- **FR-004**: System MUST persist tokens across container restarts (via /data volume).
- **FR-005**: System MUST NOT log any client secrets or access tokens.
- **FR-006**: GitHub Device Code flow MUST NOT require a client_secret.
- **FR-007**: Google Device Code flow MUST support calendar.readonly, gmail.readonly, gmail.send scopes.
- **FR-008**: System MUST provide a `GET /identity/config` endpoint reporting provider readiness (no secrets exposed).
- **FR-009**: The PAT input for GitHub MUST remain as a fallback option in the UI.

### Key Entities

- **OAuthDefaults**: Shipped client_ids/secrets for dev OAuth apps (one per provider).
- **DeviceCodeFlow**: Common pattern — start returns (user_code, verification_uri, flow_id); poll completes or times out.
- **ProviderConfig**: Per-provider readiness state exposed via `GET /identity/config`.

---

## Success Criteria

- **SC-001**: A fresh install (blank .env) can connect to Microsoft, Google, and GitHub without editing any files.
- **SC-002**: The Connect flow for each provider completes in < 60 seconds (excluding user sign-in time).
- **SC-003**: Env var overrides are respected when set (enterprise path works).
- **SC-004**: No secrets appear in any log output at any level.

---

## Assumptions

- The AURA project maintainer has registered OAuth apps on Azure, Google, and GitHub (one-time task).
- The default OAuth apps are configured for multi-tenant / public use.
- The `/data` volume is mounted for identity-service in Docker Compose (already the case).
- Google "TVs and Limited Input Devices" client type supports the required Gmail/Calendar scopes.

---

## References

- ADR-006: M365 Connector
- `.specify/specs/010-connector-skeletons/spec.md`
- Constitution: principles VI (no secrets in logs), VII (simplicity)
- GitHub Device Flow docs: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow
- Google Device Flow: https://developers.google.com/identity/protocols/oauth2/limited-input-device
- Microsoft Device Code: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
