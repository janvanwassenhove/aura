---
feature: "020-desktop-app-and-releases"
status: "implemented"
owner: "apps/desktop + CI"
priority: P1
risk: High
created: "2026-09-05"
units: [U32, U33, U44, U55, U56, U151, U152, U166, U168, U168b, U168c, U168d, U168e, U169, U169b, U170, U171, U172, U173, U174, U176, U177, U178, U192, U193, U197, U201, U211, U228, U229, U230, U231, U232, U233, U234, U235, U236, U283, U284, U285, U285b, U297, U179, U184, U185, U186, U210, U317, U318, U327, U330, U337, U338, U343, U344, U353, U354, U355, U363]
amended: "2026-09-13"
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
   wiped it. U327: it moved five files short of done — the quiet switch and
   the mode policy, the owner's MCP servers, the connector preferences, the
   latency traces and the downloaded gesture model kept the old relative
   default, and so kept being wiped. Reported as *"in quiet mode he should not
   talk, but he still talks"*: the switch had been on since September, an
   update reset the file the brain reads, and he greeted people by name under
   a header that said HUSHED.
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
6. **Given** the release job, **When** it publishes, **Then** it carries its
   own `permissions: contents: write`. Measured on this repository (U317/U318):
   the workflow-level grant **alone** returned 403 and lost three releases; the
   job-level block published successfully with the repository's
   `default_workflow_permissions` still set to `read`. The workflow-level grant
   is kept as well, but the job-level one is the load-bearing half.

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
6. **Given** a **source checkout** rather than an installer, **When**
   `start-aura.bat` is double-clicked, **Then** the same stack comes up —
   including the Python environment. U343: the launcher had been unchanged
   since July while `ensureBootstrap()` stayed packaged-only
   (`if (!IS_PACKAGED) return`), so a checkout never synced and never got the
   extras; it keyed the console build on the *existence* of `dist/index.html`,
   so every pull left an old console talking to a new brain; and it baked
   `VITE_*` at `localhost:8020`, which U234 had already replaced and U229 had
   already warned about.
