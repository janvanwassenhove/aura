---
feature: "020-desktop-app-and-releases"
---

# Implementation Plan: The Desktop App and its Releases

**Prerequisites**: `spec.md`. Retro-written from the code and the workflow.

## Shape

```
push to master
   ├─ version    semantic version from the commit markers
   ├─ test       every package, NO API keys in the environment
   ├─ screenshots  demo stack (fake robot, echo model, demo persona) → PNGs
   │                (optional: may fail without blocking the release)
   ├─ build      windows-setup.exe · mac-arm64.dmg · mac-x64.dmg · AppImage/deb
   └─ release    notes from the commit log + screenshots + installers
```

## Decisions

### Owner state lives outside the install directory

U177, and the single most important line in this spec. Everything the owner
owns — profiles, memories, keys, skills, preferences — used to sit inside the
installed application folder, which the updater replaces. Every update was a
data loss the owner discovered later.

### The commit log *is* the changelog

U285. Every unit lands as exactly one commit with an English subject at exactly
the granularity a release note wants. The alternative that was tried first
(U284) scraped the Dutch ledger, which no build step can translate, and the
version before that scraped a ledger format retired around U180 — rendering an
empty "what's new" for months, unnoticed, because nothing was watching.
`scripts/release_notes.py` is a script rather than YAML precisely so it can be
unit-tested, and `scripts/test_release_notes.py` runs in CI.

### Screenshots are privacy-safe by construction, not by review

U230, U236, U297. The capture stack is booted seconds earlier with
`ROBOT_ADAPTER=fake`, `LLM_PROVIDER=echo`, an empty store that self-seeds one
fictional persona, and every state path pointed at a throwaway directory. There
is no way for personal data to appear because none exists in the environment —
which is a stronger guarantee than any review step.

The same script now also produces the README's pictures (U297), because a
screenshot that has to be retaken by hand is a screenshot that silently rots:
the README's were four months stale before anybody looked.

### CI runs with no keys, on purpose

U283. A developer shell has `OPENAI_API_KEY` set; CI does not. Three tests
depended on it and CI stayed red for six hours while the local run was green.
Verification commands in this repository therefore start with
`OPENAI_API_KEY= ANTHROPIC_API_KEY=`.

### `127.0.0.1`, never `localhost`

U229. On Windows `localhost` resolves to `::1` first, so it can reach a
different process holding the same port on the other address family. It shipped:
the window loaded somebody else's application and looked broken. U234 then made
the ports resolved and announced rather than assumed, so the desktop shell can
move off a busy one and tell the console where it went.

## Files

| Path | Role |
|---|---|
| `apps/desktop/` | The Electron shell, updater, splash, window |
| `.github/workflows/release.yml` | version → test → screenshots → build → release |
| `.github/workflows/ci.yml` | Privacy scan, release-note tests, spec coverage, package tests |
| `.github/scripts/release-screenshots.mjs` | The capture, for releases and for the README |
| `scripts/release_notes.py` | The page, in English, from the commit log |
| `scripts/readme_shots.py` | Captured PNGs → the README's `.webp` files |
| `apps/operator-console/src/lib/endpoints.ts` | One answer to "which port is the brain on" |
