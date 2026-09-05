---
feature: "022-security-and-privacy"
---

# Tasks: Security and Privacy

Retro-specified. Item numbers (S1, S2, …) refer to `docs/audit-2026-08.md`.

## Phase 1: Keep it off the LAN

- [x] T001 [U215, S1] Bind loopback by default
- [x] T002 [U215, S4] TrustedHost + Origin guard against DNS rebinding
- [x] T003 [U220, S5] Shared secret on the Pi; every brain→robot client sends it
- [x] T004 [U226, S12] Discovery endpoints POST + JSON, so a cross-origin scan preflights

## Phase 2: Keep the secrets secret

- [x] T005 [U221, S3] Console asks `/identity/status` instead of fetching a token
- [x] T006 [U226, S3] Delete `GET /identity/token/...` entirely
- [x] T007 [U221, S14] Constant-time unlock compare + exponential backoff
- [x] T008 [U225, S10] Passphrase into the OS credential store
- [x] T009 [U225, S9] Random per-install salt, scrypt n=2^17, 12-char minimum, in-place rotation
- [x] T010 [U221, S15] `EXTERNAL_ALLOW` for `shell.openExternal`; DevTools unpackaged only

## Phase 3: Keep bad input from becoming instructions

- [x] T011 [U215, S2] Sanitise newlines and keys before persisting to `.env`
- [x] T012 [U226, S7] Refuse link-local targets, host names resolved
- [x] T013 [U121] Path traversal in skill/scenario names; argv + allow-list subprocesses
- [x] T014 [U215, S6] `/recognition/merge` requires `confirm=<id>`
- [x] T015 [U226] Stop leaking a mediapipe model

## Phase 4: Keep it out of git

- [x] T016 [U167] `privacy_scan.py`: pre-commit hook + whole-tree CI + its own tests
- [x] T017 [U182, U183] Scrub the public history; verify the tokenless update check
