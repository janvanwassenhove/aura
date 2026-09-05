---
feature: "020-desktop-app-and-releases"
status: "implemented"
owner: "apps/desktop + CI"
priority: P1
risk: High
created: "2026-09-05"
units: [U32, U33, U44, U55, U56, U151, U152, U166, U168, U168b, U168c, U168d, U168e, U169, U169b, U170, U171, U172, U173, U174, U176, U177, U178, U192, U193, U197, U201, U211, U228, U229, U230, U231, U232, U233, U234, U235, U236, U283, U284, U285, U285b, U297, U179, U184, U185, U186, U210, U317]
amended: "2026-09-05"
---

# Feature Specification: The Desktop App and its Releases

**Feature Branch**: `020-desktop-app-and-releases`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: `apps/desktop` (Electron), `.github/workflows/release.yml`, `scripts/`
**Priority**: P1
**Risk**: **High.** An update that fails, or that takes the owner's data with
it, is the only defect class in this repository that cannot be fixed by the
next release.

## Background

AURA is not a set of containers an operator runs. It is **one window** the owner
installs: the Electron shell starts the brain, the robot runtime client and the
console together (U32). Everything else in this spec follows from that: a
household installs a build, so the build has to arrive, install itself, and
leave their data where it was.

Every push to `master` produces a release (U166): version, notes, screenshots
and installers for Windows, macOS (arm64 and x64) and Linux.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — An update installs itself and does not eat anything (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a newer release exists, **When** the app checks, **Then** it says
   so in-app (U172, U173) — and the check is not silent. U178: a private repo
   with no token meant "no update" was indistinguishable from "no answer", and
   nothing was said either way.
2. **Given** an update installs, **When** it does, **Then** the owner's people,
   memories, keys and settings survive. U177 is the reason this is FR-001:
   **all owner state lived inside the install directory**, so every update
   wiped it.
3. **Given** an installer has been downloaded, **When** it is about to run,
   **Then** it is verified first (U224).
4. **Given** the update has installed, **When** it finishes, **Then** the app
   comes back. U201: it installed perfectly and never relaunched, which from
   the owner's side is identical to a failed update. U197 verified the whole
   path on the real machine.
5. **Given** a release, **When** it is built, **Then** the version comes from
   the commit markers themselves (U172), and the installer contains every
   module it needs — U176 (`updater.cjs` unpackaged, crash on launch), U235 (a
   missing module), U174 (the icons were never in git).

### User Story 2 — The release page is for the person installing it (Priority: P2)

**Acceptance Scenarios**:

1. **Given** a release, **When** the notes are generated, **Then** they are in
   **English** (U285), built from the commit subjects — which are already one
   sentence per unit in the right language and the right granularity (the
   previous version scraped a ledger format retired around U180 and had been
   rendering an empty section for months).
2. **Given** a single change, **When** the page is written, **Then** it reads
   "one improvement", not "1 improvement, each one from …" (U285b).
3. **Given** the release, **When** it is published, **Then** it carries
   screenshots, captured from a throwaway demo stack — fake robot, echo model,
   one fictional persona — so no personal data *can* appear in them (U230,
   U236, U297).
4. **Given** the screenshot job fails, **When** it does, **Then** the release
   still goes out and the page **says** the screenshots are missing (U235's
   rule). An absence nobody can see is a blind spot, not a degradation.

### User Story 3 — CI tells the truth about the build (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a push, **When** CI runs, **Then** it runs with **no API keys**.
   U283: three tests depended on `OPENAI_API_KEY` being present in a developer
   shell; CI was red for six hours while the local run was green and I reported
   green.
2. **Given** a test that passes locally, **When** it runs on Linux, **Then** it
   still passes — U168b (Linux-only failures), U168c (an import-order race on
   `LLM_PROVIDER=echo`), U168d (`update_config()` mutating a singleton no
   fixture restored), U168e (two tests relying on Windows' coarse clock).
3. **Given** a flaky test, **When** it blocks a release, **Then** it is fixed
   rather than retried (U190, U210).
4. **Given** the release workflow, **When** two run at once, **Then** they do
   not abort each other half-published (`cancel-in-progress: false`). Note that
   GitHub keeps only the **latest** queued run per concurrency group, so a
   rapid series of pushes coalesces: intermediate version numbers are skipped
   and the newest run publishes everything accumulated. No change is lost; the
   numbering has gaps.
5. **Given** publishing fails, **When** it does, **Then** the run says why in
   one sentence rather than a REST error code (U317). A failed release is
   otherwise **invisible**: the build is green, the app simply never offers an
   update, and the owner asks days later why nothing is arriving — which is
   exactly what happened when v2.0.127 through v2.0.129 never published.
6. **Given** the repository's Actions token, **When** it is read-only, **Then**
   no `permissions:` block in the workflow can rescue it. `contents: write` is
   declared at both workflow and job level; the repository setting
   (*Settings → Actions → General → Workflow permissions*) overrides both, and
   `gh api repos/<owner>/<repo>/actions/permissions/workflow` is how you check.

### User Story 4 — The window is one window, and it looks like a product (Priority: P2)

**Acceptance Scenarios**:

1. **Given** the app starts, **When** it does, **Then** the whole stack starts
   with it and the splash shows the version (U211, U44).
2. **Given** the design system, **When** anything is rendered, **Then** it uses
   the shared tokens; light theme with a green accent is the default (U33,
   U193, U216).
3. **Given** the title bar, **When** the app runs, **Then** it belongs to the
   app rather than the OS, and the status it shows is meaningful — U151:
   *"Connected · offline"* said two things at once and explained neither.
4. **Given** the robot connected before the console opened, **When** the
   console opens, **Then** it asks `/robot/status` instead of waiting for an
   event that has already happened (U152, finished in U297 — the header had
   been reporting "Robot offline" about a working robot, visibly, in our own
   release screenshots).
5. **Given** ports are in use, **When** the app starts, **Then** it resolves
   real ports and tells the console which ones (U234). U229: the window loaded
   somebody else's project because `localhost` resolved to `::1` first and a
   different process held the port there.

### User Story 5 — The repository is presentable and safe to publish (Priority: P2)

1. **Given** the repo is public, **When** anybody reads it, **Then** the README
   sells the product, shows real screenshots and links the diagrams (U184–U186,
   U231, U232, U233), and the screenshots match their captions (U230, U297).
2. **Given** the history, **When** it is public, **Then** it contains no
   personal data (U182, U183) and cannot acquire any (U167 — see
   [022-security-and-privacy](../022-security-and-privacy/spec.md)).

## Functional Requirements

- **FR-001**: Owner state (`./data`, keys, skills, prefs) lives **outside** the
  install directory and survives every update.
- **FR-002**: Every push to `master` produces a versioned release with notes,
  screenshots and installers for all four targets.
- **FR-003**: Release notes are English, generated from commit subjects by
  `scripts/release_notes.py`, and unit-tested.
- **FR-004**: Screenshots come from a stack booted with the fake adapter, the
  echo model and the demo persona only. The capture job may fail without
  blocking a release; the page then says so.
- **FR-005**: CI runs without API keys and lints `packages/` and `services/`.
- **FR-006**: The update check reports its result, including "could not ask".
- **FR-007**: An installer is verified before it is run.
- **FR-008**: Ports are resolved, never assumed; prefer `127.0.0.1` over
  `localhost`.
- **FR-009**: A release that does not publish explains itself in the run log,
  naming the setting to check. Silence is the failure mode this whole feature
  cannot afford (constitution XI).

## Out of scope

- Getting a new version onto the **robot** — see
  [021-robot-deployment](../021-robot-deployment/spec.md). The laptop
  self-updates; the Pi does not, and that asymmetry is constitution X.

## Traceability

| Units | What they delivered |
|---|---|
| U32, U33, U44, U193, U211, U228 | The Electron app; the design system; splash, restart badge, VU meter; light theme; version on the splash; room for the brain |
| U55, U56, U166, U169, U169b | NSIS installer and the release pipeline; QA and user guides; automated releases; the first real release run |
| U168, U168b, U168c, U168d, U168e, U283 | Making CI green *and honest* — spawn fix, Linux-only failures, an import-order race, a mutated singleton, clock precision, and the six hours I reported green while it was red |
| U170, U171, U174, U176, U235 | About dialog; a real app icon; icons that were never committed; `updater.cjs` unpackaged; a missing module in the installer |
| U172, U173, U177, U178, U192, U197, U201, U224 | Semantic versioning from commit markers; in-app prompts; the data-loss bug; the silent check; the panic stop; verified on the real robot; the update that never came back; verifying the installer |
| U151, U152, U229, U234, U297 | Honest title-bar status; status polled rather than awaited; the app showing another project; resolving ports; the README screenshots regenerated from the demo stack |
| U184, U185, U186, U230, U231, U232, U233, U236 | A README that sells; screenshots that match their captions; diagrams that render; where the robot comes from; screenshots that had been failing quietly for weeks |
| U284, U285, U285b | Release notes a person wants to read, in English, without an empty section |
