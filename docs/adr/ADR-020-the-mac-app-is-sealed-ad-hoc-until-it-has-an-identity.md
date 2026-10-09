# ADR-020: The Mac app is sealed ad hoc until it has an identity

**Status**: **Accepted — implemented in U412** (2026-10-09).
**Date**: 2026-10-09
**Owner**: desktop / releases
**Related**: [ADR-010](ADR-010-desktop-app-is-the-delivery-unit.md) (the desktop
app is the delivery unit), [spec 020](../../.specify/specs/020-desktop-app-and-releases/spec.md),
U337, U338, U412

---

## Context

The Mac build was configured `mac.identity: null`, and every release log said:

```
• skipped macOS code signing  reason=identity explicitly is set to null
```

"Skipped" read as "left as Electron shipped it". It is not. electron-builder
renames Electron's executable and rewrites `Info.plist` before it reaches the
signing step it then skips, so the bundle's seal no longer matches its
contents. macOS calls a downloaded app with a broken seal *damaged*: "AURA is
damaged and can't be opened. You should move it to the Trash." There is no
button past that — only the terminal — and on Apple Silicon the kernel refuses
code whose signature does not hold.

A Mac can open an app from outside the App Store in three states:

| The app is… | What the owner sees on first open |
|---|---|
| signed with a **Developer ID** and **notarized** | Nothing. It opens. |
| **sealed ad hoc** (identity `-`) | "Apple could not verify AURA is free of malware" — once; *Open Anyway* in System Settings → Privacy & Security. |
| **unsigned, or with a broken seal** | "damaged and can't be opened". |

## Decision

Every Mac build is **sealed ad hoc** by an `afterPack` hook
(`apps/desktop/mac-sign.cjs`) and **verified** with
`codesign --verify --deep --strict`, both in the release and in a CI job that
packs the app on macOS on every push. A broken seal fails the build.

When a Developer ID is configured, the hook steps aside and electron-builder
signs — the switch is configuration, not code.

## Consequences

- The owner confirms AURA once per install, in Privacy & Security. The user
  guides say where.
- Updates on a Mac already open the release page rather than installing in
  place (`maybeOfferUpdate` in `main.cjs`), so ad-hoc sealing costs the updater
  nothing.
- **Moving to a Developer ID** (the step that removes the confirmation): an
  Apple Developer Program membership; a *Developer ID Application* certificate
  exported as `.p12`; repository secrets `CSC_LINK` (the `.p12`, base64) and
  `CSC_KEY_PASSWORD`; for notarization `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`
  and `APPLE_TEAM_ID`; and in `package.json` `mac.identity` removed,
  `mac.hardenedRuntime: true` and `mac.notarize: true`. Hardened runtime will
  need entitlements for what the app spawns (the brain, `uv`), and that has to
  be tested on a Mac before the first such release.

## Alternatives considered

**Keep `identity: null` and document `xattr -cr`.** Rejected: it asks every
owner to run a terminal command to undo a defect the build introduced, and it
does not make the seal valid — only stops macOS from checking it.

**Developer ID now.** Not rejected — deferred. It needs a paid account and
secrets only the owner can create, and an unverified hardened-runtime build
would trade one "won't open" for another. Ad-hoc sealing fixes the broken
state today and leaves the door open.
