# AURA — Adaptive Unified Robotic Assistant

> **A desk robot that knows who you are, joins your workday, and keeps your
> life private — on your own laptop.**

AURA turns a **Reachy Mini** into a personal chief-of-staff: it recognises you,
holds a real spoken conversation, reaches into your mail, calendar, chat and
tasks, learns how *you* work, and moves like it means it. Everything personal
is encrypted on your machine and never leaves it.

<!-- screenshots are published with every release: github.com/janvanwassenhove/aura/releases -->

### The name is the promise

| | |
|---|---|
| **Adaptive** | Adapts behaviour and interaction to the person, the context and the situation. |
| **Unified** | Brings conversation, mail, Teams, calendar, todos, memory and agents together in one place. |
| **Robotic** | Physically embodied through Reachy Mini — it looks at you, reacts, gestures. |
| **Assistant** | A personal assistant and copilot, not just another chatbot. |

### Why it feels different

- **It looks at you and talks back.** Sub-second spoken replies over a live
  audio session, head tracking that follows your face, gestures timed to the
  words. Say "Hey Richie" and just talk.
- **It knows the room.** Faces are recognised, new visitors become guests, and
  every person gets their own encrypted profile — greeting, tone and context
  adapt to who is standing there.
- **It does the work.** Mail, calendar, Teams, todos, music, screen control
  and dev tasks behind one conversation, with approval gates on anything
  sensitive.
- **It gets better by itself.** Skills are written from real usage and
  rewritten when the evidence says they should be.
- **It keeps running when the internet doesn't.** Offline tier, local models,
  and a robot that behaves gracefully instead of freezing.
- **Privacy is the product, not a checkbox.** AES-256-GCM per-person
  encryption, biometrics that never touch disk unencrypted, a step-up gate on
  destructive actions, and a scanner that blocks personal data from ever
  reaching git.

### In one picture

```
┌──────────────── LAPTOP ────────────────┐        ┌──── REACHY (Pi 5) ────┐
│  aura-brain (:8000)                     │  LAN   │  robot-runtime (:8001) │
│  orchestrator · conversation · memory · │ ◄────► │  motion · audio I/O ·  │
│  identity · connectors · knowledge 🔐   │ REST+WS│  offline behavior loop │
│                                         │        └────────────────────────┘
│  operator-console (:5173, Vue 3)        │   The Pi never holds keys,
└─────────────────────────────────────────┘   tokens, or profile data.
```

## Install (no build required)

