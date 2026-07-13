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
- [~] **U16 — ReachyRobotAdapter LIVE-VERIFIED; Pi packaging remains** · deps: U13 · `<hash>`
  `adapters/reachy.py` over the reachy-mini SDK (optional `[reachy]` extra, lazy import): motion vocabulary (nod/tilt/shake/wave/gesture/point/bow/wake_up/sleep) as head-pose/antenna primitives, media via MediaManager (graceful no_media), sync SDK behind to_thread + motion lock; ROBOT_ADAPTER=reachy wired. 12 stub-SDK contract tests + 3 live tests (REACHY_LIVE=1) **passed against the physical robot over wifi** (192.168.0.178, network mode). Remainder: package robot-runtime to run ON the Pi (needs SSH onto the device) + live media (WebRTC/local ALSA).
- [x] **U17 — two-host bring-up docs** · deps: U13 · `fe11c72`
  `infra/two-host-bringup.md`: run robot-runtime on the Pi + aura-brain on the laptop across the one network hop; env for both sides, console URLs, and a U14+U15 resilience check.

## Phase 3 — capability spine

- [~] **U18 — recognition (perception): non-HW slice done** · deps: U11 · `5bf88cd`
  `EmbeddingMatcher` (enroll/identify via cosine + threshold, embeddings AES-GCM encrypted at rest) + `PersonRecognized` event (broadcast). 🔒 HW remainder: camera capture + frame→embedding model (on the Pi) and the brain greet/mode wiring on a live feed.
  Schema (`PersonRecognized`) + encrypted embedding store + enrollment API can be built and unit-tested with fixture images; live camera is 🔒 HW.
- [x] **U19a — knowledge layer: schemas + person-scoped store** · deps: U11 · ADR-008 · `27cabbb`
  `shared_schemas/knowledge`: models (Person/ProfileFact/ObservedSignal/Relationship/ConsentRecord/RecognitionLink) + KnowledgeStore ABC + InMemory impl. Per-person scoping, erasure, signal reinforcement, minors-explicit-only guard. Suite 88 green (also fixed 2 pre-existing shared-schemas test bugs).
- [x] **U19b — envelope crypto (OMK/DEK, AES-GCM)** · deps: U19a · ADR-008 · `dce86a6`
  `crypto.py` (AES-256-GCM + scrypt, vetted lib) + `EncryptedKnowledgeStore`: per-person DEK wrapped by OMK, at-rest bytes always ciphertext, delete=cryptographic erasure. Contract parametrized across memory+encrypted stores. Shared-schemas 100 green.
- [ ] **U19c — owner-unlock tiers (OS-session + step-up)** · deps: U19b · ~~🔒 DECIDE~~ · DONE
  `StepUpGate` (STEP_UP_WEBHOOK_URL, auto-deny if unset); `UnlockTier` (BENIGN/SENSITIVE); knowledge API gated by tier; `/knowledge/lock`, `/knowledge/tier`, `/knowledge/stepup/callback/{token}/grant|deny`; `set_omk_loaded()` wired in main. Brain 23 green.
- [x] **U19d — knowledge transparency (API + console view)** · deps: U19a · `1fe53d0` + `11c2d3a`
  Brain `/knowledge/*` API: list/inspect (facts+signals)/add+delete fact/erase person/consent; encrypted store when KNOWLEDGE_PASSPHRASE set. Brain 15 green. Console: `knowledgeStore` (Pinia, 403→locked banner) + `KnowledgePanel.vue` modal (🧠 header button): people list w/ role badges, person detail (facts editable, signals read-only w/ confidence), add person/fact, forget-person w/ confirm, tier badge + Lock button, minor-policy note. Console 45 green (16 new).
- [x] **U19e — judgment/anticipation layer (stateless over the store)** · deps: U19a,U19c · `8783ab5`
  `JudgmentLayer` (shared-schemas): builds a minimal `PersonContext` per turn — guest→name only, minor→explicit facts only (ADR-008 §10), family/owner→top-N facts + high-confidence signals. `PersonContext.to_system_note()` injected into pipeline system prompt. Brain subscribes to `PersonRecognized` to track active person. Shared-schemas 117 green, orchestrator 137 green, brain 23 green.
- [ ] **U20 — outbound dev-agent tool** · deps: U5 · ~~🔒 DECIDE~~ · DONE
  `DevAgentTool`: classify read/write/commit/push; auto-approve reads; `ApprovalManager` step-up for writes/commit/push; cross-repo always asks; Claude Code escalation via `DEV_AGENT_BACKEND=claude` with separate approval. Gated by `DEV_AGENT_ENABLED=true`. Orchestrator 139 green.
