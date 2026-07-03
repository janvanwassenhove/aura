# AURA Setup Guide — from unboxing to a talking robot

The complete path for **device day**: you have the Reachy Mini Wireless, a
laptop, and this repository. At the end, AURA recognises your household, talks
with the voice pipeline, survives network loss, and keeps everything it learns
encrypted on your laptop.

For a hardware-free dry run, do the same steps with `ROBOT_ADAPTER=fake` and
skip §2.

---

## 0. What runs where

AURA is **two hosts, three services** (ADR-007):

| Host | Service | Port | Role |
|------|---------|------|------|
| Laptop | `aura-brain` | 8000 | Orchestration, LLM, connectors, memory, identity, **knowledge (encrypted)** |
| Laptop | `operator-console` | 5173 | Vue console: conversation, robot state, events, 🧠 knowledge, ⚙ settings |
| Reachy (Pi 5) | `robot-runtime` | 8001 | Motion, audio I/O, on-device offline loop |

**The Pi never holds keys, tokens, or profile data.** If someone walks off with
the robot, they get motors and a speaker.

## 1. Laptop prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Node 20+ (operator console)
- Docker Desktop (optional — everything also runs bare-metal)

```bash
git clone <repo> && cd reachy-chief-of-staff
uv sync
```

## 2. Bring up the robot (Pi side)

Follow [infra/two-host-bringup.md](../infra/two-host-bringup.md) §1 to install
and start `robot-runtime` on the Pi. Short version:

```bash
# on the Pi
uv sync --package robot-runtime --no-dev
ROBOT_ADAPTER=reachy PORT=8001 uv run --package robot-runtime robot-runtime
```

Verify from the laptop: `curl http://<pi-ip>:8001/health` → `{"status":"ok"}`.

> The physical `ReachyRobotAdapter` (U16) needs the device — until it lands,
> `ROBOT_ADAPTER=fake` on the Pi exercises the identical contract.

## 3. Run the setup wizard (laptop)

```bash
uv run python -m aura_brain.wizard
```

The wizard walks through every choice and writes `infra/dev/.env`:

1. **Robot connection** — the Pi's URL, with an optional live health check.
2. **LLM provider** — `openai` / `openrouter` (free tiers) / `gemini` /
   `echo` (no key, for testing). API keys are typed hidden and never echoed.
3. **Voice pipeline** — STT (`local_whisper` runs offline; `openai_realtime`
   is the low-latency speech-to-speech transport) and TTS (`kokoro`/`piper`
   offline, or `openai`).
4. **Offline resilience** — heartbeat monitoring plus an optional local model
   (ollama/llama.cpp) that answers when the internet is down.
5. **Security** — the knowledge passphrase (see §5), a fresh random salt, the
   step-up webhook for destructive-action approvals on your phone, and the
   dev-agent switch.
6. **Mode & connectors** — startup persona; M365 mock or real Work IQ; google/
   github/slack connectors.
7. **People** — your household. Owner first, then family; children get
   `role=minor` (explicit facts only — AURA never learns passively about
   minors, ADR-008 §10). Facts are simple `key=value` lines. People are
   written **directly into the encrypted store** — the wizard refuses to save
   them unencrypted.

Re-run the wizard any time; the previous `.env` is backed up to `.env.bak`.

## 4. Start the brain + console

**Docker (recommended):**

```bash
docker compose -f infra/dev/docker-compose.yml up --build
```

**Bare-metal (two terminals):**

```bash
# terminal 1 — the brain (reads env from your shell; export what the wizard wrote)
uv run --package aura-brain aura-brain

# terminal 2 — the console
cd apps/operator-console && npm install && npm run dev
```

Open **http://localhost:5173**:

- **Robot State** — mode, behavior, speaking indicator, recognised person,
  motion log.
