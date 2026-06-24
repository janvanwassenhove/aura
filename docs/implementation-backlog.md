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
- [x] **U4 — mount conversation router** · deps: U1 · `dedea85`
  Added Null STT/TTS providers (`STT_PROVIDER/TTS_PROVIDER=null`) so it mounts text-first without Whisper/Kokoro; `routes.init(... ctx.bus ...)` + mount. Text turn round-trips (echo fallback). Brain suite 6 green.
- [x] **U5 — mount orchestrator router** · deps: U2,U3,U4 · `960c73a`
  Full orchestrator wiring (pipeline, persona, approval, gateway, presentation, offline queue, webhook dispatcher) on `ctx.bus`; mounted. `/orchestrator/turn` (echo) + `/orchestrator/config/llm` via brain. All 5 modules now one process. Brain suite 7 green.
- [x] **U6 — one shared bus, verified** · deps: U5 · `e2383fd`
  Integration test: an orchestrator echo turn delivers `ResponseDrafted` on `ctx.bus`; broadcaster + pipeline are wired to that same bus instance. Brain suite 8 green.
- [x] **U7 — seam: connector→identity in-process** · deps: U5 · `7389618`
  Connectors gain an optional async `token_fetcher`; when set they skip the HTTP token fetch (HTTP kept as fallback). Registry threads it; identity exposes in-process `get_valid_token`; brain injects it. Connector suite 26 green (+3 seam tests); brain 8 green.
- [x] **U8 — seam: orchestrator→connector in-process** · deps: U5 · `c66e8ca`
  Pipeline gains a `connector_client`; when set it calls the connector module via ASGI in-process (HTTP fallback kept). Also fixed latent bug: `_call_connector` omitted the `/connector` prefix. Brain suite 9 green; orchestrator 110 green.
- [x] **U9 — seam: →memory (+ conversation→orchestrator) in-process** · deps: U5 · `960474d`
  One ASGI `ctx._inproc_client` routes fallback_agent reminders, conversation turn-persistence, and conversation→orchestrator back into the brain app. Brain suite 10 green.
- [x] **U10 — seam: orchestrator→identity in-process** · deps: U5 · `8990dc1`
  No-op by design: orchestrator never calls identity over HTTP; identity is mounted in-brain (U2) + `get_valid_token` in-process (U7). Verified, nothing to flip.
- [x] **U11 — compose down to 3 services** · deps: U6–U10 · `8990dc1`
  Compose now: `robot-runtime` + `aura-brain` (5 merged) + `operator-console`. Added apps/aura-brain/Dockerfile + root .dockerignore; console points all APIs at the brain origin (:8000); deleted 5 retired service Dockerfiles. Compose validates. (Not docker-built here — no docker in this env.)
- [x] **U12 — full-stack smoke (echo/mock part)** · deps: U11 · `e5b58d1`
  `test_smoke.py`: a **write** tool (send_mail) through the collapsed brain — stubbed LLM → approval gate fires → auto-granted in-process → mock connector executes → synthesis reply. Approval gate proven in-path, no key. 🔒 SECRET remainder: live-LLM + Realtime voice run (manual, needs `OPENAI_API_KEY`).

## Phase 2 — laptop↔Reachy split & resilience

- [x] **U13 — brain↔robot boundary contract** · deps: U11 · `b0d9410`
  `aura_brain.robot_client.RobotClient` — connect/status/speak/motion/mode over REST, matching robot-runtime's endpoints. Contract test drives the real robot-runtime (FakeRobot) in-process via ASGI; no hardware. robot-runtime is a test-only dep of the brain (runtime decoupled). Brain suite 13 green.
- [x] **U14 — heartbeat watches the real link** · deps: U13 · `2c75031`
  HeartbeatMonitor gains OFFLINE (DEGRADED→OFFLINE when ALL signals down; backward-compatible). Brain wires it to watch ROBOT_RUNTIME_URL/health + UPSTREAM_HEALTH_URL and sets it on the pipeline (degradation→FallbackAgent); gated by HEARTBEAT_ENABLED. Heartbeat 7, orchestrator 111, brain 13 green.
- [x] **U15 — on-device offline loop** · deps: U13 · `7f2f569`
  `OfflineBehaviorLoop` in robot-runtime: brain commands `_touch()` liveness; on timeout the robot speaks a one-time "lost my brain" notice + idles + emits RobotModeChanged(→OFFLINE), recovering on next command. Verified vs FakeRobot. Robot suite 28 green.
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
- 2026-06-21 — U4 (`dedea85`) + U5 (`960c73a`): conversation (null providers) + orchestrator mounted. **Phase 1 step 2 (mounting) COMPLETE — all 5 modules serve from one aura-brain process, one shared bus.** Brain suite 7 green. Next: U6 (verify single bus end-to-end), then seams U7–U10.
- 2026-06-21 — U6 (`e2383fd`): shared-bus invariant verified (brain suite 8). Stopped at 1 unit — next is U7, a 4-connector seam (github/google/slack/workiq → identity in-process) better suited to a fresh budget. Approach: add an injectable async `token_fetcher(user_id, provider)` to those connectors + registry; identity exposes an in-process token helper; brain injects it.
- 2026-06-21 — U7 (`7389618`): connector→identity seam flipped in-process across all 4 connectors + registry + identity helper + brain wiring (large multi-file unit; stopped at 1). Next: U8 (orchestrator→connector in-process — `pipeline._call_connector` calls the connector module directly, keep HTTP fallback flag).
- 2026-06-21 — U8 (`c66e8ca`) + U9 (`960474d`): orchestrator→connector and →memory seams flipped in-process via one ASGI client; also fixed a latent `/connector` prefix bug. Only U10 (orchestrator→identity) seam remains — note orchestrator doesn't yet call identity directly (no current HTTP seam in pipeline); U10 is mostly verifying/wiring identity access. Then U11 (compose→3) + U12 (smoke, 🔒 SECRET part).
- 2026-06-21 — U10 (no-op, verified) + U11 (`8990dc1`): **Phase 1 COMPLETE — compose collapsed to 3 services (robot-runtime + aura-brain + console).** Next: U12 full-stack smoke (echo-mode portion doable; real-LLM/write-tool part is 🔒 SECRET). After that, Phase 2 starts: U13 (brain↔robot boundary contract).
- 2026-06-21 — U12 (`e5b58d1`, echo/mock part) + U13 (`b0d9410`): write-tool/approval-gate smoke through the brain; brain↔robot RobotClient contract (tested vs FakeRobot). **Phase 2 underway.** Next: U14 (heartbeat watches brain↔robot link + upstream net) and U15 (on-device offline loop) — both buildable vs FakeRobot. 🔒 HW units (U16 Reachy adapter/Pi pkg, U26) and 🔒 DECIDE (U19c, U20) still pending.
- 2026-06-21 — U14 (`2c75031`) + U15 (`7f2f569`): heartbeat now watches the real failure surface (robot link + upstream) with an OFFLINE state; robot has an on-device offline behavior loop. **Phase 2 resilience done.** Next: U17 (two-host bring-up docs, no HW) then Phase 3 non-HW units: U19a (knowledge schemas+store), U18 schema/store part. 🔒 U16 (Reachy adapter — HW), 🔒 U19c/U20 (DECIDE) remain blocked.
