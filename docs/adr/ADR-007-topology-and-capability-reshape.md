# ADR-007: Topology & Capability Reshape

**Status**: Proposed
**Date**: 2026-06-21
**Supersedes (in part)**: ADR-002 (event model deferral assumptions), the 6-service split implied by ADR-001
**Owner**: architecture

---

## Context

AURA was built as a 6-service Docker Compose stack with an in-process asyncio
event bus per service and synchronous REST between services. The code quality is
good — the approval gate, gateway auth, schemas, and provider switch are solid.

However, a review against the **actual product goals** (a personal Reachy Mini
"chief of staff") surfaced four structural mismatches:

1. **Over-decomposition.** Six services, six Dockerfiles, six health checks, and
   network hops between them — but the "event bus" (`packages/shared-events`) is
   in-process *per container* and used only to feed each service's WebSocket to
   the operator console. Cross-service communication is plain REST
   (`httpx`). We pay the full cost of microservices and get none of the
   decoupling. For a single-user desk robot this is pure overhead.

2. **Topology doesn't match reality.** Everything runs as one Compose stack on
   one host. The real deployment is **laptop (master) ↔ Reachy Mini**. The
   `HeartbeatMonitor` pings sibling containers on the same host — it does *not*
   watch the laptop↔Reachy link, which is the exact failure the offline
   fallback is supposed to survive. The Reachy's compute also cannot host six
   containers plus STT/TTS plus a local model.

3. **The headline capabilities are absent.** No recognition (face/camera —
   zero code), no outbound dev-agent (drive VS Code / Claude Code), no real
   `ReachyRobotAdapter`, and no local-LLM brain (offline fallback is regex).
   `identity-service` is OAuth-token storage, not person identity.

4. **Tool-calling is not wired end-to-end.** `pipeline.py` calls the LLM
   without passing `tools=`; available tools are injected as *text* into the
   system prompt, so the function-calling API never returns `tool_calls`. The
   connector execution path is effectively unreachable from a real turn.

## Decision

### 1. Collapse to two deployables

| Deployable | Runs on | Owns |
|---|---|---|
| **`robot-runtime`** | the Reachy **Mini Wireless (Pi 5)** — FakeRobot on laptop for dev | motion, audio I/O, **camera/perception**, behavior engine, a local offline behavior loop. The Pi runs *only* these; STT/LLM/knowledge-base never run on-device. |
| **`aura-brain`** | the laptop (master) | orchestration, conversation, connectors, memory, identity/OAuth — as **modules in one process**, not separate services |

The brain's internal module boundaries are preserved (orchestrator / conversation
/ connector / memory / identity stay as packages), but they run in one process
and call each other in-process. The in-process `AsyncEventBus` becomes a genuine
single bus for the brain. The only network boundary that matters — laptop↔Reachy —
becomes explicit and is what the heartbeat watches.

### 2. The laptop↔Reachy link is the resilience boundary

The offline fallback triggers when the **brain↔robot link** (or the brain's
upstream internet) drops — not when a sibling container fails a health check.
`robot-runtime` ships a minimal on-device behavior loop so the robot stays
responsive (idle motion, "I've lost my connection" speech, local wake-word ack)
when the brain is unreachable.

### 3. Add the missing capability spine (priority order)

1. **Perception / recognition** in `robot-runtime`: camera → face embeddings →
   `PersonRecognized{identity, confidence}` event → drives greeting + mode.
2. **Outbound dev-agent tool** in the brain: a tool the LLM can call to drive
   Claude Code / VS Code tasks / shell, **gated by the existing
   `ApprovalManager`**. (Distinct from the inbound OpenClaw gateway.)
3. **Local-LLM provider** (Ollama/llama.cpp) behind the existing provider
   switch, so "offline" degrades to a local model, not regex.
4. **Personal Knowledge & Judgment Layer** ("geweten en kennisbank") — a
   per-person, evolving model of how the owner and family work/react, used to
   anticipate and support. **Owner-only, encrypted at rest, local-only.** This is
   the most privacy-sensitive component and gets its own ADR-008 for the data
   model, crypto, and consent. Recognition (#1) gates which person's store
   unlocks; a stranger unlocks nothing. See `docs/reshape-plan.md` Phase 3e.

### 4. Fix tool-calling before building on it

Pass `tools=` (OpenAI/Gemini function schemas) from `pipeline.py`, OR commit
fully to a text-protocol intent router. Pick one. Today it is neither.

### 5. Treat per-turn latency as a hard gate

Latency targets exist in the specs but the implementation misses them: voice uses
batch `whisper-1`/`tts-1` (not the Realtime API ADR-005 promises), responses
don't stream, there's no barge-in, and a tool turn makes two sequential LLM
calls. The collapse to one process removes the per-turn network hops; the rest is
explicit performance work (streaming STT, token-streamed TTS, barge-in,
single-pass tool calling) gated by *measured* end-to-end latency on the real
hardware + provider. On the Reachy Wireless, STT/LLM never run on the Pi — only
motion and audio I/O do. See `docs/reshape-plan.md` Phase 3.5.

### 6. Demote the delivery-method ceremony

`.github/apm/` and `knowledge/` (a generic enterprise agentic-delivery framework,
~150 files, largely duplicated under `.specify/`) move to `docs/method/` or out
of the product repo. Not load-bearing.

## Consequences

**Positive**
- One process to run the brain; debugging is in-process, not across six HTTP hops.
- Heartbeat and fallback model the failure that actually happens.
- Robot can physically run on the Reachy; brain stays on capable hardware.
- The excellent safety/approval code is preserved and *reused* for the
  highest-risk new capability (dev-agent).

**Negative / risks**
- Merging services touches imports and the Compose file; needs careful, staged
  migration (see `docs/reshape-plan.md`).
- A single brain process loses per-service crash isolation. Acceptable for a
  single-user system; revisit only if a module proves unstable.
- Perception + the knowledge layer add the system's biggest privacy surface —
  face embeddings (biometric) and per-person behavioural profiles are
  special-category personal data (more so for family/children). They must be
  stored locally, **encrypted at rest, owner-access-gated, never egressed to a
  cloud LLM wholesale, never logged**, and be transparently inspectable/erasable
  by the owner (extends Constitution Principle VI; detailed in ADR-008).

## Alternatives considered

- **Greenfield rewrite** — rejected. Throws away genuinely good safety/adapter/
  schema code for no structural gain the reshape doesn't already deliver.
- **Keep 6 services, add real Redis Streams bus** — rejected. Adds infra to
  justify a decomposition the product doesn't need; optimizes the wrong axis.
- **Keep 6 services, just fill the gaps** — rejected as the end state, but
  adopted as an *interim* step: the tool-calling fix and first capability proof
  happen before the topology collapse, to de-risk.

## References

- Constitution — Principles II (HW abstraction), IV (safety gates), VI (no
  sensitive data in logs)
- `docs/reshape-plan.md` — the phased migration
- ADR-002 (event model), ADR-004 (offline fallback)