- **Conversation** — type to talk; per-turn latency shows under the reply.
- **Event Log** — the live event bus.
- **🧠 Knowledge** — everyone AURA knows: explicit facts (editable) vs observed
  signals (read-only, with confidence), forget-person, tier badge + lock.
- **⚙ Settings** — switch LLM provider/model at runtime, connector status.

## 5. The security model in two minutes

- **Everything learned about people is encrypted at rest** (AES-256-GCM, one
  key per person, wrapped by an owner master key derived from your
  passphrase). The store file `data/knowledge.enc.json` is ciphertext only —
  back it up freely.
- **Unlock tiers**: without the passphrase in the environment the brain runs
  BENIGN — knowledge is locked (the console shows a banner) but everything
  else works. With it, SENSITIVE unlocks profiles for greetings and context.
- **Destructive operations** (delete a fact, forget a person) additionally
  require a **step-up approval on your phone** via `STEP_UP_WEBHOOK_URL`; with
  no webhook configured they are auto-denied. Deleting a person destroys their
  encryption key — cryptographic erasure, unrecoverable by design.
- **Face recognition identifies, it does not authenticate.** Recognising your
  face personalises greetings and context; it never unlocks anything.
- **A spoken passphrase is rejected** — it can be overheard.
- **Data minimisation per role**: guests → name only; minors → explicit facts
  only; family/owner → top facts + high-confidence signals. Only that minimal
  slice ever reaches an LLM prompt; profiles are never sent wholesale.
- **Sensitive connector actions** (send mail, etc.) always pass the approval
  gate; offline-queued sensitive actions never auto-execute on reconnect.
- **Tokens never appear in logs**; connector tokens live in the OS keyring.

## 6. Voice

Text works immediately. For voice on the device:

| Setup | STT | TTS | Needs |
|-------|-----|-----|-------|
| Offline-first | `local_whisper` | `kokoro` | nothing (models download once) |
| Lowest latency | `openai_realtime` | (built-in) | `OPENAI_API_KEY` with Realtime access |

The Realtime transport (U22) holds one speech-to-speech session with server-side
voice-activity detection and **barge-in** — interrupt AURA mid-sentence and it
stops talking, like a person would.

## 7. Resilience check

Pull the plug and confirm the fallbacks (details in
[infra/two-host-bringup.md](../infra/two-host-bringup.md) §4):

1. **Kill the brain** → within ~15 s the robot says it lost its brain once,
   then idles; it recovers on the next command.
2. **Kill the internet** (keep the LAN) → the heartbeat flips DEGRADED; turns
   route to the local model if configured, else the regex fallback.
3. **Restart the brain** → people and facts are still there (encrypted store
   persists), the console reconnects by itself.

## 8. Day-two operations

| I want to… | Do this |
|------------|---------|
| Add/edit people or facts | Console → 🧠 Knowledge (or re-run the wizard) |
| Give a minor's consent for learning | 🧠 → person → consent (owner-granted) |
| Change LLM provider/model | Console → ⚙ Settings (runtime, no restart) |
| Lock knowledge before guests arrive | 🧠 → Lock (restart with passphrase to re-unlock) |
| Back up | Copy `data/` (ciphertext) + your `.env` (contains secrets — keep private) |
| Forget a person completely | 🧠 → person → Forget (phone approval; cryptographic erasure) |
| Change the passphrase | Export people via console, delete `data/knowledge.enc.json`, re-run wizard, re-add |

## 9. Still blocked on hardware (as of 2026-07-03)

- **U16** — the real `ReachyRobotAdapter` against the Reachy SDK + Pi packaging.
- **U18 remainder** — camera capture → face embedding on the Pi (recognition
  matcher + encrypted embedding store are done and tested).
- **U22 live run** — Realtime voice against the real API + mic/speaker (the
  transport state machine is done and tested).
- **U24** — streaming STT/TTS wiring on device; **U26** — on-Pi budget guard.

Each has tested software seams waiting; they are wiring days, not build weeks.