Grab the installer for your platform from the
[latest release](https://github.com/janvanwassenhove/aura/releases/latest) —
Windows (`.exe`), macOS (`.dmg`, Apple Silicon + Intel) or Linux
(`.AppImage`/`.deb`). First launch installs its own Python runtime; the app
then checks for updates and offers to install them for you.

You need a Reachy Mini for the embodiment, but **the whole stack runs without
hardware** (FakeRobot) if you just want to try it.

## Quick start

**Dry run (no hardware, no keys):**

```bash
cp infra/dev/.env.example infra/dev/.env       # defaults: FakeRobot + echo LLM + mock M365
docker compose -f infra/dev/docker-compose.yml up --build
```

Open the console at http://localhost:5173 and type a message.

**Device day (real Reachy):** run the guided setup wizard, then follow
[docs/setup-guide.md](docs/setup-guide.md):

```bash
uv run python -m aura_brain.wizard
```

The wizard configures the robot link, LLM provider + key, voice pipeline,
offline resilience, security (encryption passphrase, phone step-up approvals),
and seeds your household — owner, family, guests, minors — straight into the
encrypted knowledge store.

## What AURA does

- **Recognises people** and personalises: greeting, context, and tone follow
  who is in front of it (recognition *identifies*; it never *authenticates*).
- **Chief-of-staff turns**: calendar/mail via M365 (mock or Work IQ MCP),
  todos, reminders — with an **approval gate** on every sensitive action.
- **Dev assistance**: an outbound dev agent that can read repos freely but
  needs explicit approval for every write, commit, or push (off by default).
- **Presentations**: synced speech + gesture co-pilot with slide navigation.
- **Voice**: offline STT/TTS (whisper.cpp, kokoro) or the OpenAI Realtime
  speech-to-speech transport with barge-in.
- **Survives failures**: heartbeat monitoring degrades gracefully — local LLM
  when the internet dies, regex fallback after that, and an on-device loop so
  the robot stays polite even with no brain at all.
- **Always stoppable**: one **Stop** button cuts speech mid-word, ends the
  conversation and mutes the microphone — because a voice assistant that can
  be triggered by ambient noise must be silenceable in one click.

## Security model (ADR-008)

| Principle | Mechanism |
|-----------|-----------|
| Profiles encrypted at rest | AES-256-GCM envelope: per-person DEK wrapped by an owner master key (scrypt from your passphrase) |
| Local-only | Knowledge never egresses; prompts get a minimal role-based slice, never the profile |
| Minors protected | `role=minor` → explicit facts only, no passive learning, ever (consent is owner-granted, explicit) |
| Right to be forgotten | Deleting a person destroys their key — cryptographic erasure |
| Destructive ops gated | Phone step-up approval via webhook when configured; otherwise a typed confirmation from the owner's own console (erasure must never be impossible) |
| Sensitive actions gated | Approval gate is never bypassed; offline-queued actions never auto-execute on reconnect |
| The robot is dumb | The Pi holds no keys, tokens, or data — stealing it yields motors |
| No secrets in logs | Tokens never logged; keyring-backed storage |

Transparency: the console's **🧠 Knowledge** panel shows every person, every
fact (editable), every observed signal (with confidence) — and the lock state.

## Repository layout

```
apps/
├── aura-brain/           # THE laptop process: all five modules on one bus + wizard
└── operator-console/     # Vue 3 + Pinia console

services/
├── robot-runtime/        # Runs on the Pi: RobotAdapter, behavior engine, offline loop
├── orchestrator/         # Pipeline, approval gate, personas, dev agent, presentations
├── conversation-runtime/ # STT/TTS providers + Realtime transport
├── connector-service/    # M365 (mock/Work IQ), google, github, slack
├── memory-service/       # Sessions, todos, reminders (SQLite)
└── identity-service/     # Tokens (OS keyring), persona, mode

packages/
├── shared-schemas/       # Pydantic events + knowledge layer (store, crypto, judgment)
├── shared-events/        # AsyncEventBus + WebSocket broadcaster
├── shared-policies/      # Approval rules, mode access control
├── shared-personas/      # Persona definitions & system prompts
└── shared-prompts/       # Prompt templates

infra/
├── dev/                  # docker-compose (3 services), .env.example
└── two-host-bringup.md   # Laptop ↔ Pi bring-up

docs/
├── setup-guide.md        # ★ Device day: unboxing → talking robot
├── implementation-backlog.md  # The autonomous build ledger (source of truth)
└── adr/                  # Architecture decision records (ADR-001…008)
```

The five laptop services are **mounted into one `aura-brain` process** (one
event bus, in-process seams via ASGI — ADR-007); they remain separate packages
for testing and clarity.

## Development

```bash
# Python tests, per package
uv run --package orchestrator --extra dev pytest services/orchestrator/tests
uv run --package aura-brain   --extra dev pytest apps/aura-brain/tests

# Console
cd apps/operator-console && npm test && npm run build

# One-time per clone: privacy gate — blocks committing personal data
# (voice logs, databases, recordings, keys, .env files, personal e-mails).
# CI enforces the same scan on every push, so skipping this only delays the block.
git config core.hooksPath .githooks
```

Key rules (see [.specify/memory/constitution.md](.specify/memory/constitution.md)):

- **FakeRobot is the primary dev target** — everything works without hardware.
- No Reachy SDK imports outside `services/robot-runtime/`.
- `M365_CONNECTOR=mock` needs no license; `LLM_PROVIDER=echo` needs no key.
- Sensitive actions require approval — the gate is never bypassed.
- Auth tokens must never appear in logs.

## Status

All software-buildable units are complete and tested (see
[docs/implementation-backlog.md](docs/implementation-backlog.md)). Remaining
work needs the physical device: the Reachy SDK adapter (U16), on-Pi camera
recognition (U18), live Realtime voice (U22/U24), and the on-Pi budget guard
(U26) — the tested seams for each are in place.

## Natural voice conversation (U84)

The conversation layer is a real state machine (`aura_brain/conversation_manager.py`):
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING, with INTERRUPTED as a
first-class state. Every transition is logged with turn id, `tts_playing`,
`llm_active` and `cancel_requested` (never audio or secrets).

**Barge-in** works end-to-end: while the robot speaks, the mic keeps
listening; an interruption stops the robot's audio instantly
(`POST /robot/audio/stop` → playbin cut), cancels the in-flight LLM call and
the speak task, and the interrupting utterance becomes the new active turn —
with one-shot context telling the LLM its previous answer was cut off.

**Characters** (`personas/*.json`, seeded on first run): friendly_assistant,
dry_tech_butler, kids_companion, workshop_coach, quiet_mode. A character sets
the system prompt, verbosity/humor, voice + speed, motion energy and
interruptibility (`wake_word` | `vad` | `off`). Select via Settings
(`ACTIVE_CHARACTER`), list via `GET /setup/characters`.

Key settings (Settings panel / env): `VOICE_MODE=wake_word`, `WAKE_WORD`,
`ACTIVE_CHARACTER`, `BARGE_IN_FACTOR` (interrupt sensitivity),
`SESSION_MEMORY`, `SPEAK_STREAMING` (off = smoothest playback). See
`docs/conversation_diagnosis.md` for the architecture map.
