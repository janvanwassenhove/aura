---
feature: "014-zero-config-oauth"
---

# Tasks: Zero-Config OAuth

**Prerequisites**: `plan.md` (done), `spec.md` (done)

## Phase 1: Backend Core

- [ ] T001 [US1,2,3] Create `services/identity-service/src/identity_service/defaults.py` with DEFAULTS dict
- [ ] T002 [P] [US1,2,3] Update `packages/shared-config/src/shared_config/identity.py` — add github_client_id, google_client_id, google_client_secret fields
- [ ] T003 [US3] Create `services/identity-service/src/identity_service/auth_github.py` — GitHubDeviceCodeFlow class
- [ ] T004 [US2] Rewrite `services/identity-service/src/identity_service/auth_google.py` — Device Code flow
- [ ] T005 [US1,2,3] Update `services/identity-service/src/identity_service/main.py`:
  - Remove 503 guards in `_ms_flow()` / `_google_flow()` — use defaults
  - Add `POST /identity/auth/github/start` + `POST /identity/auth/github/poll`
  - Replace Google `/start` endpoint with device code version + add `/poll`
  - Add `GET /identity/config`

**Checkpoint**: All backend endpoints work with default credentials

---

## Phase 2: Frontend

- [ ] T006 [P] [US1,2,3] Update `apps/operator-console/src/stores/connectionsStore.ts`:
  - Add `startGitHubAuth()` / `pollGitHubAuth()`
  - Rewrite `startGoogleAuth()` to device code pattern
  - Remove `needsSetup` flag and related logic
- [ ] T007 [US1,2,3,4] Update `apps/operator-console/src/components/SettingsPanel.vue`:
  - Microsoft: remove setup wizard panel (Connect always works)
  - Google: convert to device code UI (code + verification URL + Done button)
  - GitHub: convert to device code UI + "Use PAT instead" link
  - Slack: add better inline help (keep token paste UX)

**Checkpoint**: UI shows device code flow for MS/Google/GitHub

---

## Phase 3: Deploy & Verify

- [ ] T008 Rebuild identity-service: `start.ps1 -Build identity-service`
- [ ] T009 Rebuild operator-console: `start.ps1 -Build operator-console`
- [ ] T010 End-to-end test: verify all providers show device code flow on Connect

---

## Dependencies & Execution Order

- T001, T002 can run in parallel (different packages)
- T003, T004 depend on T001 (import defaults)
- T005 depends on T001, T002, T003, T004
- T006, T007 depend on T005 (need endpoints live)
- T008, T009 depend on T006, T007
- T010 depends on T008, T009

## Notes

- Placeholder client_ids in defaults.py until OAuth apps are registered
- [P] = parallelizable with prior task in same phase
