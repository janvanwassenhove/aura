# Two-Host Bring-Up — laptop brain ↔ Reachy Mini Wireless

How to run AURA across its two real hosts (ADR-007): the **brain** on the laptop,
**robot-runtime** on the **Reachy Mini Wireless (Pi 5)**. The brain↔robot link is
the one network hop; everything else lives in the single brain process.

```
┌──────────── LAPTOP (x86) ────────────┐         ┌──── REACHY (Pi 5, ARM) ────┐
│  aura-brain  (:8000)                  │  LAN    │  robot-runtime (:8001)      │
│  orchestration · conversation ·       │ ◄─────► │  motion · audio I/O ·       │
│  connectors · memory · identity ·     │ REST+WS │  perception · offline loop  │
│  STT/LLM/TTS · knowledge base         │         │                             │
└───────────────────────────────────────┘         └─────────────────────────────┘
```

The Pi runs **only** motion + audio I/O + the on-device offline loop (U15). STT,
the LLM, and the knowledge base never run on the Pi.

## 1. Robot side (Pi)

> The real `ReachyRobotAdapter` + Reachy-app packaging is **U16 (🔒 hardware)**.
> Until then, `ROBOT_ADAPTER=fake` runs the same contract on the Pi for wiring tests.

```bash
# on the Pi
git clone <repo> && cd reachy-chief-of-staff
uv sync --package robot-runtime --no-dev
ROBOT_ADAPTER=reachy \           # 'fake' until U16 lands
  PORT=8001 \
  CORS_ORIGINS=http://<laptop-ip>:5173 \
  BRAIN_LINK_TIMEOUT_S=15 \
  uv run --package robot-runtime robot-runtime
```

Verify: `curl http://<pi-ip>:8001/health` → `{"status":"ok", ...}`.

## 2. Brain side (laptop)

```bash
# point the brain at the Pi (the one network hop) + enable the heartbeat
ROBOT_RUNTIME_URL=http://<pi-ip>:8001 \
  HEARTBEAT_ENABLED=true \
  UPSTREAM_HEALTH_URL=https://api.openai.com/v1/models \   # any liveness URL
  LLM_PROVIDER=openai OPENAI_API_KEY=sk-... \
  STT_PROVIDER=null TTS_PROVIDER=null \                     # or openai_realtime
  M365_CONNECTOR=mock \
  PORT=8000 \
  uv run --package aura-brain aura-brain
```

Or via Docker on the laptop (`infra/dev/docker-compose.yml`) with
`ROBOT_RUNTIME_URL` pointed at the Pi instead of the bundled robot-runtime.

## 3. Operator console

Point the console at the brain origin (already the compose default) and the Pi WS:

```
VITE_ORCHESTRATOR_URL=http://<laptop-ip>:8000
VITE_ORCHESTRATOR_WS=ws://<laptop-ip>:8000/ws/events
VITE_IDENTITY_URL=http://<laptop-ip>:8000
VITE_CONNECTOR_URL=http://<laptop-ip>:8000
VITE_ROBOT_RUNTIME_WS=ws://<pi-ip>:8001/ws/events
```

## 4. Resilience check (U14 + U15)

- Pull the LAN cable / drop wifi between the hosts:
  - **Robot** (U15): after `BRAIN_LINK_TIMEOUT_S` it speaks "lost my brain", idles,
    and emits `RobotModeChanged(→OFFLINE)`.
  - **Brain** (U14): the heartbeat marks the robot link down → DEGRADED; if upstream
    internet is also down → OFFLINE, and turns fall back to the local agent.
- Reconnect → robot recovers (→ONLINE) on the next command; brain heartbeat
  RECOVERING → ONLINE after the stability window.

## Notes

- Keep both hosts on the same LAN/subnet; the brain reaches the Pi by IP.
- Firewall: allow inbound 8001 on the Pi and 8000/5173 on the laptop.
- The Pi cannot host STT/LLM/knowledge — keep those on the laptop (Pi 5 compute).
