# Changelog

All notable changes to AURA are documented here. Release tags follow semver
(`v<major>.<minor>.<patch>`); pushing a tag builds the Windows installer and
publishes a GitHub Release automatically.

## [Unreleased]

## [1.0.0] — 2026-07-14

First commercial-ready desktop release.

### Highlights
- **Desktop app**: Electron shell (frameless, themed title bar) that runs the
  AURA brain + operator console in one window; NSIS installer with one-time
  first-run bootstrap (installs `uv`, syncs the Python workspace).
- **In-app onboarding**: full-screen setup wizard on first run — assistant
  name & language, robot discovery (mDNS + subnet scan) and connectivity test,
  LLM provider + key (write-only), hands-free wake word, knowledge encryption.
- **Embodied conversation**: replies are spoken on the robot with a gesture
  matched to content *and* mode (silent desk stays quiet, presentation goes
  expressive); streamed TTS starts the first sentence while the rest is still
  being synthesized; barge-in lets you interrupt the robot mid-sentence.
- **Hands-free voice**: wake-word loop on the robot microphone with follow-up
  conversation windows, hallucination filtering, and per-person greeting
  cooldowns.
- **Recognition & knowledge**: face recognition (identifies, never
  authenticates) with AES-256-GCM-encrypted profiles, transparency panel,
  unknown-visitor log with one-click tagging, minors explicit-facts-only.
- **Laptop control, always gated**: allow-listed app launcher, VS Code and
  Chrome control (navigation approval-gated), Windows media keys, developer
  tasks via Claude Code, and default-off Computer Use (screenshot +
  mouse/keyboard) — every sensitive action asks the owner first, with
  optional per-tool "always allow".
- **Connectors**: M365/Google/GitHub/Slack with honest statuses (mock data is
  labeled MOCK, per-connector Test probe), Spotify + Sonos music control.
- **Resilience**: offline tier (local LLM → regex fallback), robot
  self-maintenance loop, per-turn latency instrumentation.

### Security model
- Approval gate on every sensitive action; capability toggles are default-off
  for high-impact features (Computer Use).
- Knowledge and face embeddings encrypted at rest; erasure is cryptographic.
- Secrets are write-only through every API; never logged, never echoed.
- The robot (Pi) never holds keys, tokens, or profile data.
