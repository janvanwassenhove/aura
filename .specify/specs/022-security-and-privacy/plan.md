---
feature: "022-security-and-privacy"
---

# Implementation Plan: Security and Privacy

**Prerequisites**: `spec.md`, [`docs/audit-2026-08.md`](../../../docs/audit-2026-08.md).
Retro-written; the audit table is the live tracker and this records the shape.

## Threat model, in one paragraph

The attacker is not a nation state. It is the LAN: a smart television, a
neighbour on the same Wi-Fi, a web page open in another tab, and a public git
history. The assets are a household's faces, memories about children, mail and
calendar tokens, and control of a laptop. The consequences are not reversible
by a later release, which is why the bar here is different from everywhere else
in the repository.

## Decisions

### Loopback by default; the LAN only where the design requires it

The brain and the console bind loopback. The robot runtime **must** be reachable
across the LAN — the brain is on the laptop and the runtime is on the Pi — so it
is guarded by a shared secret rather than by not listening. That asymmetry is
deliberate and documented, because "bind everything to loopback" would simply
not work for the one process that has a camera.

### Tokens move in-process, never through the browser

The console never needs a token; it needs to know whether one exists. U221
replaced the fetch with `/identity/status`, and U226 deleted the route that had
been handing out live tokens to anyone who could reach the port. Deleting beat
authenticating: the route had no remaining callers, and an authenticated
token-dispensing endpoint is still a token-dispensing endpoint.

### The OS is a better secret store than a file we wrote

U225. A passphrase in `.env` beside the ciphertext it protects is not a secret.
Windows Credential Manager binds it to the Windows login via DPAPI. The
trade-off is stated in `CLAUDE.md`: there is exactly one copy, and no recovery.

Existing installs rotate in place on boot rather than requiring the owner to do
anything, because a security improvement nobody applies is not one.

### The privacy gate is two gates

`scripts/privacy_scan.py` runs on staged files in `.githooks/pre-commit` (fast,
where the fix is cheap) **and** over the whole tree in CI (the backstop, so
`--no-verify` does not get anything through). The scanner has its own tests.
This is the same two-layer shape the spec-coverage check adopted in U299: a
nudge where it is cheap, an enforcement where it cannot be skipped.

### Refuse link-local, allow the LAN

U226, S7. Blanket SSRF protection would break the product — finding the robot
*is* a LAN scan. So the rule is specific: link-local ranges where cloud
metadata lives are refused, including via resolved host names; the private LAN
and loopback stay allowed.

## Files

| Path | Role |
|---|---|
| `scripts/privacy_scan.py`, `scripts/test_privacy_scan.py` | The gate and its tests |
| `.githooks/pre-commit`, `.github/workflows/ci.yml` | Where it runs |
| `apps/aura-brain/src/aura_brain/main.py` | Binding, TrustedHost, Origin guard |
| `apps/aura-brain/src/aura_brain/setup_api.py` | `.env` sanitising; secrets never echoed |
| `apps/aura-brain/src/aura_brain/knowledge_api.py` | Unlock: constant-time, backoff |
| `services/robot-runtime/` | `ROBOT_SHARED_SECRET` guard |
| `services/identity-service/src/identity_service/main.py` | Status, PUT, DELETE — no token reads |
| `apps/desktop/` | `EXTERNAL_ALLOW`, DevTools only unpackaged, installer verification |
| `docs/audit-2026-08.md` | The consolidated backlog and what is verified OK |
