# AURA Implementation Backlog (autonomous resume ledger)

This is the **single source of truth** for the autonomous build loop. Each
scheduled session resumes from here. It exists because sessions do **not** share
context — this file is the memory between them.

Branch: **`aura-autobuild`** · Plan: [reshape-plan.md](reshape-plan.md) ·
Design: [phase-1-design.md](phase-1-design.md) · ADRs: [007](adr/ADR-007-topology-and-capability-reshape.md), [008](adr/ADR-008-knowledge-judgment-layer.md)

---

## RESUME PROTOCOL — read this first, every session

1. `git status` clean? If not, inspect — a prior session may have crashed
   mid-unit. Reconcile (commit or revert) before starting new work.
2. Pick the **next unit** that is `[ ]` (todo) **and not** `🔒 BLOCKED`. Work
   top-to-bottom; respect `deps:`.
3. Do the unit. **Write/adjust tests. Run the affected test suite — it must be
   green before commit.**
   - Run a package's tests with: `uv run --package <pkg> --extra dev pytest <path>`
4. Commit on `aura-autobuild` with a message starting `auto(<unit-id>): …`.
5. Edit this file: flip `[ ]`→`[x]`, append the commit short-hash, add a one-line
   note. Commit that ledger update too (or amend into the unit commit).
6. **Token budget:** do **1–3 units per session**, then STOP. Stop *earlier* if you
   sense context filling up — leave margin, do **not** balance on the limit. The
   rule that matters: **never end a session with uncommitted work.** A clean stop
   after 1 unit beats a crash mid-unit-3.
