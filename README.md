# AURA — Adaptive Unified Robotic Assistant

An embodied AI chief-of-staff for the **Reachy Mini Wireless**. AURA greets the
people it recognises, assists with work and development tasks, runs
presentations with synced speech and gesture, keeps working when the network
dies — and treats **security and privacy as the top requirement**: everything
it learns about people is encrypted on the laptop and never leaves it.

```
┌──────────────── LAPTOP ────────────────┐        ┌──── REACHY (Pi 5) ────┐
│  aura-brain (:8000)                     │  LAN   │  robot-runtime (:8001) │
│  orchestrator · conversation · memory · │ ◄────► │  motion · audio I/O ·  │
│  identity · connectors · knowledge 🔐   │ REST+WS│  offline behavior loop │
│                                         │        └────────────────────────┘
│  operator-console (:5173, Vue 3)        │   The Pi never holds keys,
└─────────────────────────────────────────┘   tokens, or profile data.
```

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

## Security model (ADR-008)

| Principle | Mechanism |
|-----------|-----------|
| Profiles encrypted at rest | AES-256-GCM envelope: per-person DEK wrapped by an owner master key (scrypt from your passphrase) |
| Local-only | Knowledge never egresses; prompts get a minimal role-based slice, never the profile |
| Minors protected | `role=minor` → explicit facts only, no passive learning, ever (consent is owner-granted, explicit) |
| Right to be forgotten | Deleting a person destroys their key — cryptographic erasure |
| Destructive ops gated | Phone step-up approval via webhook; auto-denied if unconfigured (fail closed) |
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