7. **Given** a **managed laptop**, **When** the app starts the brain, **Then**
   it starts. U344: on a corporate machine the Defender ASR rule
   `01443614-CD74-433A-B99E-2ECDC07BFC25` ("block executable files unless they
   meet a prevalence, age or trusted list criterion") refuses every launcher
   `uv` generates in `.venv\Scripts` — the brain died with `Access is denied.
   (os error 5)` before its first line, while `python.exe` in the same folder
   ran fine.
8. **Given** the brain has already exited, **When** the shell is waiting for
   it, **Then** it says so at once and quotes the reason. U344's second half,
   and the worse one: the app polled `/health` for ninety seconds against a
   process that was already gone, then reported a timeout naming no cause —
   while the answer sat in `brain.log` the whole time. From the owner's side
   that is a frozen splash screen (constitution XI).

### User Story 5 — The repository is presentable and safe to publish (Priority: P2)

1. **Given** the repo is public, **When** anybody reads it, **Then** the README
   sells the product, shows real screenshots and links the diagrams (U184–U186,
   U231, U232, U233), and the screenshots match their captions (U230, U297).
2. **Given** the history, **When** it is public, **Then** it contains no
   personal data (U182, U183) and cannot acquire any (U167 — see
   [022-security-and-privacy](../022-security-and-privacy/spec.md)).

## Functional Requirements

- **FR-001**: Owner state (`./data`, keys, skills, prefs) lives **outside** the
  install directory and survives every update. Checked, not trusted: a test
  scans the brain and its services for every environment variable whose default
  resolves against the working directory, and fails when the desktop app does
  not pin it to `userData` — so the next such setting cannot be forgotten the
  way five of them were (U327).
- **FR-012**: The free route for an open-source project is wired: SignPath
  Foundation signs the Windows installer through the release workflow. The
  unsigned installer is uploaded, submitted, and the signed file lands back on
  top of it, so the ordinary upload publishes the signed one without knowing
  anything about signing. Skipped entirely without a token and never able to
  fail a release; the order (upload → sign → verify → publish) is checked,
  because reversing two of those steps publishes an unsigned build under a
  summary that says it is signed (U338).
- **FR-011**: The Windows installer is signed when a certificate is configured,
  and **says which** when it is not. Signing runs through `apps/desktop/
  sign.cjs`: Azure Trusted Signing when the Azure secrets are present, a PFX
  when those are, and otherwise a no-op that logs `UNSIGNED` — a fork, a pull
  request and a local `npm run dist` must still produce a working installer,
  and a missing secret must never fail a release. The release then verifies the
  artefact and writes the answer into the run summary, because "unknown
  publisher" is otherwise discovered at install time on somebody else's
  machine. A private key written to a runner is deleted in a `finally`
  (U337).
- **FR-016**: Windows gets **two** installers, published side by side. The NSIS
  `.exe` stays: it is the auto-update path and every install that already
  exists. The **MSI** is added for a managed machine, and for the same reason
  FR-014 starts `python -m aura_brain` rather than a generated launcher — an
  MSI is not an executable, it is data handed to `msiexec.exe`, which is
  Microsoft-signed and already allowed, and it installs into `Program Files`
  instead of executing itself from a user-writable directory. The MSI is
  therefore **per-machine** (`msi.perMachine: true`); electron-builder defaults
  both installers to per-user, which puts the app in `%LOCALAPPDATA%` — the
  location the default AppLocker rule set exists to deny. Reported with the
  screenshot Windows actually shows: *"Windows cannot access the specified
  device, path, or file. You may not have the appropriate permissions to access
  the item."* — refusal to **execute**, before any wizard, while an unsigned
  MSI for another product reached its wizard on the same laptop. Signing
  (FR-011) is unaffected and still wanted; it is a different problem, and U337
  already recorded that it would not by itself defeat a policy block (U353).
  **Measured on the managed laptop (U354)**: the MSI installs, into
  `C:\Program Files\AURA\AURA.exe`. Installation is solved.
- **FR-018**: Installing and *running* are separate gates with different keys,
  and only one of them is ours. Defender's ASR rule
  `01443614-CD74-433A-B99E-2ECDC07BFC25` — "block executable files from running
  unless they meet a prevalence, age, or trusted list criteria", the same rule
  by id that FR-014 routes around for the brain launcher — refuses
  `AURA.exe` itself. There is no equivalent route: the launcher was a shim with
  a signed, prevalent `python.exe` beside it, whereas `AURA.exe` **is** the app,
  and every release is unsigned, minutes old and run by almost nobody — all
  three limbs of the rule, by construction. No installer format, install
  directory or packaging flag changes it. The only limb a project can satisfy
  deliberately is the trusted list, which is FR-011's signing; prevalence and
  age cannot be engineered. Until then it takes an ASR exclusion for the install
  directory, which only IT can add (Tamper Protection) (U354). **Measured
  against the app that does run on that laptop (U355)**: Reachy Mini Control's
  executable is unsigned too, so the trusted list is not what admits it — it
  passes on prevalence and age, one build shipped to everyone for weeks. Under
  FR-002 AURA cuts a release per push to `master` (162 `v2.0.*` tags) and so
  never ships the same binary twice: prevalence and age are not merely hard for
  this project, they are **unreachable by construction**, which leaves FR-011's
  signing the only limb it can ever satisfy.
- **FR-017**: An update installs **the way this copy was installed**. The
  updater picks the MSI for a per-machine install and the `.exe` for a per-user
  one, decided from where the running executable lives; it falls back to
  whichever the release actually carries, because an older release has no MSI
  and "no update available" would be a lie. The staged file is then run the way
  that file can be run — `msiexec /i` for an MSI, `call … /S` for the `.exe`.
  The MSI branch is deliberately **not** silent: a per-machine install needs
  elevation, and a UAC prompt with no window to explain it is worse than a
  wizard. Without this, an MSI install would update itself into a second,
  per-user copy in a different directory, and which one the shortcut starts
  would be a coin toss (U353).
- **FR-002**: Every push to `master` produces a versioned release with notes,
  screenshots and installers for all four targets.
- **FR-003**: Release notes are English, generated from commit subjects by
  `scripts/release_notes.py`, and unit-tested.
- **FR-010**: Refreshing the published screenshots is **one command**
  (`scripts/refresh_screenshots.py`): it boots the demo stack on free ports,
  captures, converts and cleans up. The release captures the same pictures but
  cannot commit them, so the committed ones only ever change here — and a
  six-step manual dance is why they stood still for weeks. The isolation is
  enforced in code: every owner-state path is redirected into a throwaway
  directory and the run refuses to start if one still resolves inside the
  repository (U330).
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
- **FR-013**: Starting from a source checkout is one action and leaves nothing
  stale. `start-aura.bat` syncs the Python environment itself — the packaged
  bootstrap does not run for a checkout — down the same extras ladder
  (`recognition`, `computeruse`, `presentation`), on the interpreter CI
  actually tests. It rebuilds the console whenever the console's git tree hash
  differs from the one recorded in the last build, and it bakes no endpoint:
  the shell injects the ports it really got (FR-008).
- **FR-014**: The brain is started as `python -m aura_brain`, never through a
  generated console script. Launchers written into `.venv\Scripts` are
  unsigned and brand new by construction, which is exactly what a managed
  machine's ASR policy refuses; the interpreter is signed and allowed. Checked,
  not trusted: `apps/desktop/test-brain-launch.cjs` asserts the spawn argv and
  that `aura_brain/__main__.py` calls the same `run()` the console script
  declares, so the two entry points cannot drift.
- **FR-015**: A brain that exited fails the startup wait **immediately**,
  quoting its own last stderr. Waiting out a timeout on a dead process turns a
  named, logged cause into an unexplained freeze.

## Out of scope

- Getting a new version onto the **robot** — see
  [021-robot-deployment](../021-robot-deployment/spec.md). The laptop
  self-updates; the Pi does not, and that asymmetry is constitution X.

- **FR-019**: The brain configures logging before uvicorn starts, so its own
  lines actually reach `brain.log`. Nothing did: `uvicorn.run()` sets up its own
  loggers and leaves the root at WARNING, so every `logger.info` in the brain,
  the orchestrator and the scenario runner was discarded — including
  `"beat %r fired"`. Found while diagnosing a beat that did not speak during a
  rehearsal, with 20 MB of log holding nothing but HTTP access lines. `LOG_LEVEL`
  overrides the default INFO and a nonsense value is never fatal — this is the
  process the whole app waits on. The noisy HTTP libraries are pinned at WARNING,
  because the brain polls the robot's camera several times a second and INFO
  there would bury the log it is meant to make readable. The handler is added
  once and **no other handler is ever removed** (U363).

## Traceability

| Units | What they delivered |
|---|---|
| U32, U33, U44, U193, U211, U228 | The Electron app; the design system; splash, restart badge, VU meter; light theme; version on the splash; room for the brain |
| U55, U56, U166, U169, U169b | NSIS installer and the release pipeline; QA and user guides; automated releases; the first real release run |
| U168, U168b, U168c, U168d, U168e, U283 | Making CI green *and honest* — spawn fix, Linux-only failures, an import-order race, a mutated singleton, clock precision, and the six hours I reported green while it was red |
| U170, U171, U174, U176, U235 | About dialog; a real app icon; icons that were never committed; `updater.cjs` unpackaged; a missing module in the installer |
| U355 | Why the same ASR rule admits another unsigned app: prevalence and age, which a release-per-push project can never reach — so signing is the only door |
| U354 | The MSI installs on the managed laptop — and Defender's ASR rule then refuses to run the app itself, which is a different gate and needs signing or an IT exclusion |
| U363 | The log recorded no beats — nothing configured logging at all, so every INFO line the app wrote was thrown away |
| U353 | An MSI beside the .exe, per-machine, because a managed laptop refuses to execute the installer at all — and an update that follows the way this copy was installed |
| U172, U173, U177, U178, U192, U197, U201, U224 | Semantic versioning from commit markers; in-app prompts; the data-loss bug; the silent check; the panic stop; verified on the real robot; the update that never came back; verifying the installer |
| U151, U152, U229, U234, U297 | Honest title-bar status; status polled rather than awaited; the app showing another project; resolving ports; the README screenshots regenerated from the demo stack |
| U184, U185, U186, U230, U231, U232, U233, U236 | A README that sells; screenshots that match their captions; diagrams that render; where the robot comes from; screenshots that had been failing quietly for weeks |
| U284, U285, U285b | Release notes a person wants to read, in English, without an empty section |
| U327 | The five settings U177 left in the install directory — quiet and the mode policy among them — pinned to userData, with a test that finds the next one |
| U330 | The published screenshots refreshed from the current app, one command to redo it, and two drawings that had stopped being true |
| U337 | Windows code signing wired end to end (Azure Trusted Signing or a PFX), an unsigned build that admits it, and every check in scripts/ actually running in CI |
| U338 | SignPath Foundation wired into the release: free signing for an open-source project, guarded and order-checked |
| U343 | The from-source launcher caught up with the app it starts: it syncs Python with the extras, rebuilds a stale console, and stops baking a port |
| U344 | The brain launched through the interpreter instead of a shim a corporate ASR rule forbids, and a dead brain that now names its cause instead of freezing the splash |
