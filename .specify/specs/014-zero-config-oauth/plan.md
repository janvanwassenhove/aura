---
feature: "014-zero-config-oauth"
---

# Implementation Plan: Zero-Config OAuth

**Branch**: `014-zero-config-oauth` | **Date**: 2026-05-01 | **Spec**: `.specify/specs/014-zero-config-oauth/spec.md`

## Summary

Ship pre-registered OAuth app credentials as code defaults. Add Device Code flow for GitHub and Google. Remove the 503 "not configured" guards — Connect always works out of the box. Env vars override defaults for enterprise use.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript (frontend)
**Primary Dependencies**: FastAPI, MSAL, httpx (GitHub/Google HTTP), Pydantic v2, Vue 3 + Pinia
**Storage**: CryptfileTokenStore (encrypted keyring at /data/keyring.cfg)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Docker (Podman)
**Performance Goals**: Device code start < 2s; poll completes immediately after user sign-in
**Constraints**: No client_secrets in logs; Google device flow requires client_secret for token exchange

## Constitution Check

- [x] Hardware abstraction respected — no Reachy SDK imports
- [x] Sensitive data excluded from logs — secrets in defaults.py are never logged; tokens in keyring only
- [x] Events emitted for all state changes — AuthCompleted event on successful connection
- [x] Approval gate not applicable — auth is user-initiated, not a tool call
- [x] Test coverage planned for all acceptance criteria

## Project Structure

### Source Code

```text
services/identity-service/src/identity_service/
├── defaults.py              ← NEW: shipped OAuth client_ids
├── auth_github.py           ← NEW: GitHub Device Code flow
├── auth_google.py           ← REWRITE: Device Code replaces InstalledAppFlow
├── auth_microsoft.py        ← UNCHANGED (already uses Device Code)
├── main.py                  ← UPDATE: use defaults, add GitHub endpoints, add /config
└── token_store.py           ← UNCHANGED

packages/shared-config/src/shared_config/
└── identity.py              ← UPDATE: add github/google client_id fields

apps/operator-console/src/
├── stores/connectionsStore.ts  ← UPDATE: add GitHub/Google device code actions
└── components/SettingsPanel.vue ← UPDATE: unified device code UX
```

## Implementation Steps

### Phase 1: Backend Core

1. Create `defaults.py` — contains `DEFAULTS` dict with client_ids per provider (placeholder values until apps registered)
2. Update `IdentityServiceSettings` — add `github_client_id`, `google_client_id`, `google_client_secret` fields
3. Create `auth_github.py` — `GitHubDeviceCodeFlow` class:
   - `start(client_id, scopes)` → POST github.com/login/device/code → returns {user_code, verification_uri, device_code, interval}
   - `poll(client_id, device_code, interval)` → POST github.com/login/oauth/access_token → returns access_token or pending/expired
4. Rewrite `auth_google.py` — `GoogleDeviceCodeFlow` class:
   - `start(client_id, scopes)` → POST oauth2.googleapis.com/device/code → returns {user_code, verification_url, device_code, interval}
   - `poll(client_id, client_secret, device_code, interval)` → POST oauth2.googleapis.com/token → returns access_token + refresh_token
   - `refresh(client_id, client_secret, refresh_token)` → silent refresh
5. Update `main.py`:
   - `_ms_flow()`: use `defaults.DEFAULTS["microsoft"]` when env vars blank (no more 503)
   - `_google_flow()`: new device code pattern using defaults
   - Add `POST /identity/auth/github/start` and `POST /identity/auth/github/poll`
   - Add `POST /identity/auth/google/start` (device code version) and `POST /identity/auth/google/poll`
   - Add `GET /identity/config` — returns `{microsoft: {ready: true}, google: {ready: true}, github: {ready: true}}`

### Phase 2: Frontend

6. Update `connectionsStore.ts`:
   - Add `startGitHubAuth()` / `pollGitHubAuth()` (mirrors Microsoft pattern)
   - Update `startGoogleAuth()` to use device code pattern (POST /start → show code → POST /poll)
   - Remove `needsSetup` logic (Connect always works)
7. Update `SettingsPanel.vue`:
   - Microsoft: remove setup wizard (keep device code UI as-is)
   - Google: convert to device code card (code + verification URL + "Done" button)
   - GitHub: replace PAT input with device code card + small "Use PAT instead" link
   - Slack: keep as-is

### Phase 3: Test & Deploy

8. Add unit tests for `auth_github.py` and `auth_google.py` (mock HTTP calls)
9. Rebuild identity-service + operator-console
10. End-to-end verification

## Complexity Tracking

No constitution violations.