7. If **every** remaining unit is `🔒 BLOCKED`, do nothing, say so, and end the
   loop (don't reschedule).

### `🔒 BLOCKED` markers (the loop must SKIP these, never attempt)
- `🔒 HW` — needs physical hardware (Reachy Pi, camera, mic) → only a human can do.
- `🔒 DECIDE` — needs a human product/security decision first.
- `🔒 SECRET` — needs a credential/account the loop doesn't have.

When a blocked unit is the next logical step, the loop should still advance any
*unblocked* unit further down, and **surface** the blocked item in its summary so
the human can unblock it.

---

## Phase 1 — collapse to aura-brain  (scaffold done: 3263ffc)

- [x] **U1 — mount memory router** · deps: none · `e428c28`
  `set_store(store)` + `ReminderScheduler(ctx.bus)` + `include_router` in `aura_brain.main`.
  Done: `/memory/health` + todo create/list round-trip through the brain; brain suite 3 green.
- [x] **U2 — identity → APIRouter + mount** · deps: none · `98ba088`
  identity routes moved onto an `APIRouter`; `create_app()`/`app` kept for standalone. Brain mounts it; `/identity/persona` reachable; brain suite 4 green.
- [x] **U3 — mount connector router** · deps: U1 · `99252b6`
  Brain lifespan builds `ConnectorRegistry` (mock M365), sets primary+registry, mounts router. `/connector/health` via brain; brain suite 5 green.
- [ ] **U4 — mount conversation router** · deps: U1
  `routes.init(stt, tts, bus=ctx.bus, …)` with mock/echo providers; mount. Done: text-turn route via brain; tests green.
- [ ] **U5 — mount orchestrator router** · deps: U2,U3,U4
  Wire pipeline, persona, approval, gateway, presentation, offline queue against `ctx.bus`; mount.
  Done: `/orchestrate` + `/orchestrator/config/llm` via brain; orchestrator tests green.
- [ ] **U6 — one shared bus, verified** · deps: U5
  Assert every module published onto `ctx.bus`; a single `/ws/events` carries the whole stream. Add a brain integration test.
- [ ] **U7 — seam: connector→identity in-process** · deps: U5
  Replace the HTTP token fetch in `connectors/{github,google,slack,workiq}` with an injected in-process TokenStore handle. Convert its tests.
- [ ] **U8 — seam: orchestrator→connector in-process** · deps: U5
  `pipeline._call_connector` calls the connector module directly (keep an HTTP fallback flag). Convert tests.
- [ ] **U9 — seam: →memory in-process** · deps: U5
  `fallback_agent` + conversation persistence use the in-process MemoryStore. Convert tests.
- [ ] **U10 — seam: orchestrator→identity in-process** · deps: U5
- [ ] **U11 — compose down to 3 services** · deps: U6–U10
  `aura-brain` + `robot-runtime` + `operator-console`. Delete the 4 retired Dockerfiles/health-checks; update operator-console origins to one brain URL.
- [ ] **U12 — full-stack smoke** · deps: U11 · partly 🔒 SECRET (real LLM key)
  FakeRobot + mock connector + real (or echo) LLM: one read tool + one **write** tool through the approval gate, end-to-end. Echo-mode portion is doable now; real-LLM portion uses `OPENAI_API_KEY` if present.

## Phase 2 — laptop↔Reachy split & resilience

- [ ] **U13 — brain↔robot boundary contract** · deps: U11
  Define the WS(events)+REST(commands) contract the brain uses to drive `robot-runtime`. Code + schema; no hardware needed (FakeRobot).
- [ ] **U14 — heartbeat watches the real link** · deps: U13
  Rework `HeartbeatMonitor` to watch (a) brain↔robot link and (b) upstream internet; drive ONLINE/DEGRADED/OFFLINE. Tests with a fake link.
- [ ] **U15 — on-device offline loop** · deps: U13
  `robot-runtime` minimal local behavior (idle motion, "lost my brain" speech, wake-word ack) when brain unreachable. Testable against FakeRobot.
- [ ] **U16 — ReachyRobotAdapter + Pi packaging** · 🔒 HW · deps: U13
  Implement `adapters/reachy.py` against the SDK (same contract tests as Fake); package robot-runtime as a Reachy Mini app. Needs the Pi.
- [ ] **U17 — two-host bring-up docs** · deps: U13 (doc can precede HW)

## Phase 3 — capability spine

- [ ] **U18 — recognition (perception)** · 🔒 HW for camera; schema/store doable now · deps: U11
  Schema (`PersonRecognized`) + encrypted embedding store + enrollment API can be built and unit-tested with fixture images; live camera is 🔒 HW.
- [ ] **U19a — knowledge layer: schemas + person-scoped store** · deps: U11 · ADR-008
- [ ] **U19b — envelope crypto (OMK/DEK, AES-GCM, keyring)** · deps: U19a · ADR-008
- [ ] **U19c — owner-unlock tiers (OS-session + step-up)** · 🔒 DECIDE (unlock UX confirmed in ADR-008 §9 — implement that) · deps: U19b
- [ ] **U19d — transparency/console: inspect-edit-delete a profile** · deps: U19a
- [ ] **U19e — judgment/anticipation layer (stateless over the store)** · deps: U19a,U19c
- [ ] **U20 — outbound dev-agent tool** · deps: U5 · 🔒 DECIDE sandbox scope
  `run_dev_task` gated by `ApprovalManager`, repo allow-list, full audit. Build behind a flag; the allow-list/scope needs human sign-off before enabling.
- [ ] **U21 — local-LLM offline tier wiring** · deps: U5 (Ollama provider already added)
  Make `ollama` the automatic DEGRADED/OFFLINE brain instead of the regex FallbackAgent.
- [ ] **U22 — Realtime API voice transport** · deps: U4 · 🔒 SECRET (key) for live
  Replace batch whisper-1/tts-1 in `conversation-runtime` with the GA Realtime path proven in the spike; barge-in; token-stream. Logic buildable; live run needs the key + audio (🔒 HW).

## Phase 3.5 — performance gate

- [ ] **U23 — per-turn latency instrumentation** · deps: U5
  Emit first-audio + full-turn timings into the event stream; show in console.
- [ ] **U24 — streaming STT + token-streamed TTS + barge-in** · deps: U22
- [ ] **U25 — single-pass / parallel tool calling** · deps: U5
- [ ] **U26 — on-Pi budget guard** · 🔒 HW · deps: U16

## Phase 4 — presentations & polish

- [ ] **U27 — presentations to real slides + synced gestures** · deps: U5
- [ ] **U28 — operator-console pass for new events** · deps: U6,U18,U20

---

## Progress log (append-only; newest last)

- 2026-06-21 — ledger created on `aura-autobuild`; Phase 0/0b complete, Phase 1 scaffold (U-pre) done before this loop started.
- 2026-06-21 — U1 done (`e428c28`): memory router mounted into aura-brain, shared bus. Next: U2 (identity → APIRouter).
- 2026-06-21 — U2 (`98ba088`) + U3 (`99252b6`): identity refactored to APIRouter + mounted; connector registry built + mounted. Brain suite 5 green. Next: U4 (conversation router), then U5 (orchestrator — deps U2,U3,U4 now needs only U4).
