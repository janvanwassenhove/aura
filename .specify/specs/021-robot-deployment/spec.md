---
feature: "021-robot-deployment"
status: "implemented"
owner: "robot-runtime / scripts"
priority: P1
risk: Medium
created: "2026-09-05"
units: [U17, U26, U198, U199, U200, U239, U240, U241, U242, U242b, U339, U345, U346]
---

# Feature Specification: Getting Code onto the Robot

**Feature Branch**: `021-robot-deployment`
**Created**: 2026-09-05 (retro-specified — see [015-spec-coverage](../015-spec-coverage/spec.md))
**Status**: Implemented
**Owner**: `services/robot-runtime`, `scripts/deploy_robot.py`, `scripts/robot_selfupdate.sh`
**Priority**: P1
**Risk**: Medium — the failure mode is silent rather than loud: a robot running
old code answers, moves and looks fine.

## Background

The system runs on two hosts (U17):

* **the laptop** — the brain, the console, everything the owner sees. It
  self-updates on every release.
* **the Raspberry Pi inside the robot** — `robot-runtime`, motors, camera,
  speaker, microphone. Historically flashed by hand.

That asymmetry is constitution X — *"the Pi is older than you think"* — and it
is not a temporary state to be engineered away. A household updates the app the
moment it is offered and touches the robot's filesystem approximately never, so
**the brain must assume it is newer than the runtime it is talking to**.

Reported as *"hoe werkt deployment naar reachy eigenlijk? is dit nieuwe
installatie app?"* and, later the same evening, *"zojuist update app gedaan, is
robot dan niet up to nu?"* — a fair question, and the answer at the time was
no.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Drift is impossible to miss (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the laptop and the robot are running, **When** the owner asks,
   **Then** `python scripts/deploy_robot.py --check` reports both commits and
   whether the robot is BEHIND (U240).
2. **Given** the robot is behind, **When** the console shows the robot,
   **Then** the drift is visible there too rather than only in a script.
3. **Given** the robot is behind but **no robot-runtime files changed**,
   **When** the difference is examined, **Then** no deployment is needed —
   the check reports the commit, and the diff decides.

### User Story 2 — The robot can follow releases by itself (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the self-update timer is installed, **When** a release lands,
   **Then** the robot pulls and restarts unattended (U241) — verified in
   practice: it picked up U287 at 22:18 with nobody watching.
2. **Given** the updater, **When** it runs, **Then** it does not live inside
   the working tree it is updating (U242) — a script that replaces the
   directory it is running from is a script that sometimes does not finish.
3. **Given** the repository is checked out on the Pi, **When** line endings
   differ between hosts, **Then** they are pinned so a pull is not a diff
   (U242b).

### User Story 3 — When the robot cannot be reached, it says why (Priority: P1)

**Acceptance Scenarios**:

1. **Given** the robot is unreachable, **When** the console shows it, **Then**
   it names the reason — *connection refused*, *no route*, *name not resolving*
   — rather than a spinner (U198).
2. **Given** a reason that suggests an address, **When** it is shown, **Then**
   the address is editable right there, pre-filled (U199), and the network can
   be scanned for the robot (U200).
3. **Given** an older runtime, **When** the brain calls something it does not
   have, **Then** the call fails alone, the sequence around it completes, and
   the degradation is reported (U196, U238).
4. **Given** a robot that answers and refuses us (HTTP 401), **When** the
   console shows it, **Then** it is named as a pairing problem rather than as a
   network fault, and the robot's pairing key can be entered on that same
   screen — write-only, never echoed back, and clearable for a robot that has
   none (U339).
5. **Given** that same robot, **When** the console reads the *headline* rather
   than the reason, **Then** it says the same thing. U345: U339 taught `reason`
   the difference and left `error` opening with "robot unreachable:
   HTTPStatusError" — two fields of one response telling two different
   stories, and the console leads with the wrong one.
6. **Given** an address is saved, **When** the endpoint reports back, **Then**
   it does not call the robot reachable on the strength of `/health` alone.
   That route is not gated, so it answers `200` for a robot that refuses every
   real call — and "saved, reachable" beside a header still reading *offline*
   is the contradiction this endpoint exists to prevent (U345).

### User Story 4 — The Pi does not fall over under load (Priority: P2)

1. **Given** the Pi is hot or saturated, **When** it is, **Then** non-essential
   work is shed rather than everything degrading together (U26).

## Functional Requirements

- **FR-001**: `scripts/deploy_robot.py --check` compares the running robot's
  commit against the local one and reports BEHIND / in step.
- **FR-002**: `scripts/robot_selfupdate.sh` runs from outside the working tree
  and is driven by a timer on the Pi.
- **FR-003**: Line endings are pinned repository-wide (`.gitattributes`) so a
  checkout on Linux and one on Windows are the same tree.
- **FR-004**: Every brain→runtime call added after this spec tolerates a 404
  from an older runtime and reports the degradation instead of success.
- **FR-005**: An unreachable robot is diagnosed, not spun on, and the fix (an
  address, a scan, a pairing key) is offered on the same screen.
- **FR-006**: A second machine is paired with a robot that holds a shared
  secret (U220) from the app — `ROBOT_SHARED_SECRET` is settable through
  `/setup/config`, reported only as set/not set, and takes effect without a
  restart.
- **FR-007**: **Not reached** and **reached and refused** are distinguished in
  every field the owner sees, not only in the diagnosis sentence. An HTTP
  status from the robot is evidence the network is fine; leading with
  "unreachable" reports something that was not verified (constitution XI). The
  address probe asks a gated route as well as `/health`, so "reachable" means
  the brain can actually use it.
- **FR-008**: The pairing key is read **per request**, never bound into a cached
  client. U346: `_client()` froze `robot_auth_headers()` at construction, so a
  brain started before pairing sent an empty header for the rest of its life —
  the live video panel stayed dark with 401s while the MJPEG stream beside it
  worked, because that one builds a client per call. U339 promises pairing takes
  effect without a restart; a cached header silently exempts one path from that
  promise. Checked by a test that builds the client while a key is set and
  asserts it carries none.

## Out of scope

- The laptop's own updates — see
  [020-desktop-app-and-releases](../020-desktop-app-and-releases/spec.md).
- How the shared secret is checked on the robot — see
  [022-security-and-privacy](../022-security-and-privacy/spec.md) (U220).
  Setting it on a second machine is here (U339), because that is where the
  owner meets the problem.

## Traceability

| Units | What they delivered |
|---|---|
| U17 | Two-host bring-up: laptop brain ↔ Reachy Pi |
| U198, U199, U200 | Say why the robot is unreachable; make the address settable; find it on the network |
| U239 | Bring the Pi back in step after nineteen units of drift (U220 → U238) |
| U240 | Make deployment drift impossible to miss |
| U241 | Let the robot follow releases by itself |
| U242, U242b | Move the updater out of the tree it updates; pin line endings |
| U26 | On-Pi budget guard — shed non-essential work when hot or saturated |
| U339 | A 401 named as a pairing problem, and the robot's key settable from the Connection card |
| U345 | The two places U339's distinction had not reached: the headline field, and an address probe that only asked the ungated route |
| U346 | The pairing key read per request instead of frozen into a cached client — the one path where "no restart needed" was not true |
