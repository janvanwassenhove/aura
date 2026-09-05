# ADR-010: The desktop application is the delivery unit

**Status**: **Accepted** — retro-recorded 2026-09-05
**Date**: 2026-09-05 (decided in practice at U32, hardened through U177 and U201)
**Owner**: apps/desktop
**Related**: ADR-007 (topology reshape); constitution X; specs
[020](../../.specify/specs/020-desktop-app-and-releases/spec.md),
[021](../../.specify/specs/021-robot-deployment/spec.md)

---

## Context

ADR-007 collapsed six services into one `aura-brain` process, but stopped short
of saying what a user actually *receives*. The scaffold's answer was
docker-compose: an operator with a terminal, an `.env` file, and the ability to
restart a container.

The owner of this product is a household. They install something, double-click
it, and expect their calendar to show up. Every assumption inherited from the
operator model has had to be removed one unit at a time:

* a setting that lives in an environment variable (U254, U295, U298);
* a change that needs a restart to take effect (U249, U254);
* a status only visible in a log (U178, U198);
* a port that must be free (U229, U234);
* state that lives wherever the process was started from (U177).

Each of those was reported as a bug by the owner, in their own words, and each
was really the same design assumption surfacing again.

## Decision

**The unit of delivery is a signed desktop application that starts the entire
stack in one window.** The Electron shell owns the lifecycle of `aura-brain` and
the console; the robot runtime is the only other process, and it lives on the
Pi.

Four commitments follow.

1. **Owner state lives outside the install directory.** Profiles, memories,
   keys, skills and preferences survive every update, because the updater
   replaces the application folder. (U177 — before this, every update was a
   silent data loss.)

2. **Every setting is reachable from the window, and applies without a
   restart.** An environment variable is a deployment detail, not a setting. If
   a change requires a restart, the product is telling the owner it is broken.

3. **Ports are resolved, never assumed, and `127.0.0.1` is preferred over
   `localhost`.** The shell takes what it can get and tells the console where it
   went (U234). On Windows `localhost` resolves to `::1` first, which once made
   the window load a different application entirely (U229).

4. **Releasing is automatic and the update installs itself.** Every push to
   `master` produces notes, screenshots and installers for Windows, macOS
   (arm64 and x64) and Linux (U166); the app checks, verifies (U224), installs
   and **comes back** (U201).

The corollary is the asymmetry in constitution X: the laptop follows releases
within minutes, the robot may be weeks behind. See ADR-004's amendment and spec
021.

## Consequences

**Good.** The product can be given to somebody who has never seen a terminal.
It also forced a useful discipline: because there is no operator to read a log,
every failure has to be legible on screen — which is where ADR-009 came from.

**Bad.** The single window is a single point of failure: a crash in the shell
takes the brain with it, and a bad release reaches every install at once. This
is mitigated by CI (no keys, all packages), a verified installer, and the fact
that owner state is now outside the blast radius — but it is a real trade.

**Bad.** Building four installers on every push to `master` is slow and
occasionally flaky, and a flaky test blocks a release rather than a merge
(U190, U210).

**Ugly.** Development still uses docker-compose, so two ways of starting the
system exist and can drift. The mitigation is that CI exercises the packaged
path (the release workflow boots the real stack to take screenshots), so drift
shows up as a failing release rather than as a surprise on somebody's laptop.

## Alternatives considered

**Ship docker-compose with a README.** Rejected: it makes the household an
operator. Every "this is really dev like" report traces back to a remnant of
this model.

**A hosted service with a thin local agent.** Rejected on the product's central
promise: the knowledge, the faces and the keys stay on the owner's machine.
Nothing here is worth moving to a server the owner does not control.

**Two applications — a background service plus a UI.** Rejected as premature:
it doubles the install, the update and the failure surface for a benefit
(surviving a UI crash) that has not yet been the problem.
