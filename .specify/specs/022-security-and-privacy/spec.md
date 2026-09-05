---
feature: "022-security-and-privacy"
status: "implemented"
owner: "cross-cutting"
priority: P1
risk: High
created: "2026-09-05"
units: [U121, U167, U182, U183, U215, U220, U221, U225, U226, U224]
amended: "2026-09-05"
---

# Feature Specification: Security and Privacy

**Feature Branch**: `022-security-and-privacy`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented; the audit backlog in
[`docs/audit-2026-08.md`](../../../docs/audit-2026-08.md) is the live tracker.
**Owner**: cross-cutting
**Priority**: P1
**Risk**: **High**, and asymmetric. Everything else in this repository can be
fixed by the next release. A knowledge store read off the LAN, or a family
member's data in a public git history, cannot be.

## Background

AURA holds face embeddings, long-term memory about a household including
children, OAuth tokens for the owner's mail and calendar, and the ability to
drive their laptop. It runs on a laptop in a home, on a LAN with a television
and a printer and whatever else, and its robot half is a Raspberry Pi with a
camera and a microphone.

Two audits (U121, and the four-track audit in August recorded in
`docs/audit-2026-08.md`) and a public-repository review (U182, U183) drove the
work below. The constitution states the principle — *no sensitive data in logs*
— but the threat model is wider than logging, and this spec records it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Nothing on the LAN can read the household (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the brain, **When** it binds, **Then** it binds **loopback** by
   default. It used to bind `0.0.0.0:8020` with no auth on any endpoint, which
   handed any LAN neighbour the knowledge store, the OAuth tokens and an RCE
   chain (S1, U215).
2. **Given** a request from another origin, **When** it arrives, **Then** Host
   and Origin are validated — CORS alone is defeated by DNS rebinding (S4,
   U215).
3. **Given** the robot runtime on the Pi, **When** it is reached, **Then** an
   opt-in shared secret is required (`ROBOT_SHARED_SECRET`, `hmac.compare_digest`,
   `/health` and docs exempt), and every brain→robot client sends it. It is
   still bound to the LAN by design — the brain is on a different host (S5,
   U220).
4. **Given** the discovery endpoints, **When** they are called, **Then** they
   are POST with a JSON content type, so a cross-origin scan hits a CORS
   preflight and the Origin guard refuses it before any port is touched (S12,
   U226).

### User Story 2 — A token never reaches a place it is not needed (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the console needs to colour a badge, **When** it asks, **Then** it
   calls `/identity/status` — it used to fetch the **raw OAuth access token**
   into the browser to decide whether a dot was green (U221), and the route
   that served it had no auth at all (S3). That route is **deleted**: the brain
   and connector-service take tokens in-process via `get_valid_token`, and the
   console stores and revokes with PUT/DELETE (U226).
2. **Given** the unlock endpoint, **When** a passphrase is tried, **Then** the
   comparison is constant-time and five failures trigger exponential backoff
   (429 with `retry_after_s`) — it was a free oracle (S14, U221).
3. **Given** Electron, **When** a renderer asks to open a URL, **Then** it must
   be on `EXTERNAL_ALLOW`, and DevTools exist only in unpackaged builds (S15,
   U221).

### User Story 3 — The owner's key is protected by the operating system (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the knowledge passphrase, **When** it is stored, **Then** it lives
   in the OS credential store (Windows Credential Manager, DPAPI-protected by
   the Windows login), **not** in `.env` beside the ciphertext it protects
   (S10, U225). `KNOWLEDGE_PASSPHRASE` still wins when explicitly set, for
   docker, CI and headless.
2. **Given** key derivation, **When** it runs, **Then** the salt is random per
   install and stored in `key-params.json` beside the ciphertext, scrypt runs
   at n=2^17, and the minimum passphrase is 12 characters. The old static salt
   `aura-knowledge00` at n=2^14 with an 8-character minimum is gone, and
   existing installs **rotate in place on boot** — DEKs rewrapped, embeddings
   re-encrypted (S9, U225).
3. **Given** there is no recovery path, **When** the passphrase is lost,
   **Then** the profiles and face data are lost with it. This is stated in
   `CLAUDE.md` and in
   [018](../018-knowledge-people-and-judgment/spec.md) because it is a real
   consequence of the design, not an oversight.

### User Story 4 — Personal data cannot ride along with a commit (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a staged commit, **When** the pre-commit hook runs, **Then**
   `scripts/privacy_scan.py --staged` refuses personal or sensitive data
   (U167).
2. **Given** a push, **When** CI runs, **Then** the same scanner runs over the
   **whole tree**, so `--no-verify` locally is still caught (U167).
3. **Given** the repository became public, **When** it did, **Then** the
   history was scrubbed and re-checked, and the scanner prevents its return
   (U182, U183).
4. **Given** the scanner itself, **When** it changes, **Then** its own tests
   run in CI (`scripts/test_privacy_scan.py`).

### User Story 5 — An input never becomes an instruction (Priority: P1)

**Acceptance Scenarios**:

1. **Given** `/setup/prefs` or `/robot/address`, **When** a value is persisted
   to `.env`, **Then** newlines and keys are sanitised — an unescaped newline
   was env-var injection, and therefore RCE on the next launch (S2, U215).
2. **Given** `/robot/address`, **When** a target is resolved, **Then**
   link-local ranges (`169.254.0.0/16`, `fe80::/10` — where cloud metadata
   lives) are refused, host names included. The private LAN and loopback stay
   allowed by design (S7, U226).
3. **Given** a skill or scenario name, **When** it is used as a path, **Then**
   a regex blocks traversal (U121).
4. **Given** any subprocess, **When** it runs, **Then** it uses an argv list
   and an allow-list — never `shell=True` (U121).
5. **Given** `/recognition/merge`, **When** it would erase a person, **Then**
   it requires `confirm=<id>` (S6, U215).

### User Story 6 — Deleting a person really deletes them (Priority: P1)

1. **Given** a person is forgotten, **When** they are, **Then** their key is
   destroyed, leaving unreadable ciphertext, and their face data goes too
   (U244, [018](../018-knowledge-people-and-judgment/spec.md)).

## Functional Requirements

- **FR-001**: The brain binds loopback by default; the robot runtime is guarded
  by an opt-in shared secret.
- **FR-002**: No endpoint returns a live access token. Tokens move in-process.
- **FR-003**: The owner key derives from a passphrase in the OS credential
  store, with a per-install random salt at scrypt n=2^17.
- **FR-004**: Encryption is AES-256-GCM with a per-write random nonce and AAD
  binding.
- **FR-005**: Personal data cannot enter git: hook plus CI, with the scanner
  under test.
- **FR-006**: Values persisted to `.env` are sanitised; outbound targets refuse
  link-local; paths refuse traversal; subprocesses use argv and an allow-list.
- **FR-007**: Anything destructive requires explicit confirmation.
- **FR-008**: Verified-OK areas listed in `docs/audit-2026-08.md` are not
  re-audited without a reason: Electron core hardening, `yaml.safe_load`
  everywhere, no `eval`, no secrets in responses or logs, `.env` gitignored.

## Out of scope

- The approval gate on tool calls — that is
  [019-skills-and-automation](../019-skills-and-automation/spec.md) and
  constitution IV.
- Role-based disclosure between household members — that is
  [018-knowledge-people-and-judgment](../018-knowledge-people-and-judgment/spec.md)
  and ADR-008 §10.

## Traceability

| Units | What they delivered |
|---|---|
| U121 | First audit: path traversal, SSRF, unsafe CORS |
| U167 | The privacy gate — hook + CI, with the scanner under test |
| U182, U183 | Public-repository review: history scrubbed, return prevented, tokenless update check verified |
| U215 | S1, S2, S4, S6 — loopback default, `.env` injection, Host/Origin guard, confirmed merge |
| U220 | S5 — shared secret between brain and robot |
| U221 | S3 (console side), S14, S15 — no tokens in the browser, the unlock oracle closed, Electron links gated |
| U225 | S9, S10 — owner key out of `.env`, modern KDF parameters, in-place rotation |
| U226 | S3 (route deleted), S7, S12, and a leaked mediapipe model |