- [x] **U21 — local-LLM offline tier wiring** · deps: U5 · `f2a4864`
  Pipeline offline path tries a local model (OFFLINE_LLM_PROVIDER, e.g. ollama) before the regex FallbackAgent; `openai_chat` gained per-call provider/model overrides. Orchestrator 113 green.
- [~] **U22 — Realtime API voice transport (logic done)** · deps: U4 · `32ad906` · 🔒 SECRET+HW for live
  `RealtimeVoiceSession` (conversation-runtime): GA-protocol state machine over an injectable wire — server VAD, b64 PCM in/out, text turns, transcript deltas, barge-in (response.cancel + on_interrupt). 10 tests over a fake wire; conversation-runtime 20 green. Remainder: live socket + mic/speaker wiring (🔒 SECRET key + HW).

## Phase 3.5 — performance gate

- [x] **U23 — per-turn latency instrumentation** · deps: U5 · `aec8518`
  `TurnLatencyMeasured` event (total/llm/tool ms, first_audio_ms=None until voice) emitted every turn, wired through broadcaster → console. Orchestrator 114 green.
  Emit first-audio + full-turn timings into the event stream; show in console.
- [ ] **U24 — streaming STT + token-streamed TTS + barge-in** · deps: U22
- [x] **U25 — parallel tool calling** · deps: U5 · `afdb299`
  Tool loop split into a sequential gate pass + a concurrent (asyncio.gather) execution pass for independent tools; approval-gated tools still serialize. A multi-tool turn pays the slowest tool, not the sum. Orchestrator 115, brain 13 green.
- [ ] **U26 — on-Pi budget guard** · 🔒 HW · deps: U16

## Phase 4 — presentations & polish

- [x] **U27 — presentations: synced speech+gesture + co-pilot** · deps: U5 · `f1127d9`
  PresentationManager drives speech + slide motion_cue concurrently (RobotDriver Protocol; brain injects RobotClient) with advance()/previous() navigation. Orchestrator 118, brain 13 green.
- [x] **U28 — operator-console pass for new events** · deps: U6,U18,U20 · `df26bbc`
  `robotStore.ts`: handles `PersonRecognized` (tracks last recognized person + confidence) and `RobotModeChanged` (offline mode from OfflineBehaviorLoop). `conversationStore.ts`: handles `TurnLatencyMeasured` (tracks total/llm/tool ms). `RobotPanel.vue`: shows recognized person name + confidence. `ConversationPanel.vue`: shows per-turn latency bar after each response.

## Phase 5 — final development (device-day readiness)

- [x] **U29 — encrypted knowledge store persists to disk** · deps: U19b · `3965153`
  `EncryptedKnowledgeStore(path=…)`: ciphertext bundles + wrapped DEKs load at init, atomic flush on every mutation; erasure reaches disk; plaintext never written. Brain wires `KNOWLEDGE_DB_PATH` when `KNOWLEDGE_PASSPHRASE` set. Shared-schemas 123 green.
- [x] **U30 — interactive setup wizard** · deps: U29 · `1294049`
  `python -m aura_brain.wizard`: robot link (+health check), LLM provider/key, voice, offline resilience, security (passphrase confirm + opt-in .env storage, random salt, step-up webhook, dev-agent), persona, connectors, and person seeding (owner/family/guest/minor + facts) directly into the encrypted store. Secrets never echoed; refuses plaintext people. Compose /data → bind mount; knowledge env passthrough. Brain 30 green.
- [x] **U31 — full documentation pass** · deps: U29,U30 · `eb5355b`
  README overhaul (topology, quickstart, security-model table, layout, status); `docs/setup-guide.md` (device day: unboxing → wizard → security §5 → voice → resilience check → day-two ops table); `.env.example` refresh (dropped removed anthropic/ollama providers, added knowledge/security + OFFLINE_LLM_BASE_URL sections).
