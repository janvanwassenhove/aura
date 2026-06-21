# Phase 1 Design — Collapse to `aura-brain`

Companion to [ADR-007](adr/ADR-007-topology-and-capability-reshape.md) and
[reshape-plan.md](reshape-plan.md) Phase 1. **Read and approve before code moves.**

## Goal

Merge the five laptop-side services into **one process** (`aura-brain`), keeping
their module boundaries as packages. Delete the cross-service HTTP hops; keep the
one boundary that's real — **brain ↔ `robot-runtime` (the Pi)**.

## What merges, what stays a boundary

```
┌───────────────────────── LAPTOP ──────────────────────────┐     ┌──── PI (Reachy) ────┐
│  aura-brain  (one FastAPI process, one AsyncEventBus)      │     │   robot-runtime      │
│                                                            │ WS  │                      │
│   orchestrator · conversation · connector · memory ·       │◄───►│  motion · audio I/O  │
│   identity   (all in-process modules)                      │ /REST│  perception · offline│
└────────────────────────────────────────────────────────────┘     └──────────────────────┘
```

- **Merge into `aura-brain`:** `orchestrator`, `conversation-runtime`,
  `connector-service`, `memory-service`, `identity-service`.
- **Stays a network service:** `robot-runtime` — it runs on the Pi (ADR-007),
  so brain↔robot remains WS (events) + REST (commands). This is the boundary the
  heartbeat watches (Phase 2).

## The HTTP seams being collapsed (measured)

| Caller → Callee | Call site | Becomes |
|---|---|---|
| orchestrator → connector | `pipeline._call_connector` (`CONNECTOR_SERVICE_URL`) | in-process call to connector module |
| orchestrator → memory | `fallback_agent._create_reminder` (`MEMORY_SERVICE_URL`) | in-process MemoryStore call |
| orchestrator → identity | token lookups (`IDENTITY_SERVICE_URL`) | in-process TokenStore call |
| conversation → memory | `conversation_runtime.main` (`MEMORY_SERVICE_URL`) | in-process MemoryStore call |
| connector → identity | `connectors/{github,google,slack,workiq}` token fetch | in-process TokenStore call |
| orchestrator → conversation | `CONVERSATION_RUNTIME_URL` | in-process call |
| orchestrator → **robot** | `ROBOT_RUNTIME_URL` | **unchanged — stays HTTP/WS to the Pi** |

## Target layout

```
apps/aura-brain/                 (or services/aura-brain/)
  src/aura_brain/
    main.py            # one FastAPI app; mounts all routers; owns the bus + WS broadcaster
    deps.py            # builds the singletons (MemoryStore, TokenStore, connectors,
                       #   pipeline, persona) once and injects them in-process
    (modules below are the EXISTING packages, imported — not rewritten)
  pyproject.toml       # unions the five services' deps; one lockfile entry
```

The five `services/*/src/<pkg>` packages stay as importable libraries; only their
**FastAPI app wiring** is replaced by `aura_brain.main` mounting their routers and
their **HTTP clients** are swapped for in-process handles via `deps.py`.

## Migration order (each step keeps the suite green)

1. **Scaffold** `aura-brain` with the shared `AsyncEventBus` + WS broadcaster and a
   `/health`. No behavior yet. Compose still runs the old services.
2. **Mount routers** from each module into `aura_brain.main` (orchestrator,
   conversation, connector, memory, identity) under their existing paths.
3. **Swap one seam at a time**, smallest blast radius first, behind a thin
   adapter so the module code barely changes:
   a. connector → identity (token fetch) in-process
   b. orchestrator → connector in-process (`_call_connector` calls the module)
   c. orchestrator/conversation → memory in-process (MemoryStore singleton)
   d. orchestrator → identity in-process
   Run the full suite after each.
4. **Single event bus:** point every module's publish at the one bus instance, so
   the WS broadcaster carries the whole stream (today each service has its own).
5. **Compose down to 3** (`aura-brain`, `robot-runtime`, `operator-console`);
   delete the four retired Dockerfiles/health-checks. Update operator-console
   URLs (one orchestrator/brain origin instead of several).
6. **Full-stack smoke** (the deferred Phase 0b item): real LLM + mock connector +
   FakeRobot, one read tool + one **write** tool (approval gate) end-to-end.

## Config / env

Collapse the per-service `*_SERVICE_URL` vars (no longer needed internally). Keep
`ROBOT_RUNTIME_URL` (the Pi). One `.env` for the brain; keyring/token settings
from identity-service move in unchanged.

## Risks & mitigations

- **Lost crash isolation** (one process). Acceptable for one user; mitigate with
  supervised restart and per-module try/except at the router layer. Revisit only
  if a module proves unstable.
- **Import/name clashes** across the five packages — namespaces differ already
  (`orchestrator`, `connector_service`, …), low risk; verify no duplicate route
  paths when mounting.
- **Test conversion**: cross-service integration tests that assumed HTTP become
  in-process; convert as each seam flips (step 3), don't big-bang.
- **Async lifecycle**: one app `lifespan` must start the bus, heartbeat,
  reminder scheduler, and any background tasks the five services started
  separately — enumerate these before step 1.

## Explicitly NOT in Phase 1

- No Pi deployment / `ReachyRobotAdapter` (Phase 2/3d).
- No new capabilities (recognition, dev-agent, knowledge layer — Phase 3).
- No Redis/real cross-host bus — the brain bus is in-process by design.

## Exit criteria

`docker compose up` runs brain + robot + console; the README text-turn works; a
write tool round-trips through the approval gate; full suite green; four service
Dockerfiles deleted.