- [x] **U21-fix — offline tier repaired after provider simplification** · `6abfa90`
  `_offline_reply` passed removed provider=/model= kwargs to `openai_chat` (TypeError). Now calls a local OpenAI-compatible server via `local_chat(OFFLINE_LLM_BASE_URL, OFFLINE_LLM_MODEL)`; regex fallback last. Orchestrator 138 green.

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
- 2026-06-21 — U17 (`fe11c72`) + U19a (`27cabbb`): two-host bring-up doc; knowledge-layer foundation (models + person-scoped store, ADR-008). Knowledge layer started. Next unblocked: U19b (envelope crypto for the store), U21 (local-LLM offline tier), U23 (latency instrumentation), U18 schema/store part. 🔒 U16/U26 (HW), U19c/U20 (DECIDE) still blocked.
- 2026-06-21 — U19b (`dce86a6`) + U21 (`f2a4864`): knowledge store now has real envelope encryption (AES-GCM, per-person DEK/OMK, cryptographic erasure); offline tier prefers a local model over regex. **Remaining unblocked: U23 (latency instrumentation), U25 (single-pass tool calling), U18 schema/store part, U19d (console — Vue/TS), U27/U28 (presentation/console).** 🔒 BLOCKED: U16/U26 (HW), U19c/U20 (DECIDE), U22/U24 live voice (SECRET/HW), U19e (deps U19c).
- 2026-06-21 — U23 (`aec8518`) + U25 (`afdb299`): per-turn latency event + parallel tool execution. **Remaining buildable (Python): U18 schema/store part (recognition — camera is HW). Remaining is mostly console (U19d/U28 — Vue/TS, need brain knowledge endpoints) + presentations (U27).** 🔒 BLOCKED: U16/U26 (HW), U19c/U20 (DECIDE), U22/U24 (voice HW/SECRET), U19e (deps U19c). Runway nearly exhausted — after U18-store + maybe U27, the rest needs hardware or the DECIDE calls.
- 2026-06-21 — U18 non-HW slice (`5bf88cd`) + U27 (`f1127d9`): recognition matcher + PersonRecognized event; presentation co-pilot (synced speech+gesture). **RUNWAY EXHAUSTED for the autonomous loop.** Every remaining unit is blocked: U16/U26 🔒HW, U19c/U20 🔒DECIDE (your sign-off), U22/U24 🔒voice(HW/SECRET), U19e deps U19c, U18-remainder 🔒HW(camera). U19d/U28 are Vue/TS console work needing brain knowledge endpoints + UI review (deferred — front-end, lower autonomous confidence).
- 2026-06-27 — U19c + U20: owner-unlock tiers (StepUpGate, BENIGN/SENSITIVE, /knowledge/lock, stepup callbacks) + outbound dev-agent (classify read/write/commit/push, ApprovalManager gating, Claude Code escalation with separate approval, DEV_AGENT_ENABLED flag). Brain 23 green; orchestrator 139 green. **Remaining: U19e (deps U19c ✓ now unblocked), U19d Vue view (UI review), U28 (deps U20 ✓ now unblocked). HW/SECRET: U16/U26/U22/U24/U18-camera.**
- 2026-07-03 — orchestrator simplification (dropped anthropic + ollama providers); U19e (`8783ab5`): judgment layer (JudgmentLayer + PersonContext, stateless over knowledge store, data-minimisation per ADR-008 §6/§10, wired into pipeline + brain). U28: operator-console handles PersonRecognized (RobotPanel), RobotModeChanged, TurnLatencyMeasured (ConversationPanel latency bar). **ALL remaining buildable units now complete. Still blocked: U16/U26 🔒HW, U22/U24 🔒voice(HW/SECRET), U18-camera 🔒HW, U19d Vue view (UI review).**
- 2026-07-03 — U19d Vue view: knowledgeStore (Pinia over brain `/knowledge/*`, 403-locked handling) + KnowledgePanel modal (people/facts/signals transparency UI, forget-person, tier badge + lock) wired into App header (🧠). Console 45 green, vite build clean. **U19d fully done. Remaining is HW/SECRET-blocked only: U16/U26, U22/U24 live voice, U18-camera. Optional: U22 transport logic buildable without key.**
- 2026-07-03 — FINAL DEV session (user request): U21-fix (`6abfa90`, offline tier TypeError), U29 (`3965153`, encrypted store persists — profiles survive restarts), U30 (`1294049`, setup wizard: env + encrypted person seeding), U22 logic slice (`32ad906`, Realtime transport state machine w/ barge-in), U31 (docs: README overhaul + docs/setup-guide.md + .env.example refresh). **Software runway fully exhausted — every remaining unit needs the physical device or a live key: U16 (Reachy adapter), U18-camera, U22/U24 live voice, U26. Device-day path: docs/setup-guide.md → `python -m aura_brain.wizard`.**
- 2026-07-13 — DEVICE DAY: robot found at reachy-mini.local (192.168.0.178); daemon initially hung (port 8000 bound, silent) — fixed by a reboot. U16 adapter built + **live-verified**: ReachyRobotAdapter (reachy-mini SDK 1.9, network mode) nodded and waved on the physical robot from the laptop; 12 stub tests + 3 live tests green. **Remaining: robot-runtime packaging ON the Pi (needs SSH), live media path (speaker/mic/camera → unlocks U18-camera + U22 live + U24), U26 budget guard.**
