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
- [x] **U16 — ReachyRobotAdapter + Pi packaging: DEPLOYED ON THE ROBOT** · deps: U13 · `66ecaa0`
  `adapters/reachy.py` over the reachy-mini SDK (optional `[reachy]` extra, lazy import): motion vocabulary (nod/tilt/shake/wave/gesture/point/bow/wake_up/sleep) as head-pose/antenna primitives, media via MediaManager (graceful no_media), sync SDK behind to_thread + motion lock; ROBOT_ADAPTER=reachy wired. 12 stub-SDK contract tests + 3 live tests (REACHY_LIVE=1) **passed against the physical robot over wifi**. Pi packaging DONE (2026-07-14): repo on the Pi at ~/aura (git bundle), uv-synced, running as systemd service `aura-robot-runtime` (boot-enabled, auto-restart, After=reachy-mini-daemon) on :8001 with ROBOT_ADAPTER=reachy + localhost daemon; live wave/nod/gesture executed through OUR REST API on the Pi. Open: live media path (daemon's WebRTC signaling :8443 not up — needed for camera/mic → U18-live/U22-live/U24).
- [x] **U17 — two-host bring-up docs** · deps: U13 · `fe11c72`
  `infra/two-host-bringup.md`: run robot-runtime on the Pi + aura-brain on the laptop across the one network hop; env for both sides, console URLs, and a U14+U15 resilience check.

## Phase 3 — capability spine

- [x] **U18 — recognition (perception): full loop wired** · deps: U11 · `5bf88cd` + `5825b99`
  `EmbeddingMatcher` (enroll/identify via cosine + threshold, embeddings AES-GCM encrypted at rest, now disk-persisted like U29) + `PersonRecognized` event. Live loop: robot-runtime `GET /robot/camera/frame` → `RobotClient.camera_frame()` → brain `PerceptionLoop` (pluggable `FaceEmbedder`: null inert / insightface via `[recognition]` extra) → debounced `PersonRecognized` on the bus (pipeline + console already consume it). `/recognition` API: enroll-from-camera (person must exist in knowledge first), forget, status. Gated: RECOGNITION_ENABLED + requires KNOWLEDGE_PASSPHRASE (biometrics ciphertext-only). Brain 43, robot 42, shared-schemas 123 green. Live camera feed itself still needs the robot's media path up (daemon stability + WebRTC/on-Pi).
- [x] **U19a — knowledge layer: schemas + person-scoped store** · deps: U11 · ADR-008 · `27cabbb`
  `shared_schemas/knowledge`: models (Person/ProfileFact/ObservedSignal/Relationship/ConsentRecord/RecognitionLink) + KnowledgeStore ABC + InMemory impl. Per-person scoping, erasure, signal reinforcement, minors-explicit-only guard. Suite 88 green (also fixed 2 pre-existing shared-schemas test bugs).
- [x] **U19b — envelope crypto (OMK/DEK, AES-GCM)** · deps: U19a · ADR-008 · `dce86a6`
  `crypto.py` (AES-256-GCM + scrypt, vetted lib) + `EncryptedKnowledgeStore`: per-person DEK wrapped by OMK, at-rest bytes always ciphertext, delete=cryptographic erasure. Contract parametrized across memory+encrypted stores. Shared-schemas 100 green.
- [x] **U19c — owner-unlock tiers (OS-session + step-up)** · deps: U19b · ~~🔒 DECIDE~~ · DONE
  `StepUpGate` (STEP_UP_WEBHOOK_URL, auto-deny if unset); `UnlockTier` (BENIGN/SENSITIVE); knowledge API gated by tier; `/knowledge/lock`, `/knowledge/tier`, `/knowledge/stepup/callback/{token}/grant|deny`; `set_omk_loaded()` wired in main. Brain 23 green.
- [x] **U19d — knowledge transparency (API + console view)** · deps: U19a · `1fe53d0` + `11c2d3a`
  Brain `/knowledge/*` API: list/inspect (facts+signals)/add+delete fact/erase person/consent; encrypted store when KNOWLEDGE_PASSPHRASE set. Brain 15 green. Console: `knowledgeStore` (Pinia, 403→locked banner) + `KnowledgePanel.vue` modal (🧠 header button): people list w/ role badges, person detail (facts editable, signals read-only w/ confidence), add person/fact, forget-person w/ confirm, tier badge + Lock button, minor-policy note. Console 45 green (16 new).
- [x] **U19e — judgment/anticipation layer (stateless over the store)** · deps: U19a,U19c · `8783ab5`
  `JudgmentLayer` (shared-schemas): builds a minimal `PersonContext` per turn — guest→name only, minor→explicit facts only (ADR-008 §10), family/owner→top-N facts + high-confidence signals. `PersonContext.to_system_note()` injected into pipeline system prompt. Brain subscribes to `PersonRecognized` to track active person. Shared-schemas 117 green, orchestrator 137 green, brain 23 green.
- [x] **U20 — outbound dev-agent tool** · deps: U5 · ~~🔒 DECIDE~~ · DONE
  `DevAgentTool`: classify read/write/commit/push; auto-approve reads; `ApprovalManager` step-up for writes/commit/push; cross-repo always asks; Claude Code escalation via `DEV_AGENT_BACKEND=claude` with separate approval. Gated by `DEV_AGENT_ENABLED=true`. Orchestrator 139 green.
- [x] **U21 — local-LLM offline tier wiring** · deps: U5 · `f2a4864`
  Pipeline offline path tries a local model (OFFLINE_LLM_PROVIDER, e.g. ollama) before the regex FallbackAgent; `openai_chat` gained per-call provider/model overrides. Orchestrator 113 green.
- [~] **U22 — Realtime API voice transport (logic done)** · deps: U4 · `32ad906` · 🔒 SECRET+HW for live
  `RealtimeVoiceSession` (conversation-runtime): GA-protocol state machine over an injectable wire — server VAD, b64 PCM in/out, text turns, transcript deltas, barge-in (response.cancel + on_interrupt). 10 tests over a fake wire; conversation-runtime 20 green. Remainder: live socket + mic/speaker wiring (🔒 SECRET key + HW).

## Phase 3.5 — performance gate

- [x] **U23 — per-turn latency instrumentation** · deps: U5 · `aec8518`
  `TurnLatencyMeasured` event (total/llm/tool ms, first_audio_ms=None until voice) emitted every turn, wired through broadcaster → console. Orchestrator 114 green.
  Emit first-audio + full-turn timings into the event stream; show in console.
- [x] **U24/U54 — streamed TTS + barge-in (logic layer)** · deps: U22 · `pending`
  `streaming.py`: `split_speech_chunks` (sentence boundaries, min 60 characters,
  tail cap) + `stream_speech` — chunk N+1 is synthesized WHILE chunk N plays on
  the robot, so the first audio arrives after one short TTS call instead of one
  long one. `_embody_reply` uses the streamed path (SPEAK_STREAMING, on by
  default). Barge-in in the VoiceLoop: while speaking, the loop listens in short
  windows; a clearly louder voice (BARGE_IN_FACTOR×gate, which filters speaker
  echo) cuts the wait short and is treated directly as a reply (BARGE_IN, on by
  default). Brain 125 (+8) green. The rest of U24 (real streaming STT over a
  live socket) stays 🔒 SECRET+HW with U22.
- [x] **U25 — parallel tool calling** · deps: U5 · `afdb299`
  Tool loop split into a sequential gate pass + a concurrent (asyncio.gather) execution pass for independent tools; approval-gated tools still serialize. A multi-tool turn pays the slowest tool, not the sum. Orchestrator 115, brain 13 green.
- [x] **U26 — on-Pi budget guard** · deps: U16 · `pending`
  `budget_guard.py`: BudgetGuard samples CPU (/proc/stat delta), memory
  (/proc/meminfo) and SoC temperature (thermal_zone0) every 5s; over budget
  (BUDGET_CPU_PCT=85 / BUDGET_MEM_PCT=90 / BUDGET_TEMP_C=75) → CONSTRAINED. The
  offline idle loop skips idle animations while constrained, giving the Pi
  headroom; `GET /robot/budget` exposes the status to the console. Readers are
  injectable (tested off-Pi; degrades to unconstrained on non-Linux). Robot 54
  (+6) green; verified live on the Pi (temp 47°C, mem 16%, unconstrained).

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

## Phase 6 — commercial desktop app v1.0  (plan: [desktop-v1-plan.md](desktop-v1-plan.md))

- [x] **U33 — design system, theming & custom title bar** · deps: U32 · `8667599`
  `styles/tokens.css` (complete var set, dark/light + 4 accents via
  data-theme/data-accent) + `themeStore` (localStorage-persisted) + an Appearance
  tab in Settings. Every emoji → lucide line icons
  (TitleBar/Robot/Conversation/Approval/Knowledge/Settings; the status glyphs
  ●○✕⟳ replaced too). Frameless window + `TitleBar.vue` (drag region, name +
  status dots, min/max/close through the preload contextBridge IPC; hides the
  window buttons in an ordinary browser). Line-art bot icon (PIL → png+ico) and a
  splash in the house style. Dead `ConnectionsPanel.vue` removed. Console 53
  green (8 new themeStore tests), build clean, verified live in the app.
- [x] **U34/U53 — in-app onboarding & robot setup wizard** · deps: U33 · `pending`
  Brain: `GET /setup/status`
  (setup_done/encrypted/name/robot-url/voice/llm-keys/people_count),
  `POST /setup/config` (env write + persist; secrets are write-only — never
  echoed, live LLM switch via orchestrator.config), `POST /setup/test-robot`
  (probe /robot/status), `GET /setup/discover` (the configured URL +
  reachy-mini.local + a /24 subnet sweep on :8001, 0.8s timeouts, 50 concurrent).
  Console: full-screen `SetupWizard.vue` on first start (6 steps: name+language →
  find/test/scan the robot → LLM provider+key → wake word → security passphrase
  (reuses /setup/secure) → done; skip/later per step; only appears when the brain
  is reachable and SETUP_DONE is missing) + `setupStore` + a Robot tab in
  Settings (address + Test + network scan + Save). The people step points at the
  existing brain panel. Brain 117 (+5), console 56 green, build clean.
- [x] **U35/U52 — connections: honest statuses + a Chrome connector** · deps: — · `pending`
  The registry gained `ConnectorStatus.MOCK` (a Mock class or `is_mock` → never a
  green "Connected" again; the overall count still treats mock as functional).
  `/connector/health` now also reports `music: mock|ok`;
  `POST /connector/test/{key}` is a per-connector probe (one real call, an honest
  "MOCK data" label). Console: amber "Mock data" badge, a Test button per
  connector with a result line, and a Spotify/Sonos card with a token hint. NEW:
  a Chrome connector (`browser.py`, CDP :9222 over HTTP — `list_browser_tabs`
  free, `open_browser_url` APPROVAL_REQUIRED; http(s) only, with a clear hint when
  Chrome runs without the debug port). VS Code control already existed
  (open_in_vscode). A token-in-log grep test (no logger call interpolates a token
  or secret). Connector 40, orchestrator 154, policies 6, console 56 green.
  GitHub device flow/PAT, the Google client-ID wizard and Slack auth.test already
  existed.
- [x] **U36-rest / U51 — mode behaviour profiles (embodiment per mode)** · `pending`
  `embodiment_plan(text, persona_config)`: the active persona's `GestureProfile`
  (shared-personas, which already existed but was being ignored) now decides HOW
  embodied a reply is — silent_desk fully silent and muted (voice_style="silent"),
  work keeps to a restrained nod (motion_ids allow-list), home nod+tilt,
  presentation/demo expressive (amplitude 0.8/1.0, wave stays in demo). The
  pipeline gained a public `persona_config` property; `_embody_reply` applies the
  plan (greetings included — same path). The VS Code link in work mode already
  existed (open_in_vscode). Brain +6 tests, orchestrator 154 green.
- [~] **U36 — embodied conversation: LIVE VIDEO + GREETING done** · deps: U34 · `a1d3684`
  Done (U36a): Pi media working (the daemon requires `/api/media/acquire` BEFORE
  SDK init — `_prime_media()` in the adapter waits for :8443; frame retry 5s;
  service on REACHY_MEDIA=default) → `GET /robot/camera/frame` delivers real
  frames. Brain `/robot` proxy (status/camera/motion, all single-origin for the
  console). Greeting flow: PersonRecognized(known) → wave + speak +
  ResponseDrafted in the console (debounced by the perception loop). Console:
  **VideoPanel** (live feed 1fps, LIVE badge, recognition overlay, "This is me"
  enrol, tidy empty states), **Quick Actions** (wave/nod/gesture/bow) in
  RobotPanel, a getting-started card with suggestion chips in Conversation.
  `build_embedder` now degrades gracefully without insightface; desktop default
  RECOGNITION_ENABLED=true + FACE_EMBEDDER=insightface (only activates with a
  passphrase); insightface+onnxruntime installed on the laptop. Brain 47 green (4
  new), robot 42, console 53, verified live (camera 811 kB through the brain
  proxy, wave {"ok":true}). Rest of U36: mode behaviour profiles,
  ResponseDrafted→gesture per mode, VS Code link in work mode.
- [x] **U37-installer/U55 — installer & release pipeline** · deps: U33–U36 · `pending`
  DECIDE resolved (the repo janvanwassenhove/aura exists). electron-builder NSIS
  config in apps/desktop (extraResources: the Python workspace → resources/aura
  excluding tests/pycache, console dist → resources/console; app v1.0.0).
  main.cjs: packaged-mode paths (`app.isPackaged` → resourcesPath) + a first-run
  bootstrap `ensureBootstrap` (installs uv through the astral.sh installer when
  absent, `uv sync --all-packages`, marker in userData, progress on the splash).
  `.github/workflows/release.yml`: tag v* → every Python suite + the console tests
  → NSIS build on windows-latest → a GitHub Release with the .exe
  (`generate_release_notes`). CHANGELOG.md seeded with v1.0.0. Config verified
  with `electron-builder --dir` (the resources layout is right, 271 MB unpacked).
  Not done: Playwright screenshots in the release, electron-updater (opt-in
  later).
- [x] **U38/U56 — commercial polish & QA** · deps: U37 · `pending`
  A log viewer without telemetry: `logs_api.py` (ring buffer on the root logger,
  `GET /logs/recent?level=&limit=`, nothing to disk or network) + a Logs tab in
  Settings (level filter, refresh, newest first, a "Local only" note). A11y:
  aria-labels on every icon-only title-bar button + a global `:focus-visible`
  outline in tokens.css. User guide in Dutch (`docs/gebruikershandleiding.md`) and
  English (`docs/user-guide.md`): wizard, talking/hands-free/barge-in, people &
  recognition, capabilities & approvals, connections, music, troubleshooting. CI
  extended: the aura-brain suite and a console job (npm test+build) now run too.
  Brain 128 (+3), console 56 green. Not done: a Playwright E2E smoke test and
  release screenshots (a separate iteration).

---

- [x] **U37 — body-yaw follow (the torso turns along)** · deps: U16 · `pending`
  No follow loop of our own needed: the SDK has
  `set_automatic_body_yaw(enabled)` — the daemon turns the torso along with the
  tracked face itself. Adapter `set_body_follow()` (+ restore when tracking is
  re-toggled, reset to 0.0 on off), route `POST /robot/body_follow`, brain proxy +
  `RobotClient.set_body_follow`, capability toggle `body_follow` (BODY_FOLLOW,
  off by default, live hook). FakeRobotAdapter gained set_tracking/set_body_follow
  → the tracking route is now testable too. Robot 48 (+3), brain 106 green;
  verified live on the Pi (on/off → {"body_follow":true/false}).

- [x] **U40 — capabilities/permissions centre + app launcher** · deps: U20,U35 · `d943f88`
  Brain `/capabilities` (GET/POST toggles: dev_agent, app_launch, follow_me,
  speak_replies, gestures, recognition, maintenance; persisted to .env +
  live-apply hooks for dev_agent/follow_me/speak_replies). A `launch_app`
  orchestrator tool + an ALLOWED_APPS allow-list (name=command, argv only,
  approval-gated, env check per call). Console CapabilitiesPanel (shield button
  in the title bar) with toggles, an explanation of the security model, and the
  registered apps. Never a bypass of the approval gate. Brain 86, orchestrator
  143, policies 6, console 56 green.

- [x] **U39 — Spotify + Sonos music control** · deps: U35 · `34c9178`
  `connector_service/music.py` (SpotifyMusic: Web API with SPOTIFY_ACCESS_TOKEN;
  play/pause/next/playlists/devices/favorites; **Sonos through Spotify Connect** —
  target by device name, no separate Sonos API; MOCK mode without a token).
  Routes `/connector/music/*` + orchestrator tools
  (play_music/pause_music/next_track/list_music_playlists/list_speakers) in work
  and home mode. Connector 32, policies 6, orchestrator 146 green; verified live
  (list_speakers + play in mock). Real playback: a one-off Spotify token.
- [x] **U41 — Claude Code dev workflow repaired** · deps: U20 · `d252950`
  `_execute_claude` used flags that do not exist → a real headless invocation
  `claude -p prompt --output-format text --permission-mode acceptEdits`, cwd via
  subprocess, its own 600s timeout, shutil.which. "build an app with VS Code +
  Claude Code" now runs a real coding session (after approval escalation).
- [x] **U42 — conversational memory (a real dialogue)** · deps: U5 · `d252950`
  The pipeline kept NO history between turns → now a per-session rolling window
  (MAX_CONTEXT_TURNS*2) with prior turns sent along; conversational identity
  prefix (any topic, speech-friendly). Live: "what is my favourite colour?"
  remembered across turns. Orchestrator 146 (6 new).

- [x] **U43 — desktop media control (Windows media keys)** · deps: U40 · `d47bd6f`
  `media_control` orchestrator tool: sends the Windows media/volume keys
  (play_pause/next/previous/stop/volume/mute) through ctypes keybd_event → drives
  the app that is ACTUALLY running (Spotify/browser), no token needed; graceful
  on non-Windows. Work and home mode. The Spotify launcher defaults to
  `explorer.exe spotify:` (URI protocol, no exe path needed). "next track"
  verified live (key sent); "open Spotify + play" = launch_app (approval) →
  media_control. Orchestrator 150 (4 new), policies 6 green.

- [x] **U44 — splash encoding, restart-badge UX, audio VU meter** · deps: U40 · `0ccd410`
  (1) Splash: `data:text/html;charset=utf-8` + `&hellip;`/`&middot;` entities → no
  more mojibake (the "startingâ€¦" fix). (2) Restart badges: gestures and
  maintenance are now toggleable LIVE (hooks: gesture detector attach/detach;
  maintenance loop start/stop) — only recognition still needs a restart; the badge
  now appears only for an outstanding change (client `pending`), not permanently.
  (3) Audio: a live VU meter (WebAudio AnalyserNode, RMS → 12 bars) while
  recording plus a "no sound yet" hint — so you can SEE that the mic hears you.
  Brain 86, console 56 green; verified live (gestures/maintenance
  applied_live=true).

- [x] **U45 — talking through Richie's own mic + Knowledge editable** · deps: U36e · `a2227b5`
  (1) Robot mic: reachy `capture_audio` resamples to 16 kHz mono s16le; a new
  `POST /robot/listen` → WAV; RobotClient.listen; brain `POST /voice/listen`
  (records on the Pi → transcribes → pipeline turn, the answer spoken on the
  robot). A bot-mic button in ConversationPanel ("Richie is listening on his own
  mic…"). Verified live: /robot/listen → a valid 16 kHz WAV (86 kB/3s);
  /voice/listen graceful on silence. (2) Knowledge editable: name and role
  editable inline (blur→renamePerson/upsertPerson) and a fact's key and value
  editable inline (blur→updateFact = add+delete). Robot 45, brain 86, console 56
  green.

- [x] **U46 — mic gain + UI breathing room** · deps: U45 · `deba026`
  Robot mic: the Reachy mic array is barely sensitive even at maximum ALSA gain
  (RMS 0.0008 ≈ silence) → adaptive peak normalisation in capture_audio (target
  0.5, gain cap 40, MIC_TARGET_PEAK/MIC_MAX_GAIN env). Live: a recording is now
  RMS 0.08 / peak 0.5 (usable for Whisper, was ~100× too quiet). UI: roomier
  spacing (panel padding, status row gap, section labels, mt-3, quick-action
  buttons) — less cramped. Robot 45 green, console build clean.

- [x] **U47 — hands-free wake word + keep-talking conversation** · deps: U45,U46 · `c1702f1`
  `VoiceLoop` (brain): runs continuously on the robot mic, behaviour set by env
  (VOICE_MODE=off|wake_word, WAKE_WORD, readable live). VAD from the raw mic peak
  (the X-Audio-Peak header of /robot/listen) → skip silence without paying for
  STT. The wake word starts a turn ("Richie, …" → the command is the remainder);
  after EVERY spoken answer (a greeting included) a follow-up window opens so you
  can keep talking without the wake word; echo guard (waits until the robot has
  finished speaking). Setting in Settings→Appearance (Hands-free: off/wake word +
  a wake-word field) through /setup/prefs (voice_mode+wake_word, persisted).
  Verified live: the loop polls /robot/listen roughly every 4s in wake_word mode.
  Brain 92, robot 45, console 56 green.

- [x] **U48 — an honest Spotify mock + an "always allow" memory** · deps: U39,U40 · `e25f181`
  (1) The mock `play_music` no longer lies about success → it returns "NOT PLAYED,
  no account connected" and points at the media-key fallback or a token; AURA now
  says honestly that it is not playing. (2) ApprovalManager auto-approve set
  (AUTO_APPROVE_TOOLS env + .env persist): grant(remember=True) → remembers the
  tool → no dialogue next time; `/orchestrator/approval/auto` GET and
  `/auto/{tool}` POST. ApprovalPanel: an "Always allow" checkbox beside Grant.
  CapabilitiesPanel: an "Always-allowed actions" list with revoke (back to
  asking). Verified live: honest answer plus auto-approve set/list/revoke.
  Orchestrator 154, connector 32, console 56 green.

- [x] **U49 — wake-word hallucinations + greeting spam + Spotify play** · deps: U47,U48 · `61a92cf`
  (1) "Бурын": the wake-word loop transcribed room noise → Whisper hallucinated
  text → that text was fed in as a command. Fix: an `is_plausible_command()`
  filter (rejects too-short input, known hallucination phrases, and non-Latin
  script for nl/en/fr) plus a mic-normalisation gate raised 0.0015→0.008 (real
  silence stays silent → Whisper returns empty instead of a hallucination).
  (2) Duplicate greetings that interrupted the telling of a joke → a per-person
  greet cooldown (GREET_COOLDOWN_S=120). (3) Spotify: the mock message is now
  directive — it instructs launch_app+media_control(play_pause) to start the REAL
  desktop Spotify (you are logged in); full favourites/Sonos targeting remains
  token-dependent. Brain 92→, robot 45, connector 32 green.
- [x] **U50 — gated Computer Use (see the screen, drive mouse and keyboard)** · deps: U40 · `pending`
  An answer to the "secure OpenClaw" question: Anthropic's own computer-use tool
  (`computer_20251124`, beta header `computer-use-2025-11-24`, Opus 4.8) lets AURA
  operate any desktop app — screenshot → one action → screenshot to verify — when
  launch_app/media_control are not enough. `ComputerUseAgent` (a loop with an
  injectable Anthropic client + an `InputBackend` protocol; `PyAutoGuiBackend` as
  the real Windows driver). A new `use_computer` orchestrator tool → in
  `APPROVAL_REQUIRED` and the work/home modes (the approval gate is NEVER
  bypassed). Capability toggle `computer_use` **OFF by default**, requires
  `ANTHROPIC_API_KEY` + the `[computeruse]` extra (anthropic+pyautogui+pillow);
  live hook in main. A step cap (`COMPUTER_USE_MAX_STEPS`), per-action logging,
  and a system prompt that forbids passwords, payments and irreversible actions
  on its own (mirroring the global safety rules). 8 new tests (fakes, no
  anthropic/pyautogui needed); brain, orchestrator and policies green.

## Agentic phase (plan: [agentic-plan.md](agentic-plan.md))

- [x] **U57 — agentic loop core** · deps: — · ESSENTIAL · `pending`
  `_orchestrate_impl` is now a genuine multi-round loop: reason → choose tools →
  (approval gate per call, every round) → execute → results back into the context
  → next round; it stops at a final answer (no more tool calls), at
  AGENT_MAX_ROUNDS (default 8, then a forced tool-less synthesis saying the
  budget is spent), or on an owner stop (finish after the current round).
  `AgentRoundStarted/Completed` events (shared-schemas) on the bus → the console
  event log. Steering: `pipeline.steer()` + `POST /orchestrator/agent/steer`
  (guidance is injected as a system note in the next round), `request_stop()` +
  `POST /orchestrator/agent/stop`. Round-1 behaviour is identical to before (all
  154 existing tests stayed green). +5 loop tests (multi-round, budget, steering
  mid-loop, stop mid-loop, approval×2 across 2 rounds). Orchestrator 159, schemas
  123, brain 128 green.
- [x] **U58 — tool ladder + base tools** · deps: U57 · `pending`
  `TOOL_LAYERS` + `LADDER_NOTE` in the system prompt (API→CLI→FS→browser→GUI;
  use_computer explicitly the "emergency exit", escalation one step at a time). A
  new module `laptop_tools.py`: `run_powershell` (APPROVAL, -NoProfile
  -NonInteractive, 60s timeout), `read_file` (free, path-bounded to
  AGENT_FS_ROOTS — resolved paths, `..` escapes refused), `write_file` (APPROVAL,
  same bounds), `git_prepare` (read-only status/diff/diff_staged/log; commit/push
  stays with the run_dev_task tiers). Output capped at 6000 characters per
  result. All four in work mode. Tests and builds already run through run_dev_task
  (read tier auto-approved) — no separate presets needed. Orchestrator 173 (+14),
  policies 6 green.
- [x] **U59 — skills system** · deps: U57 · `pending`
  `orchestrator/skills.py`: Skill + SkillStore — markdown files in SKILLS_DIR
  (default ./skills) with a mini frontmatter
  (name/description/triggers/personas/person/enabled; no yaml dependency),
  file-backed with lazy reload (external edits and U60 self-training are picked up
  without a restart). Matching: enabled + persona filter + person scope (the
  digital twin) + trigger substrings (no triggers → always relevant). Prompt
  injection in the agentic loop: relevant skills in full (max 3, body capped at
  2000), the rest by name and description; "follow a relevant skill exactly and
  say which one". A `/skills` CRUD API in the brain (the owner edits freely; the
  AGENT writes through U60, approval-gated); the store is shared with the pipeline
  in the lifespan. Orchestrator 178 (+5), brain 130 (+2) green. The console panel
  follows in U62.
- [x] **U60 — self-training & teach mode** · deps: U59 · `pending`
  `save_skill` as an agent tool in APPROVAL_REQUIRED (+ work/home): the agent
  proposes a skill or an update, the owner sees and approves EVERY write; deny →
  nothing is written (tested). Prompt nudge: "if the owner corrects you or shows
  you their way of working → propose save_skill" (also when no skills exist yet).
  Teach mode: `POST /orchestrator/agent/feedback` frames owner feedback as a
  teaching moment through the agentic loop — the agent decides for itself whether
  it becomes a skill (gated) and confirms what it learned. Person scope on skills
  (U59) plus person facts (U19) is how the digital twin builds up. Orchestrator
  182 (+4) green.
- [x] **U61 — hooks & subagents** · deps: U57 · `pending`
  `hooks.py`: declarative JSON hooks (AGENT_HOOKS env or hooks.json, editable
  live) — `pre`+`block` deterministically replaces the tool call with the hook's
  message (for example "run the tests first" before `git push`; the model reads
  why and adapts in the next round), `post`+`note` appends a follow-up note to the
  result (for example a linter after write_file). Hooks are policy, not model
  behaviour — they always fire, and they never replace the approval gate. A
  `delegate_subtask` tool: spawns a scoped subagent subloop with a hard-enforced
  read-only allowlist (the restrict parameter in `_run_tool_round` — anything
  outside the list is refused EVEN IF the mode would allow it), its own round
  budget (max 6), and no further delegation or writers. Orchestrator 187 (+5),
  policies 6 green.
- [x] **U62 — console agent UX** · deps: U57 · `pending`
  ConversationPanel gained a live **agent strip** (appears during a loop):
  "Working — round X/Y · tools", a steer input field (→ /agent/steer, lands next
  round) and a Stop button (→ /agent/stop, finish after the current round). A
  **🎓 Teach button** beside Send: sends the input as training feedback (→
  /agent/feedback; the agent may propose a skill — approval-gated). Settings
  gained a **Skills tab**: a list (name/@person/description/on-off toggle), an
  editor (name/description/triggers/person/body), delete; new skills and edits go
  through the owner API without a gate. conversationStore tracks
  AgentRoundStarted/Completed from the WS stream. Console 56 green, build clean.
  That completes the agentic plan (A–F, U57–U62).

- [x] **U63 — person profile: description + skills reference; Settings layout** · `pending`
  Person gained a `description` field (a free-text portrait, encrypted at rest,
  backward compatible) — editable in the brain panel ("About", auto-saved on blur)
  and injected into the judgment context ("About them: …") so conversations
  personalise on it. PUT /knowledge/people gained merge semantics (a
  description-only update leaves name and role alone). The person profile now also
  shows the SKILLS scoped to that person ("their way of working") with a pointer
  to 🎓/Settings→Skills — the profile is one place with everything AURA knows about
  someone. Settings modal: 36rem wide (the tabs were cut off at 26rem with six
  tabs), tab bar nowrap+scroll, roomier body padding. Brain 132 (+2), schemas 123,
  console 56 green.

- [x] **U64 — screen control without an Anthropic key (OpenAI fallback)** · `pending`
  `OpenAIComputerAgent`: the same screenshot→act→verify loop, driven by the OpenAI
  key conversations already use (vision + function calling, default gpt-4o,
  COMPUTER_USE_OPENAI_MODEL overridable). A provider ladder in
  `create_default_agent`: Anthropic native when the key is there (best at this
  work) → otherwise OpenAI → otherwise off. Same system prompt and safety, same
  step cap, same approval gate. Capability text updated. Brain +3 tests
  (click→done, step cap, ladder).
- [x] **U65 — voice choice (global and per persona)** · `pending`
  `TTS_VOICES` (11 gpt-4o-mini-tts voices) + `resolve_voice(persona)`: a
  per-persona override through `TTS_VOICE_<MODE>` env, otherwise the global
  preference `TTS_VOICE` (read live). The prefs API gained `tts_voice`
  (validated); Settings gained a "Robot voice" dropdown with a description per
  voice (Onyx — deep male, Nova — energetic female, …). `_embody_reply`
  synthesizes with the persona voice on both TTS paths (streamed and classic).
- [x] **U66 — adding skills from the person screen + 🎓 UX** · `pending`
  The person profile gained a quick-add row under SKILLS (name + procedure → POST
  /skills with person scope, description automatically "X's way of working"). The
  🎓 button: always clickable; with an empty input field an inline hint now appears
  ("type your lesson first…") instead of silently doing nothing — that was the
  "🎓 does not respond" problem (the backend endpoint worked, curl 200).

- [x] **U67 — self-conversation fix + honest music + skill cards** · `pending`
  (1) The "Nordmeer incident": Spotify played through the robot speaker → the mic
  heard lyrics → every follow-up window fed the next turn → an endless
  self-conversation. Fix: the follow-up chain is capped (FOLLOWUP_CHAIN_MAX=2
  wake-word-less turns, after which the wake word is required again; hearing the
  wake word resets the chain) + BARGE_IN_FACTOR 2.5→3.0 (robot-speaker echo).
  (2) The "favourites" lie: the music mock directive now explicitly forbids
  claiming that specific music is playing — a media key only resumes whatever was
  already queued; the answer must point at Settings → Connections for real
  favourites and Sonos. (3) Skills tab: cards instead of rows (name + @person +
  description + body preview + trigger/mode chips, dimmed when off). Brain 136
  (+1), connector 40, console 56 green.
- [x] **U68 — brain vault (option a) + [[link]] rendering in-app** · DECIDE: the owner chose (a)+links · `pending`
  Vault: the skills directory is now a self-describing Obsidian-compatible vault
  (an auto-README on first save, excluded from the skill loader); person data
  stays encrypted in-app. [[links]]: `WikiText.vue` renders `[[target]]` as
  clickable links; `navStore` handles cross-navigation (click `[[jan]]` in a skill
  → the Knowledge panel on that person; click a skill name or `[[skill]]` in a
  profile → Settings→Skills with the editor open; the @person badge on skill cards
  is clickable). Backlinks: skills mentioning `[[person]]` appear in the profile
  with a "backlink" chip (beside scope skills). The description field gained a
  live link preview and a hint. The editor placeholder explains [[..]].
  Orchestrator 187, brain 137, console 56 green. The follow-up step (c: graph
  view) stays open as a later iteration.

- [x] **U69 — music guard: lyrics can no longer become a conversation** · `pending`
  A structural fix on top of U67 (which had not been restarted yet at the time of
  the NOFX incident): as soon as AURA starts or operates music itself
  (ToolCallSucceeded on play_music/media_control/next_track →
  `note_music_started()`), follow-up windows are disabled entirely for
  MUSIC_GUARD_S (default 180s) — only the wake word still gets through (lyrics
  rarely contain "Richie"; tested that wake-word commands keep working during the
  guard). Plus a prompt fix in LADDER_NOTE: "you CAN open Spotify — never claim
  otherwise; on a music request ACT (launch + play) instead of asking more
  questions, and report honestly what you could not choose" (against the
  contradictory 'cannot open'/'opening anyway' behaviour). Brain 139 (+2),
  orchestrator 187 green.

- [x] **U70 — Computer Use made to work: pyautogui + a scaling layer + picking a track on screen** · `pending`
  (1) The warning "No module named 'pyautogui'" → pyautogui installed in the venv
  (`uv pip install pyautogui`; backend verified live, screen 3440×1440).
  (2) `ScaledBackend`: the model sees screenshots at most COMPUTER_USE_MAX_DIM=1456px
  (vision models rescale ultrawide screenshots internally → clicks landed beside
  their target); clicks, drags and scrolls are scaled back up to real pixels;
  a no-op on small screens. (3) LADDER_NOTE: choosing a specific track MAY go
  through use_computer (open Spotify, search on screen, play) — legitimate GUI use,
  because no lower layer can select a specific track; approval still applies per
  use. Brain 141 (+2), orchestrator 187 green.

- [x] **U71 — starter skill: a specific track through the screen** · `pending`
  An answer to "can't he learn that in a skill?" — yes, that is exactly what they
  are for: `skills/spotify-specifiek-nummer.md` seeded (triggers:
  spotify/speel/nummer/…, work+home). The skill forbids guessing with
  media_control on a specific request and prescribes the use_computer procedure
  (ctrl+k → search '<artist> <track>' → play the top result → screenshot
  verification → report honestly which track is playing). Verified: it triggers and
  is injected into the prompt in full. The owner can refine it in Settings →
  Skills; the agent proposes improvements itself through save_skill
  (approval-gated). The 23:40 self-conversation was still running on the
  pre-U67/U69 brain (6 turns — no longer possible after a restart: chain cap 2 +
  music guard).

- [x] **U72 — Brain panel: skills library + a brain per person (commercial layout)** · `pending`
  A new `BrainPanel.vue` behind the brain button in the title bar: on the left a
  rail with avatar initials (Skills library + people with role badges), on the
  right either (a) the **skills library** — "General skills" as hover cards in a
  grid plus per-person groups ("Jan's way of working"), add a new skill inline,
  pencil → the Settings editor, [[links]] clickable; or (b) the **brain per
  person** — a hero with avatar and role, About (auto-save + link preview), facts
  as chips with × and inline adding, their skills (including backlink chips) with
  a person-scoped quick-add. A "Security & faces" button opens the old Knowledge
  panel (lock/tier/enrol/unknown visitors stay there). [[person]] links elsewhere
  now open this panel. Console 56 green, build clean.

- [x] **U73 — barge-in requires the wake word + GUI wandering fixed** · `pending`
  Diagnosis of "Er war in den 18.": Richie's speaker sits next to his own mic —
  loudness alone can never tell self-echo apart from the user, so the barge-in
  triggered on his own TTS (transcribed, garbled, as German). Fix: a barge-in now
  only counts when the transcript contains the WAKE WORD ("Richie, stop") — his own
  echo never says his own name; the loudness gate stays as a cheap pre-filter.
  `use_computer` added to the music-guard trigger set (a GUI run can start audio).
  The skill was tightened: work ONLY in the Spotify window, never help/Connect
  links or a browser (it had wandered off to support.spotify.com), close overlays
  with esc, and on "playing on another device" pick the devices icon → 'This
  computer' and verify with the progress bar. Brain 142 (+1 new, 1 adjusted)
  green. Note: the chain cap (U67) was visibly working already — 2 phantom turns
  instead of 6.

- [x] **U74 — upgrade to gpt-5.1 (chat + screen control)** · `pending`
  The key turns out to have gpt-5/5.1/5.2. Switched over: `OPENAI_MODEL=gpt-5.1`
  (conversations, the agentic loop, tool choices — which should sharply reduce the
  aimless digressions and inconsistent tool claims) and
  `COMPUTER_USE_OPENAI_MODEL=gpt-5.1` (visually stronger than gpt-4o for the
  Spotify GUI runs). Compatibility fix: the OpenAI computer agent now uses
  `max_completion_tokens` (gpt-5.x refuses `max_tokens`; it works on gpt-4o too).
  Everything remains configurable through Settings → LLM / env. Brain computer-use
  tests 13 green.

- [x] **U75 — screen overlay + abort + brain graph** · `pending`
  (1) **The mouse lights up**: `ComputerControlStarted/Ended` events around every
  use_computer run → console → Electron IPC → a click-through always-on-top
  overlay with a glowing cursor ring (following the mouse, 40ms) and a banner
  "AURA is controlling the screen — press Esc to abort". (2) **Abort**:
  `request_abort()` on both computer agents (checked every step) + a wall-clock
  timeout COMPUTER_USE_TIMEOUT_S=180s + `POST /orchestrator/computeruse/abort`;
  abortable with Esc (a globalShortcut while the overlay is up, so it works in ANY
  app) and
  with an Abort button in the conversation strip. (3) **Graph**: `BrainGraph.vue` —
  a dependency-free force-directed canvas constellation in the Brain panel (rail
  item "Graph"): people amber, skills blue, facts as small stars; edges from
  person scope, [[wikilinks]] and facts; hover tooltip, click → open the person or
  skill. Schemas 123, orchestrator 187, computer-use 13, console 56 green.

- [x] **U76 — a VS Code-like workspace: Brain as a dockable panel** · `pending`
  No more popup: the main layout is a **workspace** with draggable splitters
  (pointer drag, min/max clamps) and a **right-hand dock with Brain | Events
  tabs**. The Brain panel gained a `docked` mode (same component: a rail with
  people/skills/graph, narrower in the dock) — the brain button and [[person]]
  links now open the dock (which widens automatically to 480px for Brain). The
  title bar gained VS Code-style **layout toggles** (PanelLeft/PanelRight icons) to
  show or hide the left and right panels. Widths, visibility and the active tab
  persist in localStorage (`layoutStore`, aura-layout-v1). The EventLog moved from
  a fixed column into the Events tab. Console 56 green, build clean.

- [x] **U77 — bottom-dock Events, per-person sources, RobotPanel fix, dancing along** · `pending`
  (1) **Events at the bottom** (terminal style): a horizontal splitter under the
  chat, vertically resizable (110–520px), a PanelBottom toggle in the title bar;
  the right-hand dock is now purely Brain. (2) **Sources per person**: a SOURCES
  section in the person brain
  (instagram/facebook/x-twitter/linkedin/blog/website/gmail/github + handle/url) —
  stored as `source:<kind>` facts: encrypted at rest and automatically in the
  conversation context through the judgment layer; green chips, separate from
  ordinary facts. Actively fetching and reading those sources is a later unit.
  (3) **RobotPanel was cut off**: the flex children gained `flex-shrink: 0` so the
  left column really scrolls instead of clipping. (4) **Dancing along**: as soon
  as AURA starts music, Richie dances along — a separate loop of
  nod/tilt/shake/gesture/wave with random amplitude and tempo,
  DANCE_DURATION_S=25, DANCE_ON_MUSIC=true (can be turned off), best effort. Brain
  142, console 56 green.

- [x] **U78 — a Richie avatar in the conversation** · `pending`
  `RichieAvatar.vue`: a vector portrait of Richie Mini (white head, coil antennae,
  dark goggles, shoulders — after the supplied illustration; theme-aware through
  CSS vars) beside every assistant turn in the chat, with the configured calling
  name instead of a hardcoded "AURA". The "is thinking…" bubble gained a gently
  wobbling Richie. If the owner wants the real artwork PNG: drop it in src/assets
  and swap it in RichieAvatar.vue (noted in the component). Console 56 green.

- [x] **U79 — robot stuck / no tracking: brain-link diagnosis + status touch** · `pending`
  Symptom (the robot stood still, did not follow or recognise): the brain could
  not reach the robot — the mDNS name `reachy-mini.local` no longer resolved from
  the laptop (the proxy said `robot unreachable: ConnectError`), so the robot fell
  back to the offline idle loop (idle_fidget nods that hold the head) and
  recognition stopped (it runs on the brain, which fetches the camera frames).
  Fixed live: the robot address set to the fixed IP through `/setup/config`
  (Settings → Robot; persisted) + head tracking switched back on on the Pi. A
  robustness fix: `GET /robot/status` now calls `_touch()` — a brain that is alive
  and polling but briefly not commanding (an ordinary conversation) no longer
  trips wrongly to offline after BRAIN_LINK_TIMEOUT. Deployed on the Pi and
  restarted. Recommendation in setup: use the IP rather than .local when mDNS is
  unreliable.

- [x] **U80 — speech cut off after one word ("Zeker…") fixed** · `pending`
  Root cause: `play_audio` did one big `media.push_audio_sample(whole sentence)`
  and returned immediately — the SDK drains a small buffer and stops when nothing
  feeds it, so long answers were cut off at roughly 0.5s (the 1s test tone just
  fitted, which is why that one did sound). Fix: push the audio in ~200ms blocks
  at playback pace (sleeping per block) and **block until the whole utterance has
  played** plus a short tail; the motion_lock is held so nothing interrupts the
  speech. A side benefit: streamed TTS (U54) now waits properly per chunk.
  Verified live on the Pi (a 4s tone: the call blocks for roughly the full
  duration instead of <0.5s). Deployed and restarted.

- [x] **U81 — speech still cut off (underrun) + following while speaking** · `pending`
  (1) A follow-up to U80's cut-off: pacing exactly in real time let the device
  buffer run dry between blocks (underrun → the SDK stops) — now roughly 80% of a
  block's duration is slept so the buffer is always fed ahead, plus a longer tail
  (0.4s). Tested with a 6s tone: the call blocks the full duration, no cut-off.
  (2) **Following while speaking**: reply gestures (nod/tilt/shake/gesture/wave) no
  longer pause head tracking (FOLLOW_WHILE_SPEAKING, on by default) — Richie keeps
  his eyes on you while he gestures and talks; the big emotes
  (wake_up/sleep/look_around/point) still manage the head themselves. Robot 54
  green, verified live, tracking switched back on on the Pi. Deployed and
  restarted.

- [x] **U82 — speech very quiet: hardware volume (ALSA) to maximum on connect** · `pending`
  Root cause: the SDK/daemon resets the speaker ALSA control `PCM` at init to
  about 62% = **-23dB** (heavily attenuated) — hence "very quiet" despite the
  digital normalisation. The adapter did set a digital gain (self._volume) but
  never touched the hardware mixer. Fix: `_set_hardware_volume_max()` sets `PCM` to
  100%/0dB on EVERY connect (amixer; overridable through
  SPEAKER_ALSA_CARD/CONTROL, disable with SPEAKER_ALSA_MAX=false); fine control
  stays digital through the app slider. Verified live (55% → 100% after a restart)
  and the ALSA state saved. Robot 54 green. Deployed and restarted.

- [x] **U83 — speech in fragments: through GStreamer playbin instead of appsrc push + streaming off** · `pending`
  The real cause: the appsrc/`push_audio_sample` path drains a small buffer and
  stops — hence the chopping, however much pacing I put on it. The SDK has
  `media.play_sound(file)` (GStreamer playbin into the same sink). `play_audio`
  now writes the (normalised) PCM to a temporary WAV in /dev/shm and plays that
  end to end, blocking until done; aplay was not an option (the device is held by
  the daemon). Additionally: streamed TTS off by default (SPEAK_STREAMING=false) —
  per chunk those were separate playbin files with gaps between them; one synthesis
  and one file plays the whole sentence smoothly. Verified live (a 7s tone end to
  end, no errors). Robot 54 green. The robot fix was deployed and restarted; the
  brain fix (the streaming default) needs an app restart.

- [x] **U84 — natuurlijke conversatie: state machine + echte barge-in + karakters** · `pending`
  Per de conversation-fix-brief, kleinste veilige refactor van alleen de conversatie/audio-laag. (1) `docs/conversation_diagnosis.md` — flow-map, wat werkt/kapot is, latency, waarom barge-in niet kon. (2) `conversation_manager.py`: state machine (IDLE…INTERRUPTED…SHUTTING_DOWN), turn-id's, cancel-tokens voor LLM én TTS, gestructureerde logging per transitie (turn/tts_playing/llm_active/cancel_requested; nooit audio/secrets), one-shot interruptie-context voor de volgende beurt. (3) Barge-in end-to-end: `POST /robot/audio/stop` (playbin→NULL, abortbare play-lus, ook FakeAdapter), speak als geregistreerde cancelbare task, LLM-call geraced tegen cancel-event (breekt mídden in de call), geannuleerde beurt blijft stil. (4) Karakterlaag: `characters.py` + `personas/*.json` (5 seeds: friendly_assistant/dry_tech_butler/kids_companion/workshop_coach/quiet_mode) met alle briefvelden — stuurt prompt, verbosity/humor, stem+snelheid (TTS speed-param), motion-energie en interruptibility (wake_word/vad/off). (5) Settings: character/interrupt_sensitivity/session_memory in prefs + `GET /setup/characters`. Suites: brain 151 (+9), orchestrator 187, robot 54, conversation 20 groen. Robot-deel op de Pi gedeployed. Bewust behouden: modi, skills, guards (U67/U69/U73), lifecycle.

- [x] **U85 — fuzzy wake-word, gevarieerde begroeting, persona-keuze+groei in de app** · `cfb1515`
  (1) Wake-word werkte niet: ASSISTANT_NAME stond nog op "AURA" én Whisper spelt "Richie" wisselend. `wake_word_index()` matcht nu fuzzy (begrensde Levenshtein ≤2 voor namen ≥5 tekens, per token) in start- én barge-in-check; naam op Richie. (2) Begroetingsvariatie: willekeurige invalshoek + "nooit dezelfde woorden"; character.greeting_message wint. (3) Persona in Robot State: dropdown + inline editor (prompt/verbosity/humor/voice/interrupt/learned traits) → POST /setup/characters/{id}; groeit via learned_traits. Brain 153, console 56 groen. Live gezet op de brain.

- [x] **U86 — Richie hoort je niet: VAD-drempel te hoog voor stille mic + live-tuning** · `pending`
  Diagnose: begroeting werkt via de camera, maar de spraaklus gebruikt de mic — en de rauwe piek bij praten (~0.023) lag ONDER de VAD-drempel 0.03, dus elke opname werd als "stilte" overgeslagen. Fix: VOICE_SPEECH_PEAK=0.012 in .env; de drempel wordt nu **live** gelezen (property i.p.v. bij startup) → instelbaar zonder herstart via prefs `mic_sensitivity`. Diagnose-endpoint `POST /setup/voice-check`: neemt op en rapporteert raw_peak/gate/passed_gate/transcript/wake_matched — zo verifieer je voice-input zonder gokken. NB: de fuzzy wake-word-code (U85) + de lagere drempel laden pas bij een **app-herstart** — de draaiende brain draaide nog de oude code (exact-match + gate 0.03). Brain 153 groen.

- [x] **U87 — Whisper laat de naam vallen: STT-prompt-hint + ruimere wake-match** · `pending`
  `voice-check` bewees: mic + drempel + transcriptie werken (peak 0.67, passed_gate), maar het transcript was "Hej." — Whisper dropte "Richie" (en gokte de verkeerde taal). Fix: STT krijgt nu een **prompt-hint** met de assistentnaam+wake-word ("Gesprek met de robot Richie. Aanspreken met 'Richie, …'.") → biast de transcriptie naar de juiste tokens i.p.v. de naam weg te laten. Fuzzy wake-match verruimd met een prefix-guard (eerste 4 tekens): "Rich/Riche/Richy/Ritchie" pakken nu allemaal, terwijl "rietje/prima" terecht falen. Brain suite groen. Vereist app-herstart om de STT-prompt te laden.

- [x] **U88 — "Richie:" wordt hardop meegezegd (sprekerlabel)** · `pending`
  Het LLM zette soms zijn eigen naam als sprekerlabel vóór het antwoord ("Richie: …"), dat vervolgens ook uitgesproken werd. Fix: `_strip_speaker_label` verwijdert een leidend "<naam>:" / "<naam> -" éénmalig (fuzzy op spellingsdrift, zodat ook "Ritchie:" pakt), toegepast op het finale antwoord vóór weergave én TTS; een naam midden in de zin of "Jan:" blijft staan. Plus een expliciete instructie in de identity-prompt om het niet te doen. Orchestrator 188 (+1) groen. Vereist app-herstart.

- [x] **U89 — STT-prompt-echo + latency (reasoning-model + venster)** · `pending`
  (1) De generieke "je praat met Richie…"-reply was Whisper die de STT-prompt-HINT letterlijk terugkaatste bij onduidelijke audio; het model antwoordde daarop. Fix: prompt terug naar kale woord-priming (`"{wake} {name}"`, geen zin) + guard die een transcript dat enkel uit de priming-woorden bestaat weggooit → behandeld als kaal wake-word (lus herluistert naar het commando). (2) **Vertraging**: OPENAI_MODEL stond op gpt-5.1 (reasoning-model, "denkt na" → 3–8s/beurt, dodelijk voor spraak) → **gpt-4o** (snel, live toegepast op de draaiende brain). Opnamevenster live-instelbaar via VOICE_WINDOW_S (default 3s i.p.v. 4). Brain-voice-tests groen. Model terug te zetten via Settings → LLM.

- [x] **U90 — modelrollen: model per taaktype (snel gesprek vs krachtig voor taken)** · `pending`
  `openai_chat(model=…)`-override + `config.model_for_role("chat"/"agent")` (leest CHAT_MODEL/AGENT_MODEL live, alleen OpenAI, anders fallback naar het actieve model). Pipeline: ronde 1 gebruikt het **chat**-model (snel, lage latency voor spraak); zodra een beurt meerstaps wordt (tools in het spel), gebruiken ronde 2+ het **agent**-model (krachtig — bv. gpt-5.1 om Computer Use aan te sturen: Spotify openen, nummer zoeken, afspelen). Computer Use zelf houdt zijn eigen COMPUTER_USE_OPENAI_MODEL. Settings → LLM: drie rol-velden (Conversation / Tasks & tools / Screen control) met model-suggesties + Save. Gezet: chat=gpt-4o, agent=gpt-5.1, computer=gpt-5.1 (live + .env). Orchestrator 190 (+2), console 56 groen. `model=` alleen doorgegeven als gezet (test-fakes blijven werken).

- [x] **U91 — spooktranscripten: STT-echo (U89 nog niet geladen) + follow-up-hardening** · `pending`
  Twee bronnen van "ik heb dat nooit gezegd": (a) "Aanspreken met 'Richie, ...'." = de oude STT-prompt-zin die Whisper terugkaatst — al gefixt in U89 (kale prompt + guard), maar de draaiende brain draaide nog de U87-code → **app-herstart nodig**. (b) "Wat weet ik?" = Whisper-hallucinatie die in een follow-up-venster (zonder wake-word) als commando werd opgevat. Hardening: follow-up-uitingen moeten nu duidelijk luider zijn dan de stilte-gate (FOLLOWUP_PEAK_FACTOR=1.6 → bewuste spraak, geen kamergeluid), én een transcript dat grotendeels de eigen laatste reply is (word-overlap ≥60%) wordt als self-echo geweigerd. Brain 155 (+2) groen. Muziek-/keten-guards (U67/U69) blijven.

- [x] **U92 — spooktranscripten definitief: interruptie-notitie-lek + wake-word-per-beurt** · `pending`
  Screenshot toonde twee bugs: (a) de U84-interruptie-notitie ("[The user interrupted…]") werd vóór het commando geplakt → verscheen letterlijk als je "YOU"-bericht én ging naar het LLM. Fix: de notitie gaat nu via `pipeline.steer()` (systeemboodschap, onzichtbaar), nooit meer in het zichtbare commando. (b) Whisper-gebrabbel ("Alel naenolim", "Yakin bolamenitari") werd in follow-up-vensters (zonder wake-word) als commando opgevat → eindeloze uitgevonden gesprekken. Fix: **FOLLOWUP_S=0 als default** → het wake-word "Richie" is nu élke beurt vereist (betrouwbaar); zet FOLLOWUP_S=8 voor natuurlijke "gewoon antwoorden"-follow-ups. Live-instelbaar. Brain 157 (+2), orchestrator 190 groen. Vereist app-herstart.

- [x] **U93 — Knowledge in Brain-paneel geïntegreerd + skill-triggers uitleg/edit + bare-wake fix** · `pending`
  (1) **Skill-tags = triggers** (niet automatisch): de woorden waarop de skill activeert. In het Brain-paneel nu zichtbaar mét tooltip-uitleg, per-tag × om te verwijderen en "+ trigger" om toe te voegen (→ /skills). (2) **Consolidatie**: het losse "Knowledge — what AURA knows"-modal is weg; Teach face + Forget person + tier-badge + Lock zitten nu ín het Brain-persoonsscherm. Dubbele Brain-knop uit de titelbalk verwijderd (de PanelRight-toggle opent het Brain-dock). (3) **Herhaalgedrag**: bare wake-word ("Richie" zonder commando) startte al een beurt-state en gaf een generiek "waar kan ik mee helpen"-antwoord → phantom-turns. Fix: beurt-state (begin_turn/thinking) start nu pas ná het oplossen van een écht plausibel commando; kaal wake-word met stilte/gebrabbel erna → niets. Brain 157, console 56 groen. Rest van de phantom-turns: FOLLOWUP_S=0 uit U92 (vereist app-herstart).

- [x] **U94 — unlock-endpoint + Add person terug in het Brain-paneel** · `pending`
  Regressie uit U93: de nieuwe Lock-knop zette de tier op BENIGN maar er was **geen unlock** (alleen herstart herstelde SENSITIVE) — dead-end. Fix: `POST /knowledge/unlock {passphrase}` verifieert de passphrase door dezelfde OMK af te leiden (zelfde salt) en te vergelijken met de geladen sleutel — foute passphrase elevate't nooit, passphrase wordt nooit gelogd/opgeslagen. Console: unlock-strook (passphrase-veld + Unlock) verschijnt wanneer locked; en de bij de consolidatie vergeten **Add person** (id/naam/rol) staat nu onder de mensenlijst in het Brain-paneel. Teach face zit al in het persoonsscherm (U93). Brain 158 (+1), console build clean. Live vastzittende BENIGN → app-herstart herstelt SENSITIVE (of unlock na herstart met de nieuwe code).

- [x] **U95 — "Restart brain"-knop: einde aan het herstart-misverstand** · `pending`
  Kern van álle "het werkt nog niet"-meldingen: Ctrl+R herlaadt alleen het console-venster (Vue), NIET het brain-proces (Python child) — dus code-fixes (STT-prompt, bare-wake, followup) én de tier bleven op de oude staat. Geen dataverlies: jan/Nora stonden gewoon in data/knowledge.enc.json; ze waren "weg" omdat de tier op BENIGN stond (locked → /people 403). Fix: Electron-IPC `aura:restart-brain` (stopBrain → wait → startBrain → waitForBrain) + preload-bridge + **Restart-knop in de titelbalk** (alleen in de app; herlaadt de console na een verse brain). Eén klik laadt nu alle nieuwe code/config én herstelt SENSITIVE. Console 56 groen, Electron syntax-checked.

- [x] **U96 — kaal wake-word als commando + benign-lock-verwarring definitief weg** · `pending`
  Data was NOOIT weg (jan/Nora stonden in het versleutelde bestand); ze waren verborgen door de benign-tier. (1) **Spookgesprek-oorzaak gevonden**: mijn STT-prompt-hint deed Whisper "Richie" hallucineren op ruis/robot-echo; de echo-guard gaf het kale wake-word terug → dat werd als commando "richie" naar het LLM gestuurd → generiek antwoord → herhaalt. Fix: `_strip_wake_word` — een commando dat na het strippen van "Richie/Ritchie" <2 tekens overhoudt gaat NOOIT naar het LLM (getest: kaal/echo-Richie → genegeerd, "Richie zet muziek op" → "zet muziek op"). (2) **BENIGN = de unlock-tier** (benign = geen toegang tot profielen, sensitive = volledige toegang). Voor een single-user desktop-app pure verwarring: nu alleen gated ná een *expliciete* Lock (`_explicitly_locked`), dus een verse start toont altijd de profielen. Lock-knop uit het paneel gehaald (footgun); unlock blijft voor het zeldzame API-lock-geval. Brain 160, console 56 groen.

- [x] **U97 — personen "verdwenen" = 500-crash op één corrupte entry (mijn testvervuiling)** · `pending`
  Diagnose: `/knowledge/people` gaf **500**, niet leeg/403 (tier was sensitive). Oorzaak: een van mijn eerdere tests schreef per ongeluk persoon 'x' in het ÉCHTE data/knowledge.enc.json, versleuteld met een andere testsleutel → `get_person('x')` gaf InvalidTag → `list_people` crashte → hele lijst weg (jan/Nora waren prima). Fix: `EncryptedKnowledgeStore.list_people` skipt nu een niet-ontsleutelbare entry (logt een warning) i.p.v. te crashen — één corrupte bundle verbergt nooit meer iedereen. Plus: 'x' verwijderd uit het bestand na verificatie dat jan/Nora wél ontsleutelen (atomic write). Schemas 123 groen. Excuses voor de testvervuiling.

- [x] **U98 — onmisbare "Restart brain"-banner (het draaiende proces was nooit herstart)** · `pending`
  Live bevestigd: bestand schoon (jan+Nora), maar `/knowledge/people` gaf nog steeds 500 → het draaiende aura-brain.exe had het OUDE bestand (met x) én de oude code in het geheugen; console-reload (Ctrl+R) herstart de brain NIET. Álle fixes van de laatste beurten (U89/U92/U93/U96/U97) wachten op een echte proces-herstart. Fix: `knowledgeStore.brainError` (true bij /people 5xx) + prominente **oranje "Restart brain"-banner** in het Brain-paneel met knop (window.aura.restartBrain van U95, met duidelijke fallback "sluit de app volledig af — de X, niet Ctrl+R" als de oude preload de bridge nog niet heeft). Console 56 groen. NB: één volledige app-herstart is nog nodig om U95's preload+banner te laden; daarna werkt de knop.

- [x] **U99 — microfoon aan/uit-toggle in Robot State** · `pending`
  Schakelaar "Microphone" bovenaan het Robot State-paneel (naast Follow me): aan → VOICE_MODE=wake_word (Richie luistert naar "Richie …"), uit → VOICE_MODE=off (de spraaklus idlet, geen mic-luisteren). Zet de pref live via /setup/prefs (leest de huidige stand bij mount); mic-icoon Mic/MicOff. Handig om het luisteren snel stil te leggen zonder naar Settings. Console 56 groen.

- [x] **U100 — slaap-/waakstand in Robot State (echt "doe niets")** · `pending`
  Sleep/Wake-toggle bovenaan Robot State. Slaap = echte modus, geen enkele actie: `ROBOT_ASLEEP=true` gate't `_embody_reply` (geen gesproken antwoorden) én `_on_person_recognized` (herkent stil, geen begroeting), VOICE_MODE=off (mic-lus idlet), head-tracking uit, sleep-pose. Wake herstelt alles (wake_up-emote, VOICE_MODE=wake_word, tracking aan). Endpoints `POST /robot/sleep|wake` + `GET /robot/sleep`; persistent in .env. Console leest de stand bij mount en synct de mic-toggle mee. Brain 160, console 56 groen.

- [x] **U101 — slaap-pose: wegduiken + antennes naar achteren** · `pending`
  De `sleep`-beweging riep de SDK-emote `goto_sleep()` aan; nu een eigen "tucked" pose: kop naar beneden wegduiken (`_rot(x, SLEEP_HEAD_PITCH=0.6)`) + beide antennes naar achteren (`SLEEP_ANTENNA=1.4`), duration 1.4s. `wake_up` herstelt rechtop. Beide instelbaar via env. Live op de Pi geverifieerd (sleep/wake 200). Robot 54 groen. Gedeployed + herstart.

- [x] **U102 — slaap-pose terug naar SDK-emote `goto_sleep()`, maar robuust** · `pending`
  Op verzoek terug naar de standaard SDK sleep-emote i.p.v. de U101 custom pose. De emote "nam" soms niet omdat head-tracking / automatic body-yaw de kop tijdens de beweging terugtrok naar het gezicht. Fix: vóór `goto_sleep()` worden `stop_head_tracking()` én `set_automatic_body_yaw(False)` hard aangeroepen (en `_tracking_on=False` gezet), plus één retry als de SDK-call gooit. Tests verifiëren de volgorde (tracking uit vóór goto_sleep). Live op de Pi geverifieerd (sleep/wake 200, geen retry-warning). Gedeployed + herstart.

- [x] **U103 — persona-graph groeit uit bronnen (blog/website/github inlezen)** · `pending`
  De U77 `source:<kind>`-facts worden nu echt GELEZEN: `POST /knowledge/people/{id}/ingest` haalt fetchbare bronnen op (blog/website/github; github-handle → profiel-URL), stript HTML, laat het chat-model max 8 facts per bron destilleren met `[[wiki-links]]` in de waarde — die verschijnen als nodes/edges in de brain graph. Dedupe op (key,value) zodat herhaald ingesten de graph niet verdubbelt; auth-walled bronnen (instagram/facebook/x/linkedin/gmail) worden eerlijk als "needs login" geskipt. Console: "Grow brain from sources"-knop in het persoonsprofiel met resultaatregel. Nieuwe module `source_ingest.py` + tests. Brain 163, console 56 groen.

- [x] **U104 — brein import/export: ChatGPT/Claude-exports minen + volledige JSON-dump** · `pending`
  Import: `POST /knowledge/people/{id}/import-chats` accepteert de inhoud van een ChatGPT- of Claude-data-export (conversations.json, formaat auto-gedetecteerd); alleen wat de PERSOON zelf schreef wordt gelezen, in ~4k-chunks verpakt (cap IMPORT_MAX_CHUNKS=15, eerlijk gerapporteerd als geskipt) en door het chat-model gedestilleerd tot `[[linked]]` facts — zelfde dedupe als U103, dus her-importeren verdubbelt niets. Export: `GET /knowledge/export` dumpt alle personen/facts/signals als één JSON. Console: "Import chat export…"-filepicker in het persoonsprofiel (lokaal gelezen, alleen naar de eigen brain gepost) en "⬇ Export brain"-download in de rail. Nieuwe module `brain_transfer.py` + 8 tests. Brain 171, console 56 groen.

- [x] **U105 — bronnen automatisch minen + provenance in de graph** · `pending`
  (1) Auto-ingest bij toevoegen: een fetchbare source (blog/website/github) wordt direct na "Add source" gelezen — het ingest-endpoint accepteert nu `{"kind","value"}` om één bron te lezen. (2) Periodieke refresh: `refresh_loop` in de brain herleest wekelijks alle bronnen (SOURCE_REFRESH_ENABLED + SOURCE_REFRESH_HOURS=168, 0=uit; live aangezet in infra/dev/.env); per persoon uit te schakelen met de "auto-refresh"-checkbox (laatste `source-refresh`-fact wint, geen step-up nodig); `POST /knowledge/refresh-sources` doet hetzelfde on-demand. (3) Provenance: elke gemineerde fact eindigt op `— via [[host]]` (of `[[chatgpt]]`/`[[claude]]` bij chat-imports). (4) Graph: `[[topics]]` in fact-values worden nu GEDEELDE topic-nodes (paars) — persoon → fact → topic/bron bouwt zichtbaar op; matcht een topic een bestaande persoon/skill dan linkt hij daarnaartoe. Brain 173, console 56 groen.

- [x] **U106 — graph: pan & zoom** · `pending`
  De brain graph is nu navigeerbaar: slepen op de achtergrond pant, scrollen zoomt in/uit rond de cursor (0.2×–4×), en er zijn +/−/reset-knoppen rechtsboven. Eén viewport-transform (`scale`,`ox`,`oy`) wordt in `draw()` toegepast; hit-testing rekent scherm→wereld terug zodat klikken/hover de zoom volgen. Een druk-zonder-bewegen telt nog steeds als klik (opent de node), slepen niet. Cursor: grab/grabbing/pointer. Console 56 groen.

- [x] **U107 — self-optimizing skills (agentic learning loop)** · `pending`
  Skills verzamelen nu gebruiks-evidence en herschrijven zichzelf voor optimale uitvoering — met approval. (1) `SkillStore` logt per skill een observatie bij elke injectie (request/persona/person) in `.metrics/<name>.jsonl` (cap 200) + `metrics()` (uses, new_since_optimized). (2) Nieuwe `skill_optimizer.propose_optimization()`: voedt huidige body + evidence-digest aan het agent-model en krijgt een JSON-voorstel {changed, rationale, body} terug — schrijft NOOIT zelf. (3) Brain: `GET /skills/{name}/metrics`, `POST /skills/{name}/optimize` (voorstel), en `mark_optimized` bij save met `mark_optimized:true`. (4) Console (Settings → Skills): "×used +N"-badge, "Optimize"-knop → before/after-diff + rationale, "Apply rewrite" slaat op en reset de teller. Owner-in-the-loop: geen onbewaakte zelf-wijziging. Orchestrator +12 tests, brain +1, console 56 groen.

- [x] **U108 — auto-optimize skills: proactieve optimalisatie-suggesties** · `pending`
  Sluit de learning loop (U107): `GET /skills/suggestions` geeft de skills terug met genoeg nieuwe gebruikssignalen (new_since_optimized ≥ SKILL_OPTIMIZE_THRESHOLD, default 8). Console (Settings → Skills): een proactieve banner bovenaan ("N skills ready to optimize") met per-skill chips ("naam +N") die direct de bestaande Optimize-flow (diff + approval) starten — je hoeft niet meer te onthouden om te klikken. Applying reset de teller → banner verdwijnt. Route vóór /{name} zodat "suggestions" geen skillnaam wordt. Brain +1 test, console 56 groen.

- [x] **U109 — langetermijngeheugen per persoon** · `pending`
  Gesprekken zijn vluchtig (U42 = alleen sessie-historie); nu distilleert AURA over sessies heen een blijvend MEMORY per herkende persoon. `person_memory.py` (PersonMemory): buffert per persoon de (user, reply)-uitwisselingen; elke PERSON_MEMORY_EVERY (default 4) vouwt het chat-model ze in het bestaande geheugen — behoudt projecten/beloftes/voorkeuren/terugkerende thema's, dropt small talk — en vervangt het `memory`-fact (encrypted at rest, gecapt op 1400 tekens). Pipeline: `set_memory_hook` in `orchestrate()` voedt elke beurt met een herkende persoon in (best-effort, breekt nooit een beurt). Judgment: het `memory`-fact wordt apart gelabeld ("Memory from past conversations:") en vooraan geïnjecteerd. Console (Brain → persoon): "Memory"-sectie, auto-gegroeid en vrij bewerkbaar. `POST /knowledge/people/{id}/memory/flush` distilleert on-demand. Gated via PERSON_MEMORY_ENABLED. Brain 180 (+5), schemas 13 (+1), orchestrator 197, console 56 groen.

- [x] **U110 — proactieve Richie: reminders uitspreken + dagelijkse briefing** · `pending`
  Tot nu sprak Richie alleen na een wake-word; reminders vuurden wel op de bus (ReminderTriggered) maar niemand sprak ze uit. `proactive.py` (ProactiveEngine): spreekt op eigen initiatief door een `ResponseDrafted` te publiceren → hergebruikt de hele embodiment/TTS-pipeline (respecteert sleep-mode al). (1) Fired reminders → hardop ("Even een herinnering: …"). (2) Dagelijkse briefing op PROACTIVE_BRIEFING_TIME (HH:MM, leeg=uit): een korte gesproken samenvatting van openstaande reminders, één keer per dag. Gating: PROACTIVE_ENABLED (live), nooit tijdens slaap, stille uren PROACTIVE_QUIET_START/END (wrap over middernacht). `GET/POST /robot/proactive` + toggle & briefing-tijd-veld in Robot State. Bijkomend: ReminderScheduler-bug gefixt (publiceerde `text=`/str-id i.p.v. `message=`/UUID zoals het schema vereist — reminders zouden anders bij publish crashen). Brain 189 (+11), memory-service 17, console 56 groen.

- [x] **U111 — emotie & mimiek: stemming via kop/antennes** · `pending`
  Richie drukt de toon van zijn antwoord uit met kop en antennes terwijl hij praat. `mood.py` (`detect_mood`): goedkope keyword/interpunctie-heuristiek (NL+EN, geen extra LLM-call → geen spraaklatentie) → één van excited/happy/apologetic/curious/attentive/neutral (apologetic wint altijd; `!!` = excited). `_embody_reply`: een gedetecteerde mood VERVANGT het generieke reply-gebaar (anders vechten ze om de kop); uit via EMOTION_ENABLED=false of een "still"-karakter. Robot-adapter: vijf `mood_*`-poses (kin omhoog + antennes perky bij happy, wiebel bij excited, gebogen + antennes droop bij apologetic, tilt + asymmetrische antennes bij curious, subtiele lean-in bij attentive) — allemaal zacht en terug naar neutraal, instelbaar via MOOD_*-envs; onbekende id's degraderen sowieso naar een nod. Live op de Pi geverifieerd (5 poses 200, geen fallback-warning). Brain 195 (+6), robot 55 (+1) groen. Gedeployed + herstart.

- [x] **U112–U115 — design-pass over alle panelen (plan A→C→B→D, goedgekeurd)** · `pending`
  **A (U112) Brain-tabs**: het persoonsscherm is geen lange scroll meer maar tabs Profile (About+Facts) / Memory / Sources / Skills; sources als icoon-chips met korte host (volle URL in tooltip, 🔒 bij login-bronnen); zeldzame acties (Import chat export, Export brain, Forget person) achter een ⋯-menu in de hero; "Add person" in de rail klapt pas uit na een +-klik. **C (U113) Event Log**: bottom-dock standaard dicht (debug-oppervlak, één klik weg via de PanelBottom-toggle); layout-key v1→v2-migratie behoudt breedtes maar dropt de oude open-stand. **B (U114) Robot State compact**: Mode/Behavior/Speaking-rijen → één status-strip (dot + gedrag + speak-icoon + herkende persoon; "UNKNOWN" schreeuwt niet meer); de vier aan/uit-schakelaars (sleep/mic/follow/proactive) → één icon-toggle-rij; alle 12 actieknoppen in één inklapbare "Actions"-sectie en de motion log ingeklapt met teller — de camera staat nu boven de vouw. **D (U115)**: lange uitlegparagrafen → één zin + tooltip. Live geverifieerd in de draaiende app (HMR + tijdelijke brain): tabs, bronnen-chips, ⋯-menu, strip en toggles renderen correct. Console 56 groen, build clean.

- [x] **U116 — follow-me stopte "zomaar": wake herstelt tracking + mood-gebaren pauzeren niet meer** · `pending`
  Twee echte oorzaken. (1) `sleep` (U102) stopt head-tracking + body-yaw hard, maar het `wake_up`-MOTION (de quick action) zette ze nooit terug aan — alleen de sleep/wake-toggle deed dat via het aparte endpoint. Eén keer Sleep→Wake up via quick actions = follow-me permanent dood. Fix: wake_up herstart `start_head_tracking` (+ body-yaw als die aan stond) en zet `_tracking_on=True`. (2) De U111 mood-poses stonden niet in `_FOLLOW_GESTURES`, dus élk emotioneel antwoord pauzeerde tracking en herstartte hem; een stil ingeslikte resume-fout doodde follow-me "willekeurig". Fix: mood_* zijn nu follow-gestures (ogen blijven op jou tijdens het uiten) en een resume-fout logt een warning i.p.v. te verdwijnen. Robot 57 (+2) groen; live geverifieerd (tracking→sleep→wake→mood alle 200, geen warnings). Gedeployed + herstart. NB: in de app stond ook de Asleep-toggle aan — dan volgt hij per definitie niet.

- [x] **U117 — brein-review 2: schaalbare facts, skills-beheer in het brein, logs bij de robot, Settings ontvet** · `pending`
  (1) **Facts schalen**: gegroepeerd per categorie ("PROJECT ×34"), grootste groep eerst, max 5 chips per groep met "+N more"-expander, filterveld vanaf 8 facts — 95 facts zijn nu overzichtelijk i.p.v. één eindeloze chip-muur (live geverifieerd met Jans echte data). (2) **Skills-beheer woont in het brein-paneel**: inline editor (naam/beschrijving/triggers/persoon/procedure + enabled/delete), Optimize-knop per kaart (✨) mét before/after-diff en Apply, gebruiks-badge en de U108-suggestie-banner — allemaal verhuisd uit Settings; [[skill]]-links en de graph openen nu de editor hier (navStore→brain-dock). (3) **App logs** verhuisd naar Robot State als derde inklapbare sectie (level-filter + refresh, nieuwste eerst). (4) **Settings ontvet**: tabs Skills, Logs én Robot verwijderd (robot-adres blijft via de setup-wizard); alleen LLM / Connections / Appearance over. Console 56 groen, build clean; live geverifieerd in de draaiende app.

- [x] **U118 — skills starten optimaal: polish bij aanmaken** · `pending`
  Antwoord op "idealiter gebeurt optimize al bij aanmaken": nieuwe `skill_optimizer.polish_draft()` herschrijft een net getypte procedure naar strakke, uitvoerbare genummerde stappen (intentie + concrete details behouden, [[links]] intact, zelfde taal) — puur schrijfkwaliteit, nog zonder usage-evidence. Brain: `POST /skills/polish` (advisory, slaat zelf niets op). Console: de skill-editor heeft een "✨ polish on save"-checkbox (default aan) die de draft vóór het opslaan door de optimizer haalt en meldt wat er verbeterd is; de quick-add in het persoonsprofiel polijst stil mee (best-effort — offline/geen key → ruwe draft wordt gewoon opgeslagen). Orchestrator 9 optimizer-tests (+2), brain 5 (+1), console 56 groen. NB: de eerdere feedback-screenshots toonden de oude UI — U117 stond al klaar op de dev-server (geverifieerd: 3 Settings-tabs, ✨ per kaart, App logs); één Ctrl+R laadt hem, en één brain-herstart activeert /skills/polish.

- [x] **U119 — brein-rail: geen dubbele scrollbar meer + Add person zichtbaar in elk thema** · `pending`
  (1) De rail had `overflow-y:auto` op het geheel → een scrollbar zodra de inhoud ook maar 1px oversteeg (naast de content-scrollbar = dubbel). Nu: header (Skills/Graph/People) en footer (Add person/unlock) staan vast, en alléén de mensenlijst (`.rail-people`, flex:1) scrollt, en enkel bij écht overlopen. Live geverifieerd: bij 2 personen 0px scrollbar op rail én lijst. (2) "+ Add person" erfde `color: var(--accent-contrast)` (= wit) van `.rail-btn` → onzichtbaar op een licht thema. De ghost-variant krijgt nu leesbare accent-tekst + zichtbare dashed rand; geverifieerd zichtbaar in licht (blauw op rgb(248,250,252)) én donker. Console 56 groen, build clean.

- [x] **U120 — horizontale scrollbar weg: docks clampen + skill-grid + graph-labels** · `pending`
  De scrollbar bleek HORIZONTAAL (onderaan het venster): het brede rechterpaneel (voor de graph gesleept) + links + midden was samen breder dan het venster, en de skill-cards forceerden extra breedte. Drie fixes: (1) de splitters clampen nu tegen de live vensterbreedte (`maxSideWidth` laat altijd ruimte voor het andere dock + een centrum-minimum), plus een clamp bij `onMounted`/`resize` zodat een op een groot scherm breed gesleept dock nooit een kleiner venster laat overlopen; `.workspace` kreeg `overflow:hidden` als vangnet. Live: persistente rightWidth=900 → geclampt naar 680, geen window-scroll. (2) Skill-grid: `minmax(min(15rem,100%),1fr)` + `min-width:0`/`overflow-wrap:anywhere` op kaart en naam → cards krimpen en wrappen naar één kolom in een smal dock i.p.v. horizontaal over te lopen; `.brain-content` kreeg `overflow-x:hidden`. (3) Graph-labels lijnen nu uit op nodepositie (rechts uitgelijnd bij de rechterrand, links bij de linkerrand) → tekst valt niet meer buiten het canvas. Console 56 groen; geverifieerd in skills- én graph-weergave (0px window-scroll, canvas past in container).

- [x] **U121 — security-audit: path traversal, SSRF & CORS gedicht** · `pending`
  Audit over brain-API, orchestrator-tools, robot-runtime, Electron en console. Drie echte bevindingen gefixt: (1) **Path traversal (HIGH)** — de `/skills/{name}`-, `.../metrics`- en `.../optimize`-routes gaven de naam ongevalideerd door aan store-methoden die er filesystempaden mee bouwden (`{name}.md`, `.metrics/{name}.jsonl`), dus `..%2f..%2fsecret` kon een willekeurig `.md` verwijderen of metrics-paden benaderen. `delete`, `_obs_path`, `_opt_path`, `record_observation`, `observations`, `mark_optimized` en `metrics` weigeren nu elke naam die niet aan `_NAME_RE` (kebab-case) voldoet → 404, geen disk-toegang. (2) **SSRF (MEDIUM)** — `source_ingest._fetch_page` haalde elke owner-URL server-side op en volgde redirects; nu alleen publieke http(s)-hosts (`_is_public_http_url`: schema-check + DNS-resolutie, weigert loopback/privé/link-local/reserved/metadata `169.254.169.254`), plus her-validatie van de uiteindelijke redirect-URL en `max_redirects=5`. (3) **CORS (LOW)** — `allow_origins=['*']` mét `allow_credentials=True` is de klassieke onveilige combinatie; credentials worden nu automatisch uitgezet (met warning) bij een wildcard-origin. Bevestigd veilig gebleven: `laptop_tools` (pad-begrensd via resolve+is_relative_to, geen shell=True), Electron (contextIsolation:true/nodeIntegration:false), destructieve knowledge-ops (step-up-gate), geen `v-html`. +8 tests (orchestrator 201, brain 201 groen).

- [x] **U122 — chat-actieknoppen altijd zichtbaar + "New skill" losgemaakt** · `pending`
  (1) De chat-inputrij is een flex waarin het tekstveld `flex:1` had zonder `min-width:0` → het veld weigerde te krimpen en duwde de mic/robot-mic/teach/Send-knoppen buiten beeld zodra de conversatiekolom smal werd. Nu: veld `flex:1 1 0; min-width:0` (krimpt), knoppen `flex-shrink:0` (blijven). Live geverifieerd: bij een 281px-brede rij zitten alle 4 de knoppen volledig binnen de rij. (2) De "+ New skill"-knop plakte visueel tegen de laatste skill-kaart (leek erbij te horen); nu in een eigen `.new-skill-bar` met scheidingslijn + marge boven de grid, als losstaande ghost-actie. Console 56 groen, build clean.

- [x] **U123 — chat: knoppen boven vol-breedte input bij smalle kolom + Anthropic-log stiller** · `pending`
  (1) Bij een smalle conversatiekolom staan de actieknoppen (mic/robot-mic/teach/Send) nu op één rij BOVEN het invoerveld, dat de volle breedte krijgt zodat je ziet wat je typt. Geïmplementeerd met een container-query: de form is gewikkeld in een `.input-area` (query-container — een element kan z'n eigen grootte niet queryen), en onder 340px klapt de rij naar `column-reverse` met de knoppen in een `.input-actions`-groep bovenaan (Send vult de restbreedte). Boven 340px blijft het de gewone één-regel-layout (U122). Live geverifieerd: bij 281px staat de rij in column-reverse, knoppen boven, input volle 281px. (2) De log-noise "Anthropic computer-use unavailable (No module named 'anthropic')" was misleidend als WARNING: het `anthropic`-pakket is een OPTIONELE dependency en de OpenAI-agent (gpt-5.1, U74/U90) is het bedoelde pad. Een `ModuleNotFoundError` logt nu als rustige INFO ("using the OpenAI computer-use agent"); alleen een échte fout blijft een warning. Console 56 + computer-use 13 groen.

- [x] **U124 — chat: knoppen gelijke hoogte + auto-groeiend multiline invoerveld** · `pending`
  (1) De actieknoppen (mic/robot-mic/teach/Send) staan nu allemaal op dezelfde hoogte via een gedeelde `--ctrl-h: 36px` (mic-knoppen stretchen, Send vast 36px) — live geverifieerd 36/36/36/36. (2) Het `<input>` is een auto-groeiend `<textarea>` geworden, à la Claude Code: `autoGrow()` reset naar `auto` en zet de hoogte gelijk aan `scrollHeight` (cap 160px, daarna scrollt het), Enter verstuurt en Shift+Enter voegt een nieuwe regel toe (respecteert IME-compositie); na versturen klapt het terug naar één regel. De rij lijnt onderaan uit zodat de knoppen op de baseline blijven terwijl de tekst omhoog groeit. In de smalle column-reverse-modus (U123) krijgt de textarea `flex:0 0 auto` zodat de flex-berekening z'n gegroeide hoogte niet overschrijft. Live: 1 regel = 36px → 5 regels = 108px. Console 56 groen.

- [x] **U125 — Robot State herontwerp: gelabelde toggles, eigen briefing-regel, geen afkapping** · `pending`
  De vier power-toggles waren icon-only met de briefing-tijd ertussen geperst, en volume-%/persona werden afgekapt bij een smalle kolom. Nu: (1) een 4-koloms grid van **gelabelde tegels** (Awake/Asleep · Mic · Follow · Notify) met icoon + tekst, gelijke hoogte, groen bij actief. (2) De **daily-briefing-tijd** kreeg een eigen gelabelde regel ("Daily briefing at [time]") onder de toggles i.p.v. de rij te overladen. (3) **Volume**: slider `flex:1 1 0; min-width:0`, "%" `flex-shrink:0` → nooit meer afgekapt. (4) **Persona**: label op een eigen regel, dropdown volle breedte (`min-width:0`) met de edit-knop ernaast die niet meer wegvalt. Live geverifieerd bij 240px kolombreedte: tegels 4× gelijke hoogte, "80%" en de edit-knop volledig binnen het paneel. Console 56 groen.

- [x] **U126 — follow-me betrouwbaarder: tracking-watchdog + zichtbare status** · `pending`
  Diagnose van "volgt soms niet / stopt abrupt": head-tracking is daemon-side en kan stil sneuvelen (een niet-follow-gebaar pauzeert het en de resume faalt, de daemon verliest het gezicht, …) en komt daarna nooit meer terug tot een handmatige toggle of reconnect. Fix: een **watchdog** her-asserteert `start_head_tracking()` (+ body-yaw) elke TRACKING_WATCHDOG_S (default 5s) wanneer follow-me AAN hoort te staan en er geen motion loopt (motion_lock vrij) — zo herstelt het binnen enkele seconden. `tracking` staat nu ook in `/robot/status` (RobotState-veld) zodat je ziet of follow-me echt actief is. Robot 59 (+2) groen; gedeployed + herstart op de Pi. Bouwt voort op U116 (wake herstelt tracking, mood-gebaren pauzeren niet).
- [x] **U127 — herkenningsbeelden per persoon in Richies brein** · `pending`
  Antwoord op "wat gebeurt er met de beelden?": herkende personen werden NIET bewaard (alleen onbekende passanten, U36f). Nu een `RecognitionGallery`: bij elke herkenning van een BEKEND persoon wordt een kleine thumbnail bewaard, per persoon, **in-memory only** (weg bij herstart), throttled (1×/20s per persoon) en gecapt (6 per persoon). `GET /knowledge/people/{id}/snapshots` (gated tot de SENSITIVE-tier — het zijn gezichtsbeelden), en person-forget wist ze mee. Console: een snapshot-strip bovenaan de Profile-tab in het brein per persoon (met tijd + confidence in de tooltip) plus de nuance "kept in memory only, wiped on restart". Nieuwe module + 9 tests (gallery + perception + endpoint). Brain groen, console 56 groen. Privacy by design (ADR-008): niks op schijf, niks verlaat de machine.

- [x] **U128 — lokaal wake-word (fundament + kostenrem voor Realtime)** · `pending`
  Eerste stap van het spraak-plan (richting F Realtime, wake-gated). Diagnose: nu wordt ELK niet-stil venster over het netwerk getranscribeerd puur om "Richie" te horen — traag én Whisper laat de naam vaak vallen. Nieuw `wakeword.py`: `build_detector()` (WAKE_ENGINE=openwakeword + WAKE_MODEL) draait openWakeWord lokaal op de audio (WAV→mono 16k int16 decode, 80ms-frames, threshold); default `stt` → None → de bestaande transcribe-then-fuzzy blijft (graceful fallback, geen nieuwe dependency verplicht). Voice-loop: buiten een follow-up-venster wordt nu eerst lokaal gedetecteerd — geen wake → STT volledig overgeslagen (latency + kosten weg); wel wake → transcript geldt als commando-dragend ook als STT de naam liet vallen. Dit is ook de kostenrem voor U129: de dure Realtime-sessie opent pas ná de lokale wake. +8 tests (decode/factory-fallback/gate). Brain groen. Enable-instructies in infra/dev/.env.

- [x] **U129 — wake-gated OpenAI Realtime spraakbeurt + kostenteller + fallback** · `pending`
  Fase F van het spraakplan: menselijke, lage-latency conversatie via de Realtime API (audio→audio, meertalig, server-side VAD), maar ALLEEN geopend ná de lokale wake (U128) zodat er nooit 24/7 audio wordt gestreamd — een beurt betaalt enkel de gesproken seconden. Nieuw `realtime_voice.py`: `run_realtime_turn(pcm)` (injecteerbare connection-factory → volledig testbaar zonder netwerk), `wav_to_pcm24k` (16k→24k resample), en een `CostMeter` (audio/tekst-tokens × env-instelbare tarieven → live spend-schatting). Voice-loop: bij VOICE_ENGINE=realtime gaat de audio vóór transcriptie rechtstreeks naar de sessie; ELKE fout (geen key/quota/offline/sessiefout) → `False` → val terug op de bestaande STT→LLM→TTS-pijplijn (default blijft `pipeline`, niets verandert tenzij expliciet aangezet). `GET /voice/realtime-cost` + een live "🎙️ Realtime ~$X (N turns)"-regel in Robot State (alleen bij realtime). +6 brain-tests. Brain 219, console 56 groen. NB: de live audio-plumbing (24k in/uit, continue capture) vergt verificatie op de Pi; default staat uit tot dan.

- [x] **U130 — meertalige STT (NL/EN/FR/DE) + code-switching** · `pending`
  De STT forceerde één taal alleen voor en/nl/fr — dat brak NL+EN door elkaar en Duits ontbrak. Nu: `language` wordt alleen gepind als de eigenaar expliciet ÉÉN taal koos (en/nl/fr/de/es/it); anders auto-detect (leeg/"auto") zodat code-switching werkt. Antwoord-taal spiegelt de invoer (identity-prompt), met Duits/Spaans/Italiaans toegevoegd aan `_LANGUAGE_NAMES`. Console: Deutsch in de taalkeuze; brain-prefs-validatie staat 'de' toe. Realtime (U129) is sowieso meertalig out-of-the-box.
- [x] **U131 — terloopse spraak: weer + nieuwsgierige toon, niet meer repetitief** · `pending`
  Nieuw `ambient.py`: `current_weather()` (Open-Meteo, geen key; WEATHER_LAT/LON, default Brussel, 15min-cache, best-effort), `time_of_day()`, en een ring van recente spontane regels. De greet-on-recognition-prompt krijgt nu een ambient-note (tijdstip + actueel weer + "herhaal deze recente regels NIET") en de instructie "één korte, warme, écht NIEUWSGIERIGE zin — klink geïnteresseerd, niet gescript"; de gesproken begroeting wordt onthouden zodat de volgende anders is. Zo verwijst Richie naar het weer en herhaalt hij zich niet meer. +5 tests. Brain groen.

- [x] **U132 — conversation-engine-schakelaar in Settings + kostenteller-vindbaarheid** · `pending`
  `VOICE_ENGINE` zat alleen in de .env. Nu een dropdown **Settings → Appearance → "Conversation engine"** (Pipeline ⇄ Realtime) via de prefs-API (`voice_engine`, gevalideerd pipeline|realtime, live in os.environ + persistent) — geen .env-editen of herstart meer nodig. De hint legt uit wat elk doet en verwijst naar de kostenteller. Die teller staat in het **Robot State**-paneel als "🎙️ Realtime ~$X (N turns)" en verschijnt zodra de engine op realtime staat (poll elke 10s via `GET /voice/realtime-cost`). Live geverifieerd: control + opties aanwezig, Deutsch in de taalkeuze. +1 test. Brain + console groen.

- [x] **U133 — "Richie spreekt niet terug": Realtime-hang → timeout + circuit-breaker → pijplijn-fallback** · `pending`
  Diagnose via de draaiende brain: `VOICE_ENGINE=realtime` én `turns:0` — de Realtime-tak werd genomen maar voltooide geen enkele beurt. Oorzaak: de Realtime-verbinding kon HANGEN (verkeerd audioformaat / geen realtime-entitlement / nooit een `response.done`); zonder timeout bevroor dat de spraaklus zónder terug te vallen. Fix: (1) `run_realtime_turn` staat nu onder `asyncio.wait_for` (REALTIME_TURN_TIMEOUT_S=15) → een hang gooit RuntimeError i.p.v. vast te lopen. (2) Circuit-breaker in de voice-loop: na 2 mislukte Realtime-beurten wordt Realtime voor de sessie uitgezet (`_realtime_broken`) met een duidelijke logregel — de pijplijn neemt de hele sessie over, geen 15s-hang meer per beurt. Zo praat Richie altijd terug, ook als Realtime (nog) niet werkt. Tests groen. NB: de live Realtime-audio blijft ongeverifieerd op de Pi; zet de engine terug op Pipeline in Settings tot we 'm samen live testen.

- [x] **U134 — Realtime werd nooit getriggerd (gating-bug) → altijd een antwoord** · `pending`
  Vervolg op "Richie spreekt niet terug na restart". Live bevestigd op de brain: `voice_engine=realtime` maar `turns:0` — de Realtime-tak stond op `(wake_confirmed or in_followup)`, en zonder lokaal wake-word (openWakeWord uit) is `wake_confirmed` altijd False; op de eerste "Richie, …"-beurt is `in_followup` ook False → Realtime werd NOOIT aangeroepen, de engine-keuze deed niks. Fix: de Realtime-beurt draait nu op ELKE bevestigde beurt (vlak vóór `_handle`): `if not await self._realtime_turn(wav): await self._handle(command)` — Realtime eerst, anders de klassieke pijplijn. Samen met U133 (timeout + circuit-breaker) betekent dit: Realtime wordt echt geprobeerd én kan de lus niet bevriezen → Richie antwoordt altijd, via Realtime of via de pijplijn-fallback. 32 voice-tests groen.

- [x] **U135 — hallucinaties in vreemde talen: taal-allowlist + no-speech-gate op STT** · `pending`
  Regressie van U130: door de taal-pin weg te halen (voor NL/EN-code-switching) mocht Whisper ELKE taal gokken, en op kamerruis/stilte verzon hij hele zinnen in Portugees ("Não me inscreva que"), Turks ("İyi günler") en gebrabbel ("Koffoló bícs") — waar Richie braaf op antwoordde, óók in die taal. De bestaande filter keek alleen naar niet-Latijns schrift, dus PT/TR glipten erdoor. Fix: op het auto-detect-pad vraagt STT nu `verbose_json` (whisper-1, `STT_AUTO_MODEL`) zodat we Whispers eigen signalen krijgen, en `_reject_reason()` gooit weg wat (a) een gedetecteerde taal buiten de huishoudtalen heeft (`VOICE_LANGUAGES`, default nl,en,fr,de — namen én ISO-codes herkend), (b) een gemiddelde `no_speech_prob` > 0.6 heeft (Whisper "hoort" spraak in stilte) of (c) een `avg_logprob` < -1.0 (gebrabbel). Alles instelbaar via env. Een pinned taal houdt het snellere model (daar is de gok al beperkt). +3 tests met exact de live-hallucinaties; 41 voice-tests groen.

- [x] **U136 — foute herkenning corrigeren: ✕ op een sighting → terug naar onbekende bezoekers** · `pending`
  Op verzoek ("let me indicate when incorrect"): elke foto in "Recent sightings" krijgt een ✕-badge (zichtbaar bij hover, met tooltip "Not <naam>?"). Klikken doet meer dan verwijderen — de correctie voedt de herkenning: de gallery bewaart nu ook de face-embedding + frame bij elke snapshot (U127 bewaarde enkel een thumbnail), `mark_wrong()` haalt hem weg en geeft hem terug, en `POST /knowledge/people/{id}/snapshots/{snapshot_id}/wrong` her-archiveert hem in het onbekende-bezoekers-log (U36f) zodat je hem aan de JUISTE persoon kunt taggen — wat die persoon opnieuw inschrijft en de herkenning verbetert. De cooldown reset zodat een gecorrigeerd gezicht meteen opnieuw vastgelegd kan worden. Console meldt eerlijk wat er gebeurde ("moved to unknown visitors so you can tag the right person" vs "could not be re-filed"). Gated tot de SENSITIVE-tier. +2 tests (gallery + endpoint incl. re-filing); brain 24 in die suites, console 56 groen.

- [x] **U137 — quick actions weer zichtbaar (tracking-conflict) + dansmoves** · `pending`
  (1) "Niet alle acties werken": live getest — ALLE acties gaven 200 zonder fouten, dus geen API-probleem. Echte oorzaak: head-tracking vocht met de beweging. `nod/tilt/shake/gesture/wave` staan in `_FOLLOW_GESTURES` (U81, oogcontact tijdens praten) dus tracking bleef áán, en sinds de U126-watchdog die elke 5s heraanzet trok de daemon de kop midden in de beweging terug — visueel "doet niks". Fix: `MotionCommand.manual` (nieuw veld); een handmatige quick action uit het paneel pauzeert follow-me altijd (ook voor look_around/point), reply-gebaren tijdens een gesprek houden oogcontact zoals bedoeld. Console stuurt `manual: true` mee. (2) **Dansmoves**: `dance` (bop+sway+twirl-routine), `bop` (kop knikt op de beat, antennes mee), `sway` (traag heen-en-weer met tegengestelde antennes) en `spin` (echte body-yaw-twirl, met sway-fallback als body-yaw ontbreekt) + een Dance-sectie in Robot State. Live op de Pi geverifieerd (nod/dance/bop/sway/spin alle 200, geen fouten). Robot 62 (+4), schemas 124, console 56 groen. Gedeployed + herstart.

- [x] **U138 — dansmuziek: de robot synthetiseert zijn eigen groove** · `pending`
  De dansmoves hebben nu geluid. `_synth_groove()` bouwt met numpy een kort deuntje: kick (55 Hz sine met snelle decay) op de tellen, hi-hat (gefilterde ruis) op de tussenslagen en een baslijn die per tel een noot uit de **A-mineur-pentatoniek** kiest — die toonladder klinkt altijd muzikaal, hoe je ook gokt. `_play_groove()` schrijft de WAV naar /dev/shm en start `media.play_sound()` **niet-blokkerend** (in tegenstelling tot het spraakpad, dat bewust blokkeert) zodat muziek en beweging tegelijk lopen; oude WAV's worden opgeruimd (max 3). De moves zijn nu op de beat gezet: dance/bop 120 BPM, sway 84, spin 110 — bewegingslegs vallen op achtste noten. Uit te zetten met `DANCE_SOUND=false`; volume volgt de app-slider; zonder media-backend danst hij gewoon stil. +3 tests (hoorbaar & niet-clippend, elke move start een groove, uitschakelbaar). Robot 23 in die suite groen; live op de Pi geverifieerd (4 moves 200, WAV's van 107–231 KB geschreven en afgespeeld, geen fouten).

- [x] **U139 — dance: torso mee, alles in de schaal** · `pending`
  De `dance`-move is een volledige lichaamsroutine geworden: naast kop en antennes zwaait nu ook de **torso** mee via `set_target_body_yaw`. Omdat de daemon soepel naar elk yaw-doel toe beweegt, wordt het doel TUSSEN de kop-legs gezet — de romp zwaait dus dóór de bewegingen heen i.p.v. erna. Drie delen: (1) warming-up — bobben met de romp zachtjes heen en weer (halve twist), (2) grote uithalen — romp en kop leunen samen dezelfde kant op (volle twist), (3) finale — een volledige twirl, dan strak landen met een flourish. Automatic body-yaw wordt tijdens de routine uitgezet zodat follow-me niet tegenwerkt, en in een `finally` altijd op 0 gezet + body-follow hersteld als die aanstond — hij eindigt dus gegarandeerd recht vooruit. Groove verlengd naar 12 beats zodat de muziek de hele routine dekt. +2 tests (torso zwaait beide kanten op en centreert; body-follow wordt hersteld). Robot 25 groen; live geverifieerd (5,3s, 200, geen fouten, tracking daarna weer aan).

- [x] **U140 — voice-brief Phase 0: instrumenteer vóór je iets verandert** · `pending`
  Per de spraak-brief (§3): geen optimalisatie zonder metingen. `turn_trace.py` — een `TurnTrace` met monotone timestamps op elke pijplijn-fase (capture_start/end, endpoint_fired, stt_final, llm_request_sent/first_token/final, tts_request_sent/first_audio, playback_first_sample/complete) + een `TraceLog` (ring van 50 + één JSON-regel per beurt naar TURN_TRACE_PATH). Ingehaakt in de voice-loop (capture/stt/endpoint, trace pas geopend bij een ÉCHTE beurt zodat de vele continue-paden geen dangling traces geven), `_handle` (llm-marks), `_embody_reply` in main.py (tts + playback) en het realtime-pad. Mouth-to-ear = playback_first_sample − endpoint_fired. `GET /voice/turn-traces?n=20` geeft de laatste beurten (traagste eerst) met p50/p95. `docs/latency-baseline.md` legt de meetmethode vast + de eerlijke kanttekening dat vaste opnamevensters géén echte endpoint hebben (capture_end == endpoint_fired; het venster zelf is vlakke dead-time die Phase 2 wegwerkt) — baseline-tabel wacht op een live 30-beurten-run op de Pi. +5 tests. Brain 235 groen. VOLGENDE: eerst die 30 beurten meten, dan bevestigen dat 60–80% in endpoint-wait + time-to-first-audio zit, dán pas Phase 1 (streaming end-to-end).

- [x] **U141 — bevinding: Realtime levert geen audio op dit account → breaker trips meteen** · `pending`
  Uit de turn-traces (voice-brief §9 stack-bevinding, mét cijfers): elke Realtime-beurt = `engine:realtime`, `llm:~10.8s`, `reply_chars:0`, geen audio. De Realtime-API produceert op dit account/model niets — daarom sprak Richie niet terug (de pijplijn-fallback toonde wél de tekst in de console). Twee fixes: (1) lege audio uit de Realtime-turn telt nu als FOUT i.p.v. stille fall-through (`raise "no audio"`), en (2) een deterministische "no audio"-fout zet Realtime **meteen** uit voor de sessie (i.p.v. pas na 2× de timeout te verspillen) → de pijplijn neemt direct over. Advies aan de eigenaar staat in de logregel: zet Conversation engine terug op **Pipeline** in Settings. NB: de spooktranscripten in dezelfde batch ("kommen von Nordmeer über" (DE), "speel muziek af") zijn de self-hearing-loop (§6.1) — de robot hoort zijn eigen muziek/echo; volledige hardening daarvan is Phase 3b van de brief. 19 voice-tests groen.

- [x] **U142 — "moet ik iets doen voor Realtime?": zelf-check die de échte reden toont** · `pending`
  I.p.v. een stille "no audio" nu een diagnose. `realtime_voice.probe()` doet een kleine TEXT-only Realtime-round-trip en rapporteert precies wat er gebeurt: verbonden + antwoord, of een gerichte reden — "model X niet beschikbaar op deze key / account heeft geen Realtime-toegang", "key geweigerd", "rate-limited/quota", of "timed out — model waarschijnlijk niet toegankelijk". `POST /voice/realtime-check` + een **"Test Realtime access"-knop** in Settings → Appearance (naast de engine-dropdown, alleen bij Realtime) met een groen ✓/rood ✗ + de reden. Zo weet de eigenaar of het aan zijn kant ligt (toegang aanzetten / ander REALTIME_MODEL) of niet. Injecteerbare connectie → 3 tests zonder netwerk. Brain + console groen.

- [x] **U143 — Realtime-model verouderd: kandidaat-modellen + auto-detectie** · `pending`
  De screenshot bewees dat het account WEL Realtime-toegang heeft (Audio→Realtime-tab in de playground), dus geen activatie nodig — de oorzaak was mijn modelnaam. `gpt-4o-mini-realtime-preview` is vervangen door het GA-model `gpt-realtime`. Nu: `_MODEL_CANDIDATES` (gpt-realtime → gpt-4o-realtime-preview → gpt-4o-mini-realtime-preview), `_default_realtime_model()` (REALTIME_MODEL of de eerste kandidaat), en de default overal omgezet naar `gpt-realtime`. `probe()` (de "Test Realtime access"-knop) loopt nu de kandidaten af, retourneert de EERSTE die werkt mét de hint "Realtime works with 'X'. Set REALTIME_MODEL=X to pin it." — of stopt vroeg bij een key/quota-fout (die verandert niet per model). De UI toont die hint. +9 realtime-tests groen, console 56 groen.

- [x] **U144 — Realtime werkt: migratie naar de GA-API (beta-vorm uitgezet)** · `pending`
  De rauwe close-reden bewees het: `invalid_request_error.beta_api_shape_disabled` (close 4000) — geen key/model-probleem maar de SDK-vorm. De oude `client.beta.realtime.connect` is server-side uit; openai 2.33 vereist het GA-pad. Live ontdekt en gemigreerd: (1) `client.realtime.connect` i.p.v. `.beta`, (2) GA-sessie `{type:realtime, output_modalities, audio:{output:{format,voice}}}`, (3) GA-events `response.output_audio.delta` / `response.output_audio_transcript.delta` / `response.output_text.delta` (oude namen als fallback), (4) de audio als ÉÉN `conversation.item.create` met `input_audio`-content i.p.v. `input_audio_buffer.append+commit` — dat buffer-pad racet de async websocket-send en de server zag een 0 ms-buffer (`input_audio_buffer_commit_empty`); de item-vorm is atomisch. `probe()` idem naar de GA-vorm + rapporteert nu de RAUWE close-reden i.p.v. een gok. Live end-to-end geverifieerd tegen het echte account: `run_realtime_turn` → 49 tekens transcript + 312 KB audio + $0.0029. 9 realtime-tests groen. REALTIME_MODEL=gpt-realtime in .env.

- [x] **U145 — Richie hoort niks meer: mijn U135-hallucinatie-fix brak de STT (leeg transcript)** · `pending`
  Live-diagnose via `/setup/voice-check`: mic goed (raw_peak 0.1155, passed_gate) maar **transcript leeg** → geen commando → `turns:0` → geen antwoord (Realtime én pijplijn). Oorzaak: U135 zette de auto-taal-modus op `whisper-1` (voor de verbose_json no-speech/taal-signalen), maar whisper-1 is fors slechter dan `gpt-4o-mini-transcribe` en gaf op échte, ruizige robot-mic-audio een LEEG transcript (op een schone TTS-clip nog verhaspeld, op mic niks). Fix: de verbose_json-gate is nu OPT-IN (`STT_HALLUCINATION_GATE=true`); default blijft het goede model. Live geverifieerd: default → "Hey Richie, kan je mij om iets vertellen?" (schoon, wake word aanwezig). De primaire verdediging tegen de vreemde-taal-loop blijft het verplichte wake-word + de echo/muziek-guards (§6.1), niet een slechter STT-model. 17 voice-tests groen (de _reject_reason-tests blijven, functie bestaat nog voor de opt-in).

- [x] **U146 — Realtime: juist antwoord + juiste labels (mop i.p.v. begroeting; RICHIE i.p.v. YOU)** · `pending`
  Twee bugs uit de screenshot. (1) **Verkeerd gelabeld**: het Realtime-pad publiceerde het ANTWOORD als `TranscriptUpdated` → verscheen als JOUW bericht. Nu: de "YOU"-bubbel is jouw STT-`command`, en het antwoord gaat via `ResponseDrafted(already_voiced=True)` → toont als RICHIE, en `_embody_reply` slaat het over (geen dubbele spraak). (2) **Generieke begroeting i.p.v. mop**: de vaste-venster-audio (wake word + stilte) was te onduidelijk, dus het model begroette maar wat. Fix: `run_realtime_turn(text=command)` — we hebben jouw exacte woorden al uit de STT, dus die sturen we als tekst naar Realtime (audio-antwoord). Betrouwbaar én sneller (geen audio-upload/flush). Live geverifieerd: "vertel eens een korte mop" → "Waarom kon de fiets niet rechtop blijven staan? Hij was te moe!" + 300 KB audio. Fallback naar audio als er geen tekst is. Schemas 124, 24 voice/realtime-tests groen.

- [x] **U147 — aandachtig luisteren: denk/luister-houding tijdens de wachttijd** · `pending`
  Op verzoek ("terwijl ik babbel moet Richie simuleren dat hij aandachtig luistert"): twee nieuwe subtiele bewegingen. `listening` (kleine lean naar de spreker + antennes vooruit, kort) en `thinking` (trage kop-roll met antennes terwijl een antwoord wordt gegenereerd, zodat de delay als "overwogen" leest i.p.v. bevroren). Bewust klein gehouden — een grote beweging voegt motorruis toe aan de mic tijdens de opname (brief §5.3). Beide staan in `_FOLLOW_GESTURES` dus tracking blijft aan (ogen op jou). De voice-loop vuurt bij elke echte beurt een fire-and-forget `thinking`-cue (LISTENING_CUE=false om uit te zetten) die tijdens de reply-delay animeert zonder latency toe te voegen. Robot 26 (+1) groen; live op de Pi geverifieerd (listening/thinking 200). Gedeployed + herstart.

- [x] **U148 — vlotter + geen spookmop: VAD-endpointing (delay↓) + self-hearing-guard (§5.1/§6.1)** · `pending`
  Twee stukken uit de spraak-brief. (1) **Endpointing** (§5.1): `capture_audio` neemt niet langer altijd het volle venster op — het stopt ~ENDPOINT_SILENCE_S (default 0.6s) nadat je klaar bent met praten, met een goedkope frame-VAD (ENDPOINT_VAD_GATE) en een minimum-spraak-drempel zodat één kuchje niet eindigt. `duration_s` is nu de MAX. Een kort commando keert dus snel terug i.p.v. altijd 3–5s — dat is de grootste hap van de gevoelde delay. VOICE_ENDPOINTING=false herstelt het vaste venster. Live: stilte neemt terecht het volle venster (endpointing pas ná spraak); unit-test met gemockte media bevestigt dat spraak→stilte < 2s stopt i.p.v. 5s. (2) **Self-hearing-guard** (§6.1, tegen de spookmop): `_is_echo_of_last_reply` checkt nu een geschiedenis van de laatste 3 antwoorden (nagalm loopt turns achter), en een nieuwe cooldown (SELF_HEARING_COOLDOWN_S=1.2s) gooit alles weg dat vlak ná Richies spreken in een follow-up-venster binnenkomt — de klassieke self-hearing-phantom. Elke afwijzing logt de reden (§6.3). Robot 69, brain voice 28 groen; robot-deel gedeployed + herstart.

- [x] **U149 — endpointing kapte zinnen af ("fertelde") + phantom in Realtime → conservatiever + wake elke beurt** · `pending`
  Twee regressies uit de screenshots. (1) **Afgekapte spraak**: mijn U148-endpointing (hang 0.6s, min-speech 0.3s) stopte de opname bij een natuurlijke pauze na het eerste woord — "vertel eens een mop" werd "fertelde", te kort voor de STT → onzin → generiek antwoord. Fix: veel conservatiever — endpoint pas na een DUIDELIJKE, aanhoudende stilte (ENDPOINT_SILENCE_S 0.6→1.2s) ná echte spraak (ENDPOINT_MIN_SPEECH_S 0.3→0.6s). Trimt nog steeds de lange staart van een afgeronde zin, maar kapt geen inter-woord-pauzes meer af. (2) **Phantom in Realtime**: de tweede RICHIE-regel zonder gebruikersbeurt ("Waarover wil je meer horen?") kwam uit het follow-up-venster. In Realtime-modus wordt dat venster nu altijd uitgezet → wake-word elke beurt vereist; Realtime is conversationeel genoeg dat her-wekken prima is, en het doodt de phantom bij de bron. Robot 27, brain voice 10 groen; robot-deel gedeployed + herstart.

- [x] **U150 — endpointing standaard UIT: kapte tussen wake-word en commando af** · `pending`
  Live-diagnose (`voice-check`): transcript was alléén "Richie" — de energy-VAD-endpointing kapte de opname af in de natuurlijke pauze TUSSEN het wake-word en het commando ("hey Richie … vertel eens een mop"), dus alleen "Richie" bereikte de STT → bare wake → niks. Zonder interim-transcripts kan energy-VAD die pauze niet van het einde van de zin onderscheiden (§5.1: dat vergt transcript-bewuste endpointing, Phase 2). Eerlijke §9-beslissing: `VOICE_ENDPOINTING=false` als default → het betrouwbare vaste venster hersteld (waarmee de mop vóór U148 gewoon werd verteld). De endpointing-code + opt-in blijven voor Phase 2. Robot 27 groen. NB: bij het deployen viel de Pi van het netwerk (SSH-timeout) — de fix staat in git maar moet nog naar de Pi zodra die weer bereikbaar is; de robot-mic-onbereikbaarheid verklaart mogelijk mee waarom er niks gebeurde.

- [x] **U151 — verwarrende titelbalk-status ("Connected · offline") gelabeld** · `pending`
  Twee losse statussen stonden zonder onderwerp naast elkaar → las tegenstrijdig. Nu gelabeld: **"App: Connected"** (de console↔brain event-stream-WebSocket) en **"Robot: online/offline"** (de verbinding met de Pi), met een groen/rood CPU-icoon dat de robot-connectie kleurt. Tooltips verduidelijken elk ("Console ↔ brain event stream" / "Robot connection"). Console 56 groen. Bijkomend: na de netwerk-drop is de Pi weer online (status connected/tracking true) en de U150-endpointing-fix (vast venster) is alsnog gedeployed + herstart.

- [x] **U152 — "Robot: offline" terwijl camera live is: status uit /robot/status pollen** · `pending`
  De console zette `connected` ALLEEN via WS-events (RobotConnected). Miste die (robot verbond vóór de console, of tijdens de netwerk-drop), dan bleef de titelbalk "offline" terwijl de camera-stream (directe HTTP) prima werkte — verwarrend. Fix: `robotStore.syncFromStatus()` + een poll van `/robot/status` elke 8s in RobotPanel → de titelbalk volgt nu de echte robot-connectie (de brain rapporteerde al `connected:true, online`). Console 56 groen. NB: hiermee samen de latency-meting uit de traces vastgelegd voor de baseline: mouth-to-ear ~12,5s, opgesplitst als capture 3,9s / stt 1,5s / een verdachte queue 5,0s / realtime-generatie+buffer 6,0s — de grootste hap is dat Realtime de HELE audio buffert vóór afspelen; streaming daarvan is de volgende Phase-1-unit.

- [x] **U153 — streaming Realtime-audio: afspelen start op de eerste chunk (Phase 1, mouth-to-ear)** · `pending`
  Grootste hap in de ~12,5s mouth-to-ear was dat Realtime de HÉLE reply bufferde vóór afspelen (~6s dood). Nu streamt `run_realtime_turn` via een `on_segment`-callback per ~1,4s-segment (`REALTIME_SEGMENT_MS`); `voice_loop._realtime_turn` speelt die segmenten op volgorde af via een consumer-task + `RobotClient.speak_segment` → een nieuwe robot-route `POST /robot/speak/segment` die `play_audio(normalize=False, tail_margin=0.06)` direct aanroept (buiten de behaviour-engine, geen gesture-/event-spam per segment). `normalize=False` voorkomt volume-pompen tussen segmenten (Realtime-PCM is al full-scale); de kleine tail-margin voorkomt hoorbare gaten. `playback_first_sample` wordt nu gemarkt zodra het eerste segment speelt i.p.v. na de hele buffer. Terugval: `REALTIME_STREAMING=false` → oude hele-utterance-weg. **Instrumentatie**: de verdachte 5s-"llm_queue" bleek het TWEEDE luistervenster bij een kaal wake-word (`_capture_command`); nieuwe trace-stages `second_capture_start/end` maken dat venster nu een eigen `second_capture`-segment i.p.v. verstopt in `llm_queue`. Tests: realtime-voice + voice-loop streaming-paden (+3), robot-runtime speak/route groen; brain 243 groen. Bijkomend een pre-existing test-isolatielek gedicht: `test_prefs` deed `os.environ.update` (VOICE_ENGINE=realtime) zonder cleanup → snapshot/restore in de fixture, suite nu deterministisch. Robot-route live geverifieerd (HTTP 200 `{ok:true}`). Robot-runtime gedeployed + herstart.

- [x] **U154 — gespreksessie-modus: continue mic-stream + server-VAD (ChatGPT-voice-architectuur)** · `pending`
  Het afgekapte "vertel eens een..." was de architectuurgrens: vaste opnamevensters kunnen nooit vloeien. Nu werkt het zoals ChatGPT voice: wake word opent een SESSIE — één persistente Realtime-verbinding waarin de robotmicrofoon continu streamt (`GET /robot/audio/stream`, chunked HTTP, s16le 16 kHz; adapter `stream_audio()` met vloeiende adaptieve gain i.p.v. per-opname-normalisatie) en de server-side **semantic VAD** de beurtwisseling doet — géén vensters, géén lokale STT, géén tweede luistervenster. Reply-audio gaat via de U153-segmentweg (eerste woorden spelen terwijl het model nog genereert); input-transcriptie (`gpt-4o-mini-transcribe` server-side) voedt de YOU-bubbels. Eerste commando (uit het wake-venster) seedt de sessie als tekst → direct beantwoord. Sessie sluit op idle (`REALTIME_SESSION_IDLE_S`=60) of max (`REALTIME_SESSION_MAX_S`=600) → kosten begrensd; daarna gewoon opnieuw "Hey Richie". Zelf-horen (§6.1): half-duplex — tijdens playback (brain-side afspeelklok) worden mic-chunks GEDROPT, dus de server hoort Richie nooit zichzelf; eerlijke trade-off: geen barge-in midden in een zin in sessiemodus (echte barge-in vergt AEC op de robot). Uit te zetten met `REALTIME_SESSION=false` (→ U153 per-turn). **Live geverifieerd**: mic-stream op de Pi levert real-time (7,6s audio in 8s curl; eerdere 0,5×-meting bleek contentie met de draaiende voice-loop die `stop_recording` deed — in productie geen overlap: de loop wacht op de sessie); brain-side netwerkconsumptie + 16→24k-resample OK; en de exacte `session.update`-shape (semantic_vad + transcription) live geaccepteerd door de GA-API (`session.updated`, geen error). Tests: `test_realtime_session.py` (volledige flow, half-duplex-gate, idle-close, error-raise) + voice-loop-sessiepad (+2); brain 251 groen, robot-runtime 71 groen. Robot-runtime gedeployed + herstart.

- [x] **U155 — gapless afspelen via de SDK-appsrc-pijplijn (fix "hangen tijdens spreken")** · `pending`
  Het haperen kwam uit de segmentweg zelf: per segment een playbin-herstart (temp-WAV + pipeline-opstart ≈ 100-300ms gat) én brain-side fire-and-forget POSTs die out-of-order konden landen en bij lange replies de 10s-HTTP-timeout raakten (segment kwijt → hoorbare hang). Fix: (1) robot speelt segmenten nu via de push-pijplijn van de SDK (`start_playing`/`push_audio_sample` → audiomixer met live silence-branch) — naadloos achter elkaar, POST retourneert zodra gebufferd (live gemeten: 0,09s), utterance-herstamping via `_appsrc_until`-klok, `stop_audio` flusht ook deze weg via `clear_player` (instant afkappen); (2) brain-sessie speelt segmenten via een geordende consumer-queue. Terugval: `ROBOT_APPSRC_PLAYBACK=false` → oude playbin-weg. Robot 71 groen, brain 37 (voice) groen; live geverifieerd op de Pi.

- [x] **U156 — echo-cancellation onderzocht + AEC-groundwork (eerlijke uitkomst: geen betrouwbare full-duplex)** · `pending`
  Vraag was: hardware-issue of oplosbaar? Antwoord uit metingen (raw mic, AGC uit): (a) de `.asoundrc`-route van deze robot levert GÉÉN effectieve hardware-AEC — echo-residu rms ~1900 bij toon vs ~15 kamerruis en ~400 raw spraakpiek → echo ~9× luider dan spraak; (b) de SDK heeft webrtcdsp+webrtcechoprobe aan boord (gst-plugins-bad aanwezig op de Pi) maar alleen in de autoaudio-fallback-branch; geforceerd via `ROBOT_WEBRTC_AEC=true` (monkeypatch: asoundrc-check uit + `Gst.ElementFactory.make`-mapping autoaudio→alsa reachymini-devices, want autodetect koos pulse/openal → device-errors) mét `delay-agnostic`+`extended-filter`+`gain-control=false` (AGC pompte het residu terug naar spraakniveau) convergeert de AEC naar ~10-12 dB demping maar INSTABIEL (residu 1000→2900 rms, her-divergentie) — residu blijft op/boven spraakvolume, dus server-VAD zou nog steeds Richie's eigen stem horen. §9-conclusie: **software-AEC op deze speaker↔mic-koppeling is niet genoeg voor betrouwbare full-duplex barge-in**; de flag blijft beschikbaar voor experimenten maar staat default UIT. Wat WEL geland is: volledige barge-in-machinerie in de sessie (`REALTIME_BARGE_IN=true` → mic blijft streamen tijdens playback, `speech_started` mid-playback → `stop_audio` (clear_player) + `response.cancel`, getest met fakes) — klaar om aan te zetten zodra een betere AEC (bv. XMOS-processed capture-route of extern AEC-device) beschikbaar is. Onderweg ook: `?raw=1` op de mic-stream (diagnose zonder AGC — AGC maskeerde de echometing volledig). Half-duplex blijft de default: onderbreken kan zodra Richie's zin klaar is.

- [x] **U157 — babbel-lichaamstaal tijdens het spreken + idle follow-me herstel** · `pending`
  (1) **Aankijken + bewegen alsof hij babbelt**: de SDK blijkt hier een ingebouwde feature voor te hebben die we nooit aanriepen — `mini.enable_wobbling()` analyseert ALLE afgespeelde audio (incl. onze U155-segmenten) en zet die om in subtiele, PTS-synchrone hoofdbewegingen die de daemon BOVENOP face-tracking componeert → hij kijkt je aan én beweegt op zijn eigen spraakritme. Aangezet bij connect (`HEAD_WOBBLE=true` default). Daarbovenop antenne-accenten tijdens het praten (`_talk_gesture_loop`, `TALK_ANTENNAS=true`): willekeurige kleine antenne-zwaaien zolang de afspeelklok loopt — antennes raken de kop niet, dus tracking blijft intact. (2) **Idle follow-me**: oorzaak gevonden — de daemon-tracker laat het gezicht los na >2s uit beeld (`_tracking_lost_timeout`) en de kop blijft dan staan tot hij je toevallig weer ziet; met het smalle camerabeeld gebeurde dat niet ("follow me werkt niet meer buiten conversaties"). Fix: `_idle_scan_loop` — elke `IDLE_SCAN_S` (45s default, 0=uit) een langzame kopzwaai; de daemon weegt onze zwaai tegen het face-aim (gewicht), dus mét gezicht in beeld wint het aim (zwaai onzichtbaar), zonder gezicht zoekt hij de kamer af tot de tracker je hervindt. Skipt bij slapen (tracking_on=False), tijdens spraak en tijdens moties. (3) Bugfix onderweg: sessie-einde kapte de staart van het laatste antwoord af (mic-teardown → stop_recording → gedeelde pipeline NULL) → de sessie wacht nu tot de afspeelklok voorbij is (`REALTIME_TAIL_MAX_S`). Robot 71 groen, sessies 8 groen; gedeployed + live gecheckt (segment 200/appsrc, geen fouten in journal, tracking true).

- [x] **U158 — "kijkt naast me" + zwakke heracquisitie gefixt (sway-yaw, body_yaw-default, scan-holds)** · `pending`
  Drie oorzaken gevonden in de SDK-semantiek: (1) **de wobbler-sway heeft default 7,5° YAW-uitslag** op 0,6 Hz — tijdens het praten dwaalt zijn blik dus langzaam ±7,5° opzij ("hij lijkt naast me te kijken"); getemd naar 2° via module-patch vóór `enable_wobbling` (`WOBBLE_YAW_DEG`, pitch 4° blijft — knikken hoort bij babbelen, roll 2°). (2) **`goto_target` heeft `body_yaw=0.0` als DEFAULT** — elke antenne-wiggle, elke scan-stap én elk conversatiegebaar (de `go()`-helper) commandeerde de torso stilletjes terug naar het midden, van de persoon wég; overal `body_yaw=None` (huidige stand houden) — dansroutines onaangetast (die sturen expliciet via `set_target_body_yaw`). (3) **Heracquisitie**: de scan was een continue pan waar de face-detector niets mee kon — nu bredere sweep (±40°) mét 0,6s holds per richting (detector heeft stilstaande frames nodig), en interval 45s→25s. Teststub `goto_target` kende `body_yaw` nog niet → bijgewerkt; robot 71 groen. Gedeployed + herstart (tracking true).

- [x] **U159 — "1 skill ready to optimize" bleef eeuwig hangen (already-optimal doodlopend spoor)** · `pending`
  Reproduceerbaar op schijf: `music.jsonl` = 37 observaties, `music.optimized` = 23 → 37−23 = **precies de "+14"** uit de screenshot; de marker dateerde van 18/07 19:08, de jsonl van 19/07 11:08 — dus nooit bijgewerkt. Oorzaak: `mark_optimized()` werd ALLEEN aangeroepen vanuit `applySkillProposal` (de "Apply rewrite"-knop). Concludeerde de optimizer `changed: false` ("Already optimal — nothing to change"), dan verscheen die knop niet, bleef de teller staan en groeide de badge met élk verder gebruik — permanent vast. Fix: een review die "niets te wijzigen" concludeert HEEFT het bewijs verbruikt → `/skills/{name}/optimize` markeert nu zelf bij `changed=false` (de skill-body blijft uiteraard ongemoeid — een oordeel is geen herschrijving), en de console ververst meteen zodat de badge verdwijnt. **Tweede, latente bug meegenomen**: de marker was een ruwe observatie-telling, terwijl `observations()` een ringbuffer is met cap `_MAX_OBS=200` — zodra een skill die cap raakte bevroor `len(obs)` en kon `new_since_optimized` nooit meer groeien; suggesties voor juist de meest gebruikte skills zouden dan stilletjes voor altijd stoppen. Observaties krijgen nu een monotoon `seq`-nummer (overleeft de cap, want alleen de oudste regels vallen weg) en de marker bewaart `seq:<n>` → verschil blijft exact. Oude bare-count markers worden nog gelezen (backwards compatible). Tests: cap-scenario + legacy-marker + end-to-end "already optimal verbruikt de signalen" (orchestrator 203 groen, brain 254 groen, console 56 groen + build OK). **NB: vereist Restart brain** — de draaiende brain rapporteert nog 14.

- [x] **U160 — demo-persona die standaard met de app meekomt (nieuw type `demo`)** · `pending`
  Elke andere persona wordt door de gebruiker aangemaakt of geïmporteerd; deze wordt mee-geïnstalleerd zodat een verse installatie meteen kan tónen wat het brein doet (profiel, graph, sources, skills) zonder eerst data te typen of een echt familielid op een beamer te zetten. **Mila Kovač** (id `mila`, `kovač` = "smid" in het Kroatisch — een code-smid): fictief, 32, backend-developer, [[Java]] in hart en nieren ([[Spring Boot]], [[JVM]], [[virtual threads]], [[Devoxx]]), Europese roots ([[Ljubljana]] → [[Wenen]] → [[Gent]]), sportief ([[trail running]] ~50 km/week, [[bouldering]], woon-werk op de [[racefiets]], traint voor een [[ultramarathon]]) plus wat kleur voor demo's (espresso, git-branches vernoemd naar Tour-etappes, sourdough). 22 facts in dezelfde `[[wiki-link]]`-stijl als gemined materiaal, dus ze vult de graph net als een echt profiel. Nieuwe `PersonRole.DEMO` + gestippelde, gedempte badge in de console zodat ze nooit als echt persoon leest. **Passief leren is geblokkeerd** voor `role=demo` (naast de bestaande minor-regel): echte gesprekken mogen niet in de gecureerde demodata lekken. Seeding: eenmalig bij opstart als het profiel ontbreekt; verwijder je haar, dan blijft ze weg (markerbestand naast de knowledge-DB); `DEMO_PERSONA=false` slaat alles over. **Bug gevangen tijdens verificatie**: bij de in-memory store (dev/tests) schreef de marker in `./data` van de working tree — een testrun blokkeerde daarmee stilletjes de échte, persistente installatie; nu wordt bij een niet-persistente store géén marker geschreven en wordt ze elke boot opnieuw geseed (regressietest toegevoegd). Ook de logregel gebruikt het ASCII-id i.p.v. de naam (de `č` laat logging op een cp1252-Windowsconsole klappen). Levenscyclus live geverifieerd tegen de versleutelde store (fresh install → seed; restart → niet opnieuw; na verwijderen → blijft weg). Brain 261 groen, shared-schemas 124 groen, console 56 groen + build OK.

- [x] **U161 — handmatig richten van kop (camera) en torso met een sleepbare bal op het camerabeeld** · `pending`
  Pijltjesknoppen dwingen je te vertalen van "kijk daarheen" naar "vier keer links"; nu sleep je een **bal rechtstreeks op het live camerabeeld** — de bal blijft staan waar je richtte, dus de control leest als een richtpunt i.p.v. losse stapjes. Horizontaal = kop-yaw, verticaal = kop-pitch; de **torso** krijgt een eigen schuifregelaar (aparte as, hoort niet in dezelfde pad) met een centreerknopje. Dubbelklik op het beeld centreert de kop. Nieuwe route `POST /robot/aim` (robot-runtime) + brain-proxy + `RobotClient.aim`; waarden zijn -1..1 fracties van een veilig bereik (kop ±40° yaw / ±23° pitch, torso ±69°) zodat de pad nooit een onbereikbare pose kan commanderen. **Face-tracking wordt gepauzeerd bij het eerste richten** — anders trekt de daemon de kop meteen terug naar het dichtstbijzijnde gezicht en voelt de pad dood (dezelfde strijd als U137); hervatten gebeurt expliciet via "Resume follow-me" in de balk, want automatisch hervatten zou de kop wegrukken van waar je net richtte. Console: `pointermove` vuurt veel sneller dan de robot beweegt, dus verzoeken worden **gecoalesceerd** (max één in flight, altijd de laatste positie) — anders bleef de kop seconden nabewegen na loslaten. Tests: clamping, torso-weglaten, junk-waarden (robot-runtime 74 groen; console 56 groen + build OK). **Live geverifieerd op de robot**: yaw 0.8 → 0.56 rad, torso 0.5 → 0.6 rad, `tracking_paused` exact één keer true, en hervatten zet tracking weer aan.

- [x] **U162 — expliciete Follow/Manual-modus: richten en face-tracking kunnen niet meer vechten** · `pending`
  De bal-besturing uit U161 pauzeerde tracking impliciet (server gaf `tracking_paused` terug, met een "Resume follow-me"-linkje) — je kon dus richten terwijl de robot dacht dat hij nog volgde, en de kop werd heen en weer getrokken. Nu één expliciete segmented switch **Follow | Manual** op de camerabeeld: in Follow-modus wordt de aim-pad + torso-slider helemaal **niet gerenderd** (richten is dan onmogelijk, geen conflict); in Manual staat follow-me aantoonbaar uit. `sendAim()` heeft dezelfde guard nog eens in code, zodat een blijven-hangende drag of een toetsenbord-nudge op de slider geen pose kan doorlaten nadat de modus terugklapte. **Tweede conflictbron gedicht**: het Robot-paneel had zijn eigen `tracking`-ref náást deze switch — twee refs voor één robotinstelling liepen uiteen (paneel zei "volgend", camera had net handmatig gericht). `tracking` verhuisde naar de robotStore met een `setTracking()` die optimistisch schakelt en **terugdraait als de robot weigert** (UI claimt nooit een modus waarin de robot niet staat); `syncFromStatus` neemt de robot als bron van waarheid (een motie of de follow-me-watchdog kan tracking zelf wijzigen). Bij openen wordt `/robot/status` gelezen zodat de switch niet liegt. **Live geverifieerd in de draaiende app**: één klik op Follow in de camera liet de Follow-toggle in het Robot-paneel meteen omslaan ("Click to follow" → "Following faces — click to stop"), de torso-slider/aim-pad verdwenen uit de DOM, en gezichtsherkenning pikte weer op (Tycho 93%) — geen console-fouten. Console 62 groen (+6 store-tests) + build OK.

- [x] **U163 — conversatie sloeg op hol: mic-AGC blies kamerruis naar spraakniveau (+ dubbel antwoord)** · `pending`
  Symptomen uit het transcript: twee antwoorden op één zin (21:34:46 én 21:34:59; 21:35:20 én 21:35:26), antwoorden op niets ("Fanny." → mop), en een Sloveense begroeting op een verhaspeld "Je moječvi". **Hoofdoorzaak in mijn eigen U154-code**: de streaming-AGC in `stream_audio` liet `running_peak` naar `1e-4` zakken in een stille kamer, waardoor de versterking opliep tot **40×** — het ruisniveau werd naar het 0.5-doelniveau geblazen en OpenAI's server-VAD las dat als spraak, dus elke paar seconden een "beurt" waar Richie beleefd op antwoordde. Fix: poort op **RMS i.p.v. piek** (live gemeten: kamergeritsel is ~0,010 RMS met pieken tot 0,09 — een piekpoort laat elke deurklik door, een RMS-poort onderscheidt "iemand praat" van "er tikte iets"); onder de poort gaat audio ONGEVERSTERKT door. Live effect gemeten op de Pi: versterking van 5,7× naar 2,6× bij aanwezige ruis, en 0× bij stilte. **Dubbel antwoord**: `initial_text` beantwoordt de wake-zin al, maar de mic-stream opende op de STAART van diezelfde zin (+ galm) → tweede antwoord op dezelfde zin; mic blijft nu `REALTIME_SEED_MUTE_S` (1,5s) dicht na het seeden. **Derde guard**: `semantic_vad` kreeg `eagerness=low` (default vuurt op de kleinste pauze), en de `server_vad`-fallback expliciete drempels (0,6 / 900ms stilte). Tests: RMS-poort met deurklik-scenario + "spraak wordt nog steeds op niveau gebracht", seed-mute (geen mic-audio naar server) en het weer opengaan ervan, plus turn-detection-config (robot 76 groen, brain 264 groen). Gedeployed + live geverifieerd. **§9-eerlijk**: de poortwaarde (`MIC_STREAM_GATE=0.02`) is afgestemd op één kamer op één moment; blijft hij op ruis antwoorden, dan is de volgende stap `turn_detection.create_response=false` — zelf pas antwoorden als de input-transcriptie een echt commando blijkt, ten koste van ~0,2-0,4s latency.

- [x] **U164 — bal-besturing was gespiegeld op ALLE assen (operator-frame vs. SDK-frame)** · `pending`
  Op de echte robot nagemeten met camerabeelden i.p.v. op tekenconventies te vertrouwen. Vóór de fix: `yaw=+1` (bal naar **rechts**) zwenkte de camera naar wat **links** stond (het blauwe gordijn/de eierstoel i.p.v. de zwarte kast bij het raam); `pitch=+1` (bal naar **beneden**) bracht juist méér plafond in beeld; `body_yaw=+1` draaide de torso naar links. Oorzaak: het SDK-hoofdframe is rechtshandig (+z-yaw draait LINKS, +x-pitch kantelt OMHOOG), terwijl de bal-metafoor "wijs naar dít punt in het beeld" is — dus precies omgekeerd, op alle drie de assen tegelijk (vandaar dat het zo verwarrend aanvoelde). Fix in `aim()`, de enige plek waar schermintentie naar robotpose vertaalt: de conventie staat nu expliciet in de docstring (**+yaw = rechts in beeld, +pitch = omlaag, +body_yaw = rechts**) en wordt daar genegeerd naar het SDK-frame. Alleen de console-pad stuurt `aim` aan, dus geen andere client raakt van slag. **Live geverifieerd na deploy**: `yaw=+1` toont nu de kast+raam die rechts stonden, `pitch=+1` toont de vloer. Tests leggen de conventie vast (rechts → negatieve SDK-yaw, omlaag → negatieve pitch, torso idem) plus dat de clamping op de mechanische limieten intact blijft; robot-runtime 78 groen.

- [x] **U165 — follow-me pauzeren zonder de face-tracker te slopen + zichtbaar maken of hij een gezicht ziet** · `pending`
  Diagnose eerst: brain én robot meldden `tracking:false` — dat kwam van mijn eigen U164-aim-metingen (elke aim pauzeert het volgen). Aanzetten lukte foutloos, de daemon had de camera en de kop bewoog (idle-scan draaide), maar er stond op dat moment **niemand voor de robot**, dus "volgt niet" was niet te reproduceren. Ook getest en verworpen: een blijvende scheefstand door vastzittende wobbler-offsets (~1° verschuiving tussen twee identieke `aim(0,0)`-frames; het grote beeldverschil was gewijzigde belichting). **Wel een echte oorzaak gevonden in de SDK-docs**: `start_head_tracking(weight)` documenteert expliciet dat `weight=0` de detectie *pauzeert zonder de tracker af te breken* ("for cheap on/off"), terwijl `stop_head_tracking()` de FaceTracker-thread én zijn camerakoppeling sloopt. Wij riepen dat laatste aan bij **élke aim** (de bal vuurt per sleepbeweging!), bij **elk handmatig gebaar** en bij elke Manual/Follow-wissel — sinds U161/U162 dus tientallen keren per minuut. Die thread-churn (met een `join(timeout=2)` die kan verlopen en de oude thread laat leken) is een geloofwaardige weg naar een tracker die niet meer heracquireert. Nu: aim-pauze, gebaar-pauze en Manual-modus gebruiken `weight=0`/`weight=1`; alleen `sleep` sloopt nog echt af. **Plus observeerbaarheid**, want "lijkt niet te werken" was niet te onderscheiden van "er staat niemand": `RobotState.face_visible` (via de SDK's `get_tracked_face`, niet-blokkerend, faalt stil) en een groen bolletje op de Follow-knop — dof = volgend maar niemand in beeld, groen = gezicht vast. Live geverifieerd na deploy: `{"tracking":true,"face_visible":false}`, dus de tracker leeft en antwoordt. Tests: aim pauzeert met gewicht 0 en hervat op 1 zonder teardown, gebaren idem, en de status rapporteert de drie gezichtstoestanden; robot-runtime 80 groen, shared-schemas 124 groen, console 64 groen + build OK. **§9-eerlijk**: de oorspronkelijke klacht is niet gereproduceerd (geen gezicht voor de robot tijdens het meten) — dit verwijdert de meest waarschijnlijke oorzaak én maakt de volgende keer meteen zichtbaar wélke van de twee het is.

- [x] **U166 — geautomatiseerde releases op elke push naar master (notes + screenshots + installers voor alle platformen)** · `pending`
  `release.yml` herschreven: push naar master (of een `v*`-tag, of handmatig) → versie `1.<run>.0` + tag → volledige testgate (alle Python-suites + console) → **buildmatrix Windows (NSIS), macOS (dmg+zip, arm64 én x64, ongesigneerd) en Linux (AppImage+deb)** → GitHub Release met alles eraan. electron-builder-config kreeg mac/linux-targets + voorspelbare artifactnamen; de uv-bootstrap in de desktop-app was Windows-only (PowerShell) en kan nu ook macOS/Linux (`install.sh`). **Screenshots privacy-veilig per constructie**: een aparte job boot een wegwerp-demo-stack ín de runner — fake robot (geen camera), echo-LLM (geen keys), lege skills-vault en wegwerp-DB via `SKILLS_DIR`/`DATABASE_URL`, in-memory knowledge met alléén de fictieve demo-persona (U160) — en fotografeert de app met Playwright (console+chat, Mila's profiel, de knowledge-graph). Er bestáát geen persoonlijke data in die omgeving. Job is optioneel (`continue-on-error`): een release zonder screenshots verslaat geen release. Release notes: ledger-highlights sinds de vorige tag (de units zíjn de changelog) + ingebedde screenshots + installatietabel + gegenereerde commitlijst. **Lokaal end-to-end geverifieerd**: demo-stack geboot zoals CI hem boot, drie iteraties op het Playwright-script (assistentnaam is AURA op verse installs, chat ging naar `VITE_CONVERSATION_URL`, WS naar de brain) → drie schone schermafbeeldingen gecontroleerd op persoonlijke data. **Onderweg twee echte vondsten**: (1) de eerste testronde toonde jóuw skills — én `skills/.metrics/*.jsonl` met je letterlijke gesproken verzoeken stond gecommit in de repo → uit git verwijderd + gegitignored (de skill-.md's zelf blijven bewust versioned); (2) `ci.yml` triggerde op `main`/`develop` terwijl dit repo `master`/`aura-autobuild` gebruikt — CI draaide dus nooit; gefixt. NB: eerste release vuurt zodra `aura-autobuild` naar `master` gemerged wordt; `[skip release]` in een commitbericht slaat een release over.

- [x] **U167 — privacy-gate: persoonlijke data kan niet meer meekomen met een commit** · `pending`
  Eerst geauditeerd, toen ingebouwd. **Audit**: repo is private; tracked tree bevat géén secrets-patronen, persoonlijke e-mails, DB's, audio of logs; de twee env-bestanden zijn bewuste templates (localhost-URLs / lege waarden). Wél in de **historie**: de twee `skills/.metrics/*.jsonl` met letterlijke spraakverzoeken (in U166 uit HEAD gehaald) zitten nog in oude commits — purge vergt history-rewrite + force-push, ligt als optie bij de eigenaar. **Ingebouwd**: `scripts/privacy_scan.py` (stdlib-only, één bron van waarheid) blokkeert op klasse — paden (data/, skills/.metrics, *.db, *.enc.json, audio, logs, *.jsonl, .env*, sleutelmateriaal, brain-exports, camerasnapshots) én inhoud (OpenAI/GitHub/Slack/AWS/Google-keys, private-key-blokken, credential-toewijzingen mét echte waarde, persoonlijke e-mailadressen). Reviewbare uitzonderingen: `ALLOWED_PATHS` voor gecureerde templates en een `privacy-ok`-regelmarker voor testfixtures. Draait op twee lagen: **pre-commit-hook** (`.githooks/pre-commit`, geactiveerd via `core.hooksPath`, gedocumenteerd in README) en **CI-backstop** (nieuwe `privacy`-job in ci.yml + stap in de release-testgate — een hook is te omzeilen met `--no-verify`, CI niet). Eerste scan ving meteen 5 hits: allemaal testfixtures ("correct-horse-battery", "fake-obo-token") → gemarkeerd. **End-to-end bewezen**: een gestagede nep-API-key werd door de hook geweigerd (commit vond aantoonbaar niet plaats), een schone commit passeert (deze). Scanner heeft eigen regressietests (7 groen: padklassen incl. Windows-separators, secrets, e-mails, placeholders/binaries, en een echte-repo `--staged`-test). Output puur ASCII (cp1252-les uit U160).

- [x] **U168 — CI echt groen: pytest-spawn-fix + lint-sweep (die 2 slapende bugs ving)** · `pending`
  De allereerste échte CI-run (mogelijk gemaakt door de U167-branchfix) faalde op twee fronten. **(1) test-job**: `uv run --package X pytest` → "Failed to spawn: pytest" — pytest zit per package in het `dev`-extra en `uv sync --all-packages` installeert extras niet; alle testregels in ci.yml én release.yml dragen nu `--extra dev` (alle 10 packages hebben dat extra, gecontroleerd). **(2) lint-job**: 341 ruff-fouten die nooit eerder gedraaid hadden. Autofix (204: import-sortering, ongebruikte imports, verouderde aliassen) + handmatig de rest; regellengte 100→120 (de commentaarrijke stijl van dit repo flagde 111 regels proza, geen codeproblemen), `UP042` bewust genegeerd (str-Enum→StrEnum verándert `str(member)`-gedrag — geen lint-gedreven runtimewijziging), `E402` toegestaan in tests (env-vóór-import is daar het punt). **De sweep ving twee echte slapende bugs**: `identity_service/auth_google.py` was kapot Python (weesregels van een oude versie na een `return` — het bestand kon niet eens geïmporteerd worden; alleen lazy imports verhulden dat) en `conversation_runtime/routes.py` had **vijf routes dubbel gedefinieerd** — het tweede blok was de oude "[echo]-stub tot LLM aangesloten is"-versie die door FastAPI's eerste-match-routing nooit draaide: 113 regels dode code weg. Alles herdraaid na de sweep: 771 tests groen over alle 10 suites (124/5/6/5/80/17/203/20/40/271). Node-20-deprecatiewaarschuwingen in Actions zijn kosmetisch (runner-intern) en genegeerd.

- [x] **U168b–e — de CI-saga: vijf runs, vijf lagen verborgen omgevingsafhankelijkheid, nu volledig groen** · `done`
  Run 29788955025: **lint ✓ test ✓ console ✓ privacy ✓** — de eerste volledig groene CI-run ooit voor dit repo. Wat de opeenvolgende runs afpelden, elk onzichtbaar op de Windows-devmachine: **(b1)** `test_media_control` patchte het globale `os.name` naar "nt" — flipt `pathlib.Path` naar `WindowsPath` proces-breed en liet op Linux zelfs pytest's eigen internals crashen (INTERNALERROR die alle rapportage opslokte); platformcheck is nu een seam (`_is_windows()`). **(b2)** `test_latency` wachtte precies één scheduler-hop op bus-dispatch → begrensde wachtlus. **(c)** `LLM_PROVIDER=echo` was een race tegen importvolgorde (config-singleton wordt bij import gebouwd, default openai) → conftest-guard (vroegste hook) + jobniveau-env in beide workflows. **(d)** De échte laag eronder: `update_config("openai",…)` in een test muteerde de singleton en monkeypatch herstelt geen module-globals — provider=openai lekte naar alle latere tests. Pijnlijke bijvangst: lokaal "slaagde" test_latency doordat de echte `OPENAI_API_KEY` er stilletjes een ÉCHTE OpenAI-call van maakte, elke run. Keyless gereproduceerd (`env -u OPENAI_API_KEY` → exact de CI-fout), autouse-fixture herstelt de singleton rond elke test, keyless geverifieerd (orchestrator 203 + brain 264 groen zonder key). **(e)** Twee brain-tests leunden op Windows' ~15ms-klokkorrel: de barge-in-test gaf de interruptietak een 2,5ms-venster bij 10ms event-pacing (Linux' precieze klok sloot het venster), en de music-guard-test eiste exact één commando waar het aantal een race is (7 op Linux) → venster 1,25s resp. assert op inhoud. Levensles van de saga: "lokaal groen" betekende hier vijf keer "de devomgeving verstopt het" — keyless draaien is voortaan de eerlijke lokale benadering.

- [x] **U169/U169b — eerste automatische release live: v1.3.0 met installers voor alle drie platformen** · `done`
  Master ge-fast-forward vanaf `aura-autobuild` (218 commits, schone ancestor) → de release-pipeline uit U166 kreeg zijn vuurdoop in drie runs. Run 1: mac ✓, maar Linux eiste `homepage` in package.json en Windows' default pwsh hakte `-c.extraMetadata.version=…` stuk (electron-builder las het als config-bestandspad) → `shell: bash` op alle runners. Run 2: Windows ✓ met de bash-fix, Linux wilde vervolgens óók een author-e-mail voor deb → GitHub-noreply-adres (de eigen U167-privacy-scanner blokkeert terecht persoonlijke provider-adressen in tracked files). Run 3: **alles groen** → release **v1.3.0** gepubliceerd met 10 assets: Windows setup.exe (78 MB), mac dmg+zip voor arm64 én x64, Linux AppImage+deb, plus de drie demo-stack-screenshots (console+chat, Mila's profiel, knowledge-graph — geen persoonlijke data, per constructie). Testgate en screenshotjob waren in álle drie de runs groen — de fragiele stukken bleken de betrouwbaarste. Open punt: versienummers zijn semver-formaat maar (nog) niet semantisch — markervoorstel (`[major]`/`[minor]`, default patch) ligt bij de eigenaar.

- [x] **U170 — About-dialoog in de titelbalk met link naar mityjohn.com** · `pending`
  Info-knop in de titelbalk (naast Capabilities) → About-modal: AURA-logo/naam/tagline, versienummer (echt releasenummer via nieuwe `aura:app-version`-IPC in de desktop-app; "dev" in browser/dev-runs), korte omschrijving, en twee linkkaarten — **mityjohn.com** ("blog & projects by mITy.John") en de GitHub-repo ("source & releases") — plus "Made by Jan Van Wassenhove". Electron kreeg een `setWindowOpenHandler`: `target=_blank`-links openen in de systeembrowser, nooit als tweede Electron-venster. Geverifieerd in de browser (DOM: modal + beide links correct; screenshots haperden op de MJPEG-camerastream). Console 64 groen + build OK. **Ontdekking tijdens verificatie**: op poort 5173 draait inmiddels de GEÏNSTALLEERDE v1.3.0 (`AppData\Local\Programs\AURA\AURA.exe`) — de eigenaar heeft de release geïnstalleerd; repo-wijzigingen verschijnen daar pas na een volgende release + update, niet meer via lokale rebuilds.

- [x] **U171 — echt app-icoon: de Reachy Mini-silhouet in plaats van de generieke bot-outline** · `pending`
  Programmatisch getekend (PIL, 2048-master → LANCZOS-downscales): witte capsulekop met twee grote camera-ogen (navy, blauwe highlight) en de twee kenmerkende schuine antennes met blauwe bolletjes, op de app-donkerblauwe afgeronde tegel (#0f172a→#1e293b) met console-accentblauw (#60a5fa). Leesbaar geverifieerd tot 16px (previewstrip). Assets: `icon.png` 512px (mac/linux/venster) + `icon.ico` met 7 Windows-maten (16–256). Bonus in dezelfde stijl: het tray-icoon was een hardcoded base64 "blauw bolletje" → gebruikt nu het echte icoonbestand, en de console had helemaal geen favicon → `public/favicon.png` (64px, zelfde artwork) + link-tag. Console-build OK; komt mee in de volgende release/installer.

- [x] **U172 — semantische versionering: bump uit commitboodschappen i.p.v. buildnummer** · `pending`
  De versiejob leest nu de laatste `v*`-tag en bepaalt de bump uit de commits sindsdien: `[major]` ergens in een boodschap → X+1.0.0, `[minor]` → X.Y+1.0, anders patch (de meeste units zijn fixes/verfijningen). Expliciete tag-push wint altijd. Dry-run tegen de echte historie: volgende release wordt **v1.5.1** (geen markers sinds v1.5.0 — klopt). Vanaf nu: `[minor]` in de commit voor features, `[major]` voor breaking changes.

- [x] **U173 — in-app updatedetectie: de app vraagt zelf of hij mag updaten** · `pending`
  Nieuw `updater.cjs` (dependency-geïnjecteerd, los testbaar) + wiring in main: 30s na start en daarna elke 4 uur checkt de gepackagede app GitHub Releases. Nieuwere versie → native dialoog: **"Download & installeer"** (Windows: downloadt de setup.exe naar temp, start de NSIS-wizard, app sluit af — instellingen blijven staan), **"Later"**, of **"Deze versie overslaan"** (onthouden per versie in userData). Niet-Windows of downloadfout → releasepagina in de systeembrowser. **Privérepo-realiteit eerlijk opgelost**: anoniem geeft de API 404 → check faalt stíl (een updatecheck mag nooit met netwerkfouten storen); staat er een `GITHUB_TOKEN` in `infra/dev/.env` (zelfde var als de connectors) dan werkt het nu al, en zonder token gaat het vanzelf werken zodra de repo publiek wordt — gedocumenteerd in `.env.example`. **Live geverifieerd** met een tijdelijk gh-token (nergens opgeslagen): pure logica (incl. "dev" verstoort nooit), anoniem → stil null, mét token → vindt v1.5.0 + exact het `windows-setup.exe`-asset, vanaf nieuwste versie → geen prompt. Kanttekening: het downloadpad zelf (80MB-stream) is niet end-to-end getest — bij falen valt hij aantoonbaar terug op de releasepagina.

- [x] **U174 — Electron-icoon-mysterie opgelost + semver-scanner beet zichzelf** · `pending`
  **(1) "Desktop app toont nog Electron-icoon"**: icoon rechtstreeks uit de geïnstalleerde `AURA.exe` (v1.5.0) geëxtraheerd → inderdaad het Electron-atoom. Buildlogs van álle release-runs: "default Electron icon is used — reason=application icon is not set". Wortel: `.gitignore` regel `build/` gold óók voor `apps/desktop/build/` — de iconen (ook het oude U37-icoon!) zaten **nooit in git**, dus elke CI-checkout bouwde zonder icoonbestand; alle releases tot nu toe droegen stilletjes het Electron-default. Lokaal bewezen dat de build mét bestand wél klopt (icoon uit lokaal gebouwde exe geëxtraheerd → Reachy-kop). Fix: gitignore-negatie (`!apps/desktop/build/**`) + iconen toegevoegd. **(2) De semver-release werd v2.0.0 i.p.v. v1.5.1**: de U172-commit-bódy die de markerconventie beschrijft bevatte letterlijk de major-marker → de scanner (die hele bodies las) vuurde erop. Zelf-referentiële klassieker. Fix: alleen **subject-regels** scannen (`git log --pretty=%s`); markers horen voortaan in de commit-titel. v2.0.0 blijft staan als baseline — een gepubliceerde tag terugdraaien is duurder dan het waard is.

- [x] **U175 — "camera werkt niet meer": stille MJPEG-stall + auto-herstel** · `pending`
  Diagnose eerst: de hele keten bleek gezond — Pi levert verse frames (1,2 MB, verspringend), brain proxied ze, de stream pompt 14+ MB/6s. Het "kapotte" beeld is de klassieke MJPEG-kwaal: valt de sérver even weg (brain-herstart, app-update, Pi-reboot), dan stopt de `<img>` **geluidloos** — geen error-event, dus de bestaande retry greep nooit in en het paneel bleef bevroren tot een volledige page-reload. Fix drieledig: (1) de WS-composable meldt elke (her)verbinding via `robotStore.noteWsOpen()` → het camerapaneel remount de stream zodra de brain terug is; (2) idem bij robot-terugkeer (`connected` false→true); (3) een handmatige ↻-knop naast de LIVE-badge voor alle overige gevallen. **Live geverifieerd in de echte app**: knop → `streamKey` bump → verse MJPEG-verbinding → binnen 2,5s weer LIVE. Console 66 groen (+2 store-tests) + build OK.

- [x] **U176 — v2.0.1/2 crashte bij start: updater.cjs zat niet in de package** · `pending`
  "Cannot find module './updater.cjs'" — het nieuwe updatermodule (U173) stond niet in electron-builders `files`-lijst, dus de app.asar miste het en de main-process-require crashte direct bij launch. Packaging slaagt gewoon mét ontbrekende modules, dus CI zag niets. Fix: bestand toegevoegd aan `files` + **CI-guard** in de buildjob die na het packagen de app.asar op alle drie platformen uitleest en faalt als main/preload/updater ontbreken — lokaal getest tegen een verse build (guard slaat aan bij ontbreken, groen bij aanwezig). Wie v2.0.1/2 installeerde: v2.0.3 eroverheen installeren lost het op.

- [x] **U177 — DATAVERLIES-BUG: alle eigenaarsdata stond in de installatiemap en werd door elke update gewist** · `pending`
  Melding: "na update zijn mijn brain/mensen weg", "kan mezelf niet meer laten herkennen", "waarom staat er BENIGN". Eén oorzaak, met bewijs: de brain draait met `cwd = resources/aura` (ín de installatiemap), en ALLE persistente paden waren daar relatief aan — `.env` (incl. `KNOWLEDGE_PASSPHRASE`), `data/knowledge.enc.json` (mensen + facts), `data/recognition.enc.json` (gezichts-embeddings), `data/aura-memory.db` (gesprekken, herinneringen, todo's) en `skills/`. NSIS vervangt die map bij elke update → alles weg. Vastgesteld: `.env` bevat nog maar `SETUP_DONE`+`VOICE_MODE` (passphrase weg → `omk_loaded:false`, tier **benign**, en dáárom weigert gezichtsherkenning: biometrie mág alleen versleuteld, ADR-008), `knowledge.enc.json` bestaat nergens meer op de schijf, `skills/` is verdwenen, `aura-memory.db` is vers/leeg. Geen export in Downloads/Desktop/Documents, prullenbak leeg → **niet herstelbaar**. Fix: alle staat verhuist naar `userData` (`%APPDATA%/aura-desktop` — overleeft updates én herinstallatie): `AURA_ENV_FILE`, `KNOWLEDGE_DB_PATH`, `RECOGNITION_DB_PATH`, `DATABASE_URL`, `SKILLS_DIR` worden expliciet gezet (waarden uit `.env` winnen nog steeds), plus een eenmalige migratie die achtergebleven staat uit de oude locatie overkopieert zonder ooit te overschrijven. Dev-checkouts houden de repo-relatieve paden, zodat een dev-run de echte app-data niet aanraakt. **End-to-end bewezen**: brain geboot op userData-achtige paden → tier sensitive + `knowledge.enc.json` aangemaakt; persoon + fact toegevoegd; brain hard gestopt en opnieuw gestart (simuleert de update) → persoon én fact staan er nog, tier nog steeds sensitive.

- [x] **U178 — updatecheck zweeg: privérepo + geen token = onzichtbaar niets** · `pending`
  "Zou hij mij niet automatisch moeten laten weten dat er een nieuwe release is?" — terecht. Nagemeten: de geïnstalleerde v2.0.3 bevat `updater.cjs` wél (U176-fix werkte), maar er is nergens een `GITHUB_TOKEN` (niet in systeem-env, niet in `.env` — die werd door de U177-bug gewist), en omdat de repo **privé** is antwoordt GitHub met 404. Mijn U173-ontwerp "faal stil" (juist voor een achtergrondcheck: nooit zeuren met netwerkfouten) maakte dat volledig onzichtbaar. Fix: `checkForUpdate` geeft nu een **status** terug (`update` / `current` / `unauthorized` / `error`) i.p.v. null, de achtergrondcheck handelt nog steeds alleen op `update`, en de About-dialoog kreeg een **"Check for updates"-knop die het resultaat uitspreekt** — inclusief "de release-repo is privé, voeg GITHUB_TOKEN toe of maak de repo publiek". Alle vier de uitkomsten live getest tegen de echte GitHub-API (privé zonder token → unauthorized; met token vanaf 2.0.3 → update v2.0.4 + juiste asset; vanaf nieuwste → current; kapot token → unauthorized) en alle drie de meldingen visueel geverifieerd in de app (kleurcodering warn/new/ok). Console 66 groen.

- [x] **U179 — "This is me"-knop weg: twee blokkades, beide door de update veroorzaakt** · `pending`
  De knop is voorwaardelijk (`v-if="recognitionEnabled"`) en `/recognition/status` gaf `{enabled:false, embedder:null}`. Twee onafhankelijke oorzaken, beide gevolg van de gewiste installatiemap (U177): **(1) geen passphrase** → kluis onversleuteld → herkenning start nooit (biometrie mag alleen versleuteld). Erger: er was **géén bereikbare UI** om er alsnog een te zetten — het passphrase-veld in BrainPanel verschijnt alleen als de kluis `locked` is (dus al versleuteld), `KnowledgePanel.vue` (met de secure-flow) is nergens meer gemount, en de SetupWizard draait alleen bij eerste installatie. Doodlopend. **(2) de gezichtsmodule was fysiek weg**: de app-venv (164 packages) bevat geen insightface/onnxruntime, want de bootstrap draait `uv sync --all-packages` en dat commando **verwijdert ze actief** — met `--dry-run` bewezen: zonder de extra staat er letterlijk `- insightface==1.0.1`, `- onnxruntime==1.27.0`. Fixes: BrainPanel toont nu een **"Secure profiles"-blok** zodra de kluis onversleuteld is (roept `/setup/secure` aan: migreert profielen, bewaart de passphrase én start herkenning); bootstrap synct met `--extra recognition` (met terugval op een gewone sync zodat een wheel-probleem het opstarten nooit blokkeert) en kreeg een **revisiestempel** (`rev=2`) zodat bestaande installaties de extra alsnog ophalen; en de camerahint wees naar een niet-bestaand "Knowledge"-paneel → wijst nu naar de echte knop. Live geverifieerd tegen de draaiende brain: beide teksten renderen, invoerveld aanwezig, console 66 groen.

- [x] **U180 — "BENIGN" zei niets: badge nu in eigenaarstaal** · `pending`
  De badge in de brain-header drukte letterlijk de interne enum-waarde af (`UnlockTier.BENIGN` → "BENIGN"), grijs en zonder uitleg. Dat is jargon uit ADR-008 en beantwoordt geen van de twee vragen die een eigenaar wél heeft: *staat mijn persoonlijke data versleuteld op dit toestel, en kan ik er nu bij?* Nu drie duidelijke toestanden met kleur en tooltip: **"Not encrypted"** (oranje — "profielen staan onversleuteld op dit toestel en gezichtsherkenning blijft uit; zet een passphrase onder Secure profiles"), **"Encrypted"** (groen) en **"Locked"** (rood, met de vraag om de passphrase). Logica verhuisd naar `src/lib/vaultState.ts` zodat álle drie de toestanden unit-getest zijn — inclusief een test die bewaakt dat interne termen (benign/sensitive/omk/tier) nooit meer in de UI lekken; een privacysignaal dat stilletjes iets verkeerds zegt is erger dan geen signaal. Live geverifieerd tegen de draaiende brain: "Not encrypted" in oranje. Console 70 groen (+4).

- [x] **U181 — nieuw gezicht wordt automatisch een gast-profiel** · `pending`
  Tot nu toe bleef een onbekend gezicht eeuwig "unknown": de sighting-log bewaarde een thumbnail voor handmatig taggen, maar de robot herkende diezelfde persoon de volgende keer opnieuw niet. Nu maakt de perceptielus bij een **écht nieuw** gezicht (de log dedupliceert al op embedding-gelijkenis, dus `count==1` = eerste keer) automatisch een profiel `guest-N` / "Guest N" met rol **guest** — bewust de minimale rol uit ADR-008: alleen een naam om mee te groeten, geen facts, geen passief leren. De embedding wordt meteen ingeschreven bij de matcher, zodat de persoon vanaf dat moment als "Guest 1" herkend wordt in plaats van als onbekende; het `PersonRecognized`-event komt dus direct terug met `known=true`. De eigenaar kan de gast hernoemen naar een echte persoon of hem vergeten met één klik. Nieuwe capability **"Remember new faces as guests"** (`AUTO_GUEST`, standaard aan, live schakelbaar) — automatisch biometrie van bezoekers vastleggen hoort een zichtbare, uitzetbare keuze te zijn. Werkt alleen met versleutelde kluis (de matcher bestaat pas als herkenning draait; biometrie mag nooit onversleuteld). Vier tests: nieuw gezicht → guest-1 + ingeschreven + `known=true`, hetzelfde gezicht spawnt géén tweede gast, id-botsing wijkt uit naar guest-2, en uitgeschakeld → géén profiel én géén vastgelegde biometrie. Brain 268 groen.

- [x] **U182 — repo is publiek: updatecheck werkt tokenloos + privacy-audit van de historie** · `pending`
  Geverifieerd: `visibility=PUBLIC` en een **anonieme** updatecheck (precies wat de geïnstalleerde app doet, zonder token) vindt nu `v2.0.8` mét het juiste `windows-setup.exe`-asset — de U178-statusweg "unauthorized" is daarmee vanzelf opgelost. Meteen een audit gedaan op wat publiek gaan blootlegt: (a) **geen enkel echt secret in de volledige historie** — de enige treffer op sk-/ghp-/xox-/AKIA-/private-key-patronen is `scripts/test_privacy_scan.py`, dat zijn de opzettelijke nep-fixtures van de scanner zelf; (b) ooit gecommitte env-bestanden zijn alleen `.env.example` (lege waarden) en `.env.production` (localhost-URL's) — beide bedoeld; (c) `data/` (kennis, embeddings, memory-DB) is altijd gitignored geweest en staat dus nergens in de historie. **Wel blootgesteld en gemeld aan de eigenaar**: de twee `skills/.metrics/*.jsonl` uit 7 oude commits (37 letterlijke spraakfragmenten, getagd `person: jan`) — in U166 uit HEAD gehaald maar nog in de historie; de getrackte `skills/*.md` met persoonlijke routines ("Jan's way of working", Spotify-playlists, VRT MAX); en het commit-auteursadres (persoonlijk Gmail in alle 239 commits). Direct opgeruimd wat wél in HEAD zat: het lokale robot-IP in de ledger vervangen door `<robot-ip>`.

- [x] **U183 — persoonlijke data uit de publieke historie gewist (history rewrite)** · `pending`
  Op verzoek van de eigenaar alle drie de blootgestelde zaken verwijderd met `git filter-repo`, na een volledige back-upbundle van de oude staat. Weg uit **elke** commit: de twee `skills/.metrics/*.jsonl` met 37 letterlijke spraakfragmenten, de drie persoonlijke skill-bestanden (`music.md`, `spotify-specifiek-nummer.md`, `vrtmax.md` — playlists, gewoontes), en het privé-Gmail-adres in auteur én committer van alle 240 commits (nu `janvanwassenhove@users.noreply.github.com`). Geverifieerd ná de rewrite: 0 treffers op `.metrics` in enige boom, alleen `skills/README.md` over, 0 gmail-vermeldingen, en 240 commits + 3 tags intact. Herhaling voorkomen op drie lagen: lokale git-identiteit staat nu op het noreply-adres, `skills/*.md` gegitignored (behalve README), en de privacy-scanner blokkeert persoonlijke skill-bestanden (met test). **Eerlijk over de grenzen**: force-push maakt de oude commits onbereikbaar via normaal bladeren, maar GitHub kan losse objecten nog even gecachet houden tot hun garbage collection — voor volledige zekerheid moet de eigenaar GitHub Support vragen die te purgen; en wie de repo al gekloond of geforkt had, houdt zijn kopie (0 forks op moment van schrijven).

- [x] **U184 — noodstop: één knop legt een op hol geslagen gesprek stil** · `pending`
  Uit het transcript bleek AURA op omgevingsgeluid te antwoorden en vervolgens op haar eigen echo — de sessie praatte tegen zichzelf. Er was géén manier om dat snel te stoppen: de mic-toggle zet alleen `VOICE_MODE`, maar breekt een lopende Realtime-sessie niet af en zwijgt de robot niet mid-zin. Nu een altijd zichtbare **rode STOP-knop** in de titelbalk → `POST /voice/panic` → (1) `stop_audio` kapt de spraak mid-woord, (2) `RealtimeSession.request_stop()` sluit de sessie binnen ≤1s (nieuwe vlag in de wachtlus), (3) `VOICE_MODE=off` zodat niets herstart, plus follow-up-vensters gewist. Mic weer aanzetten is een bewuste handeling. Werkt óók zonder actieve sessie (de klassieke pipeline kan even goed lussen). Vier tests: sessie stopt aantoonbaar binnen seconden i.p.v. de 600s-idle af te wachten, en panic knipt spraak + sessie + mic, ook zonder sessie.

- [x] **U185 — personen verwijderen werkte nooit (step-up sloot alles af)** · `pending`
  "Forget Jan…" stond in de UI maar `_require_stepup` weigert **altijd** zonder `STEP_UP_WEBHOOK_URL` (fail-closed by design). Gevolg: wissen was onmogelijk — onhoudbaar nu gastprofielen automatisch ontstaan (U181) en het recht om vergeten te worden een kernbelofte is. Nu: mét webhook blijft telefoongoedkeuring gelden; zónder webhook geldt een **getypte bevestiging** vanaf de console (`?confirm=<person_id>`, HTTP 428 als die ontbreekt) — bewuste intentie vanaf het eigen scherm, eerlijk gelabeld als zwakkere gate dan een bezitsfactor, maar oneindig beter dan een dode functie. De console stuurt de bevestiging mee na de bestaande `confirm()`-dialoog en toont nu ook de foutmelding als het misgaat. README-securitytabel bijgewerkt zodat de documentatie klopt met het gedrag.

- [x] **U186 — documentatie: AURA-betekenis + commerciëlere README** · `pending`
  Het acroniem staat nu bovenaan als tabel ("the name is the promise"): **Adaptive** (past gedrag aan persoon/context/situatie), **Unified** (conversatie, mail, Teams, agenda, todo's, memory en agents samen), **Robotic** (fysieke embodiment via Reachy Mini), **Assistant** (persoonlijke assistent/copilot, geen chatbot). README herschreven met een productbelofte bovenaan, een "why it feels different"-sectie (aankijken en terugpraten, de kamer kennen, het werk doen, zichzelf verbeteren, offline overleven, privacy als product) en een **install-sectie** die naar de kant-en-klare installers verwijst i.p.v. meteen naar docker/uv — een lezer kan nu downloaden en draaien zonder de repo te bouwen.

- [x] **U187 — Clear-knop voor de conversatie** · `pending`
  Na een op hol geslagen sessie (U184) staat het scherm vol antwoorden die niemand vroeg. Nieuwe **Clear**-knop rechtsboven in het conversatiepaneel (verschijnt alleen als er iets staat) wist de zichtbare transcriptie én de laatste latency-regel, maar **behoudt bewust het session-id** — de assistent onthoudt het gesprek dus nog; dit ruimt het scherm op, niet zijn geheugen. Test legt precies dat onderscheid vast (turns leeg, sessie intact). Console 71 groen.

- [x] **U188 — video liep achter: 680 KB per frame over WiFi** · `pending`
  Oorzaak uit de code + de eerdere doorvoermeting (U175: 14,5 MB in 6s): de robot stuurde **volledige 1280x720-JPEG's** terwijl de console ze in een paneel van ~300 px toont — 4x meer pixels dan zichtbaar, en met echte camerabeeldruis ~680 KB per frame. Bij 8 fps is dat ~5,6 MB/s (45 Mbit/s) over de WiFi van een Pi: het netwerk kan dat niet volhouden, frames stapelen op in de socket en het beeld loopt structureel áchter de werkelijkheid. Fix: de robot schaalt elk frame naar `CAMERA_STREAM_WIDTH` (640, `0`=origineel) met kwaliteit `CAMERA_STREAM_QUALITY` (70) vóór verzending, en `CAMERA_STREAM_FPS` ging van 8 naar 12. **Gemeten met een realistisch ruisbeeld**: 680 KB → 56 KB per frame (12x kleiner), bandbreedte 5,6 MB/s @8fps → **0,7 MB/s @12fps** — dus vloeiender én 8x minder data. Downscaling draait in een thread (blokkeert de eventloop niet) en valt bij élke fout terug op het origineel: video mag nooit stuk door een optimalisatie (getest, incl. te klein bronbeeld en corrupte input). Robot-runtime 82 groen. **NB: nog niet end-to-end op de robot geverifieerd** — Pi en app waren offline tijdens het bouwen; de bytewinst is bewezen, de gevoelde latency moet de eigenaar bevestigen na deploy.

- [x] **U189 — een gast benoemen, toekennen of verwijderen** · `pending`
  U181 maakt automatisch "Guest 1" aan, maar daarna liep het dood: er was geen manier om te zeggen wíé dat is. Nu drie duidelijke vervolgstappen in een blok bovenaan het gastprofiel ("This face was added automatically. Who is it?"): **(1) benoemen** — echte naam + rol (family/guest/minor/owner) → wordt een volwaardig profiel; **(2) toekennen aan iemand die je al kent** — keuzelijst van bestaande niet-gast-personen, en dan verhuist het **gezicht mee**: nieuw `EmbeddingMatcher.transfer()` ontsleutelt elk sample onder de bron-id en versleutelt het opnieuw onder de doel-id (de blobs zijn AES-GCM aan hun persoon gebonden via AAD, dus kopiëren kan niet), waarna de gast cryptografisch gewist wordt; **(3) verwijderen** — via de bestaande Forget (werkt sinds U185). Nieuw endpoint `POST /recognition/merge` weigert een onbekend doel (404) en samenvoegen-met-zichzelf (422) zonder iets te vernietigen. Tests: transfer op matcherniveau (gezicht wordt daarna als de echte persoon herkend, gast weg), merge end-to-end via de API tegen een echte versleutelde kluis, en de weigeringen. Brain 273, shared-schemas 126, console 71 groen; lint schoon.

- [x] **U190 — releases lagen stil door mijn eigen flaky test + de gast-explosie ingedamd** · `pending`
  Melding "kan gasten/personen niet verwijderen, niet hernoemen, type niet wijzigen" — en de oorzaak was niet de UI maar de **levering**: de app draaide v2.0.10 en de laatste **drie release-runs waren gefaald**, dus U185 (delete werkt), U189 (gast benoemen/toekennen) en de rest hadden de eigenaar nooit bereikt. Live bevestigd tegen de draaiende brain: `DELETE /knowledge/people/guest-7` → **HTTP 403 "Step-up webhook not configured"**, precies het gedrag van vóór U185. Boosdoener: mijn eigen U184-test gaf de nep-microfoon maar 200 chunks; op CI eindigde die stream vóór de stop en won `"mic stream ended"` van `"stopped by owner"` — een race in de TEST, niet in de panic stop. Nu een mic die het testvenster ruim overleeft (3x achter elkaar groen). **Tweede bevinding uit de screenshot**: 7 gastprofielen voor één huishouden. Oorzaak: één frame volstond om een profiel te verdienen, terwijl een half-herkend gezicht door **beide** netten valt (onder de 0,4-herkenningsdrempel én onder de 0,5-samenvoegdrempel van de sighting-log) — dus elke passage leverde een nieuwe "Guest N". Nu moet een gezicht **`AUTO_GUEST_AFTER_SIGHTINGS` keer** (3) gezien zijn vóór promotie, en geldt een plafond `AUTO_GUEST_MAX` (3) op nog-niet-benoemde gasten: daarboven blijft het een sighting die je met de hand kunt taggen. Twee tests: een vluchtig gezicht krijgt pas bij de derde waarneming een profiel, en boven het plafond wordt niets aangemaakt (event blijft `known=false`). Brain 275 groen, lint schoon.

- [x] **U191 — modellen per rol: alleen wat die rol écht kan draaien; naam en rol overal aanpasbaar** · `pending`
  Drie meldingen, één oorzaak per stuk. **(1) "ik kan niet hetzelfde model kiezen, bv. gpt-5.4, voor taken"** — de drie rolvelden waren `<input list=…>` datalists. Een datalist filtert op wat er al in het veld staat: met "gpt-4.1" ingetypt tóónt de browser gpt-5.4 domweg niet meer. Het model wás beschikbaar, het was onvindbaar. Nu echte keuzelijsten met "— use the model above —" als lege optie. **(2) "voor conversatie enkel spraakmodellen"** — klopt: de voice-loop praat speech-to-speech, een chatmodel kan daar niet in. **(3) "verifieer wat de provider zelf aangeeft"** — de lijst kwam al van de provider (`client.models.list()`), maar ongefilterd: embeddings, TTS, transcribe, image-modellen en realtime-endpoints stonden door elkaar, dus je kon een model kiezen dat pas bij het eerste verzoek stukliep. Nieuwe classificatie `_model_kinds()` in de orchestrator tagt elk model met `chat` / `vision` / `realtime` en laat wat geen van drie is helemaal weg; elke rol krijgt precies zijn lijst (Conversatie → realtime, Taken → chat, Schermbediening → vision), en het hoofdmodel toont geen realtime-endpoints meer. Een eerder opgeslagen model dat de provider niet meer aanbiedt blijft zichtbaar als "(not in the provider's list)" in plaats van stil te verdwijnen. Console valt terug op de id wanneer de brain nog van vóór U191 is. **Daarnaast**: naam en rol van **elke** persoon zijn nu ter plekke aanpasbaar (potloodje naast de naam → veld + rollijst + Save), niet langer alleen bij gasten — een typfout of een gast die familie blijkt te zijn was tot nu toe alleen te herstellen door de persoon te vergeten en opnieuw aan te leren. De persoon-**id** blijft de interne sleutel (gezichten, skills en memory hangen eraan); wie een profiel naar een andere id wil verhuizen gebruikt "assign to someone I know" (U189). Ten slotte de naamsverklaring (Adaptive/Unified/Robotic/Assistant) toegevoegd aan het About-venster, waar de README die al had. Geverifieerd in de draaiende console: rolkeuzelijsten bevatten exact realtime/chat/vision, gpt-5.4 staat weer bij Taken, en het hernoemveld opent met focus en bewaart. Orchestrator 10 groen, console-build schoon. **NB: de datalist-val is bewezen, de modellijst zelf is getest tegen id-patronen, niet tegen een live OpenAI-account** — als een provider een model raar noemt, valt het in de verkeerde emmer.

- [x] **U192 — de rode cirkel krijgt een naam en een plek, en de auto-update werkte nooit** · `pending`
  Vraag "wat doet die rode cirkelknop in de titelbalk? hoort die niet in het robot-paneel?" — terechte vraag, en het antwoord op "wat doet hij" hoorde niet in een tooltip te zitten. Het is de panic stop (U184): hij kapt de robot middenin een zin af, beëindigt de sessie en zet de microfoon uit. Staat nu **gelabeld in het Robot State-paneel** ("Stop talking", met de gevolgen uitgeschreven), tussen de andere knoppen die het gedrag van de robot sturen. In de titelbalk blijft hij enkel over als **vangnet wanneer het linkerpaneel dichtgeklapt is** — een noodrem mag niet verdwijnen omdat je een paneel hebt verborgen (geverifieerd: paneel open → gelabelde knop, geen titelbalkicoon; paneel dicht → titelbalkicoon terug).
  **De echte vondst zat in de tweede vraag** ("laat de app automatisch checken en zelf downloaden/installeren"). Dat mechanisme bestond sinds U173/U178 — periodieke check, dialoog, download, installer starten — maar regel 518 van `main.cjs` gaf `token` mee aan `downloadAsset()`, en **die naam is nergens in dat bestand gedeclareerd**. Elke klik op "Download & installeer" gooide dus een ReferenceError op de eerste regel van de `try`, werd opgeslokt door de `catch` eronder, en zakte stilletjes terug naar "open de releasepagina in de browser". De automatische installatie heeft **voor niemand ooit gedraaid** — en omdat de fallback nette, plausibele werking vertoonde, zag het eruit als een ontwerpkeuze. Nu `token: updateToken()`, en de installer wordt met `/S` stil uitgevoerd (detached + unref) zodat de eigenaar niet alsnog door een setup-wizard moet klikken waar hij al toestemming voor gaf; NSIS herstart de app zelf. Dialoogtekst aangepast aan wat er nu echt gebeurt.
  **Vangnet tegen dezelfde klasse fouten**: de Electron main-process is ongetypeerde CommonJS die door geen enkele job ook maar geparst werd. Nieuwe `eslint.config.mjs` met `no-undef` + CI-job `desktop-lint` over `main.cjs`/`preload.cjs`/`updater.cjs`. **Bewezen dat het de bug vangt**: met de oude regel teruggezet meldt eslint `523:52 error 'token' is not defined`; hersteld is de run schoon. **NB: de stille `/S`-installatie is niet end-to-end gedraaid** — dat vergt een echte release-naar-release upgrade op Windows; de ReferenceError-fix en de lintcontrole zijn wél bewezen.

- [x] **U193 — licht met groen accent als standaarduiterlijk** · `pending`
  Standaard was donker + blauw. Nu licht + groen op drie plekken tegelijk, want ze moeten het eens zijn: de themastore (verse installatie), `$reset()`, en — makkelijk te vergeten — de kale `:root` in `tokens.css`. Die laatste schildert het **eerste frame**, vóór Vue gemount is en de opgeslagen keuze toepast; laat je die op donkerblauw staan, dan flitst elke start nog even het oude thema. De `:root`-groepering is dus verhuisd van de dark/blue-blokken naar de light/green-blokken; een expliciete `data-theme` wint sowieso op specificiteit, dus bestaande keuzes blijven werken. **Het gevoelige punt**: `loadSaved()` las `parsed.theme === 'light' ? 'light' : 'dark'` — die vorm dwingt álles wat niet 'light' is naar de standaard. Bij het omdraaien is dat nu `=== 'dark' ? 'dark' : 'light'`, zodat wie ooit donker koos dat ook houdt: een standaard veranderen mag nooit een keuze overschrijven. Daar staat een aparte test op ('keeps a previously chosen dark theme'). Geverifieerd in de draaiende console met lege localStorage: `data-theme=light`, `data-accent=green`, `--bg #f1f5f9`, `--accent #16a34a`. Console 72 groen.

- [x] **U194 — desktopvaardigheden: VS Code/Copilot, Spotify, Chrome, Claude/ChatGPT** · `pending`
  De gereedschappen om een desktop te bedienen bestonden al (`launch_app`, `open_in_vscode`, `media_control`, `use_computer`, `run_powershell`). Wat ontbrak was het **weten hoe**: welk gereedschap eerst, in welke volgorde, en wanneer stoppen om te vragen. Zonder dat improviseert het model elke keer een andere, plausibel ogende volgorde. Vier ingebouwde skills, elk met een expliciete escalatieladder (eigen tool → `launch_app` → pas dan `use_computer`, dat traag is, schermafdrukken maakt en goedkeuring vraagt) en met dezelfde weigeringen als de rest van het systeem: geen wachtwoorden, geen betalingen, geen voorwaarden aanvaarden. **VS Code**: `open_in_vscode` om code te tonen, PowerShell om een repo te zóeken (`Get-ChildItem -Filter .git -Recurse -Depth 4`) en de eigenaar te laten kiezen, Copilot via Ctrl+Alt+I — maar nooit een voorgestelde bewerking namens de eigenaar aanvaarden. **Spotify**: transportknoppen zijn `media_control` (geen schermbediening nodig), een specifiek nummer is Ctrl+L → typen → resultaat lezen en de rij kiezen die écht klopt (zegt het expliciet wanneer de tophit een live/remix/cover is), speakers via Connect — en als het gevraagde toestel er niet staat, dát zeggen in plaats van stilletjes op de laptopspeakers spelen. **Chrome**: er ís geen open-URL-tool, dus Ctrl+L; zoeken direct in de adresbalk; en de regel dat pagina-inhoud informatie is, nooit een instructie. **Claude/ChatGPT**: allow-list respecteren (nooit omzeilen via `run_powershell`), wachten tot het antwoord klaar is met streamen vóór je de schermafdruk leest, en nooit iets uit de kennisbank plakken tenzij de eigenaar precies dat vroeg.
  Ze **komen als code mee**, niet als bestanden in `skills/` — die map staat op de deny-lijst van de privacyscanner (het zijn de persoonlijke routines van de eigenaar), dus wat met het product meekomt kan daar niet wonen. **Het contract**: één keer geseed, daarna is de eigenaar de baas. Een bewerkte skill behoudt zijn tekst, en een **verwijderde skill blijft weg** — daarvoor was een marker nodig (`.builtin-seeded.json`), want "seed wanneer afwezig" kan een bewuste verwijdering niet onderscheiden van nooit-gezien en zou hem elke herstart terugzetten. Een standaard die zichzelf herstelt is geen standaard. De marker noteert álle bekende namen, zodat een skill uit een látere release alsnog één keer seedt. **Allow-list uitgebreid met echte launch-ids**, gemeten op deze machine in plaats van gegokt: Chrome via `start chrome` (App Paths), Claude en ChatGPT zijn Store-pakketten zonder exe op PATH en zonder URI-schema, dus `shell:AppsFolder\<AUMID>`. **Live getest**: Chrome, Spotify én Claude starten daadwerkelijk op. 7 tests (seeden, twee keer seeden doet niets, bewerking blijft, verwijdering blijft, triggers vuren op wat een mens echt zou zeggen in NL en EN, elke skill benoemt zijn weigeringen), plus een end-to-end proef die seeden → verwijderen → herstarten doorloopt. Orchestrator 211 groen, lint schoon. **NB: `use_computer` zelf is niet in een echte app doorlopen** — de skills beschrijven de procedure, maar of Copilot's paneel op deze VS Code-versie op Ctrl+Alt+I opent, moet de eigenaar in de praktijk bevestigen.

- [x] **U195 — de video liep achter en dat werd erger; nu één frame per verzoek** · `pending`
  Melding "enorme vertraging voor het beeld in de app verschijnt". U188 maakte de frames al 12x kleiner, en tóch bleef het traag — omdat het probleem niet de omvang was maar de **structuur**. Gemeten met de echte streamingcode over een link die de helft van de producentensnelheid aankan: de beeldleeftijd liep van 0,6 s naar 2,5 s en **bleef groeien**. Oorzaak: de MJPEG-lus produceert op een vaste 12 fps ongeacht of iemand kan volgen, en TCP laat nooit frames vallen — het stelt ze alleen uit. Elke seconde dat de producent sneller is dan de link, groeit de achterstand; zodra de buffers vol zijn, blijven ze vol en is de vertraging permanent. **Twee voor de hand liggende fixes gemeten en verworpen**: slimmer doseren (alleen de rest van het framebudget wachten) hielp niets (3,23 s vs 3,23 s), en een kleinere socketbuffer nauwelijks (2,58 s). Logisch achteraf: je kunt niet slim genoeg doseren als je erop staat élk frame te bezorgen over een link die dat niet aankan — je moet frames **overslaan**, en dat kan een doorlopende stream principieel niet, want wat geschreven is staat in de wachtrij. **De structurele oplossing**: één verzoek per frame. De console vraagt een frame, wacht tot het gedecodeerd is, en vraagt dan pas het volgende — er is nooit meer dan één frame onderweg, dus er kán geen wachtrij ontstaan, en het tempo stelt zich vanzelf in op wat de link aankan. Zelfde meetopstelling, zelfde krappe link: **0,23 s → 0,22 s, slechtst 0,28 s — vlak**. Ongeveer 10x sneller, en het loopt niet meer op. Nieuw `GET /robot/camera/frame.jpg` (JPEG, want de camera levert al JPEG en PNG hercoderen kost bytes die daarna over WiFi moeten; zelfde downscaling als de stream; `no-store`), brain-proxy met één gedeelde keep-alive-client (anders kost elk frame een TCP-handshake en verlies je de winst), en de console draait een lus met een plafond van ~15 fps zodat een snelle link de Pi niet leegtrekt voor frames die het oog niet uit elkaar houdt. De blob-URL wordt pas vrijgegeven ná het wisselen, anders wijst de `<img>` even naar een vrijgegeven blob en flikkert het beeld leeg. De MJPEG-stream blijft bestaan voor wie hem gebruikt. Robot-runtime 82 + 3 nieuwe tests, brain-suite 360 groen, console 72 groen, lint schoon. **Nagemeten op de echte stack** (vraag: "kan je reele test doen?"): de Pi was offline, dus niet over jouw WiFi — maar wel met de daadwerkelijke `robot_runtime`-routes (echte JPEG-encoding en echte `downscale_jpeg`), de echte brain-proxy, elk op een eigen uvicorn-poort over echte TCP-sockets, met camerabeeld-achtige ruis in plaats van het vlakke testplaatje van de fake adapter (dat comprimeert tot 5 KB — een honderdste van een echt frame, waar geen enkele link moeite mee heeft). Framegroottes kwamen exact uit op U188's echte meting: **695,7 KB ruw → 56,9 KB na downscaling**, dus 12 fps vraagt 683 KB/s terwijl de testlink 336 KB/s draagt (~5,9 fps). Resultaat: **stream 0,36 s → 5,47 s (slechtst 5,58 s), pollen 0,19 s → 0,20 s (slechtst 0,23 s)**. Op de echte stack is het gat dus nóg groter dan in de eerste opzet — de vertraging liep op tot ruim vijf seconden. Drie fouten zaten eerst in mijn eigen meetopstelling (adapter niet verbonden, dubbele `/robot`-prefix, onrealistisch klein testbeeld); die zijn gevonden doordat de eerste run nul frames opleverde in plaats van dat blind te vertrouwen. **Wat nog openstaat: de Pi over jouw WiFi** — de structurele winst (er kán geen wachtrij ontstaan) geldt hoe dan ook, maar de gevoelde verbetering bevestig jij na deploy.

- [x] **U196 — de camera laadde niet, en de Pi bleek maanden achter te lopen** · `pending`
  Melding "nog steeds issues met camera, laadt niet" op v2.0.16, met de robot **online** in de titelbalk. Eerst nagegaan of mijn eigen U195 de dader was: nee, die zit niet in v2.0.16. Toen live gemeten tegen de draaiende brain op poort 8020. Het oude PNG-frame gaf **1,4 MB**, de MJPEG-stream leverde **17 MB in 6 seconden** — er stroomde dus volop data, de stream was technisch in orde (geldige multipart-boundaries, geldige JPEG's). Eén frame gedecodeerd en toen viel alles op zijn plaats: **1280x720, 487 KB per frame**. U188's downscaling (640x360, ~56 KB) draaide daar helemaal niet. **Oorzaak: de Pi wordt apart uitgerold.** De desktop-app werkt zichzelf bij, maar `robot-runtime` op de Pi is een handmatige `git clone` + start (infra/two-host-bringup.md) — dus U188 heeft de robot nooit bereikt, maanden nadat het gebouwd was. Bij 12 fps vraagt dat 5,8 MB/s (47 Mbit/s) over de WiFi van een Pi: dát is waarom video al die tijd traag bleef, en waarom de `<img>` uiteindelijk afhaakte.
  **Het gevaar dat dit blootlegde**: U195 laat de console `/robot/camera/frame.jpg` opvragen — een route die op deze Pi **niet bestaat**. Zonder meer zou de "fix" een 404 hebben opgeleverd en precies de melding "No camera feed" hebben veroorzaakt die hij moest oplossen: een oplossing die kapotmaakt wat ze repareert. Daarom valt de brain-proxy nu terug: hij probeert de nieuwe route één keer, onthoudt het antwoord, en spreekt bij een 404 een oude robot aan via zijn MJPEG-stream. Die stream wordt in de brain **continu leeggetrokken met behoud van alleen het laatste frame** — juist dóór niet te bufferen blijft het beeld actueel, en er kan op geen van beide hops een wachtrij ontstaan. Het frame wordt één keer per ontvangen frame verkleind (niet per opvraging, want de console vraagt vaker dan de robot levert): **696 KB → 57 KB** naar de console. Geverifieerd tegen een nagebouwde oude Pi die álleen de legacy-stream heeft: eerste poll 200 met geldige JPEG, probe zet zichzelf correct op "oud", en **12 opvragingen leveren 12 verschillende frames** (een vastgevroren cache zou er 1 geven), mediaan 0 ms. Achtergrondlezer stopt netjes bij shutdown (anders wacht de app op een verbinding die uit zichzelf nooit eindigt) en slikt `CancelledError` zonder traceback. 4 nieuwe tests plus 11 groen in `test_robot_api`, brain-suite 279 groen, lint schoon.
  **Wat dit NIET oplost en jij wel moet doen**: de Pi stuurt nog steeds 487 KB-frames over WiFi. De brain maakt ze klein ná de trage hop, dus de bandbreedte tussen robot en laptop blijft het knelpunt. Op de Pi `git pull` + `robot-runtime` herstarten haalt U188 (downscaling aan de bron, 12x minder data) én U195 (`/camera/frame.jpg`) binnen. **NB: de brain-side fallback is getest tegen een nagebouwde oude Pi, niet tegen jouw echte robot** — de Pi was tijdens het bouwen bereikbaar via de draaiende brain, maar ik heb de nieuwe code daar niet op kunnen draaien.

- [x] **U197 — op de echte robot getest, en de update installeert zichzelf** · `pending`
  **Eerst de camera op de echte hardware** (vraag: "test with real robot"). De Pi bleek te draaien op `reachy-mini.local:8001`, niet `reachy.local` — daarom faalde mijn eerdere bereikbaarheidstest. Resultaat, en het bevestigt de diagnose van U196 op echte hardware: `GET /robot/camera/frame.jpg` → **HTTP 404**. De nieuwe console zou dus zonder de fallback van U196 letterlijk stukgelopen zijn op "No camera feed" — precies de melding die hij moest oplossen. Metingen over de echte WiFi: de robot levert **65 frames in 9,2 s = 7,0 fps bij 474 KB gemiddeld = 3,34 MB/s (27 Mbit/s)**; de link zit dus vol en haalt de beoogde 12 fps niet. Met de nieuwe proxy ervoor: eerste poll HTTP 200 in 734 ms (opstarten van de achtergrondlezer), daarna **38 KB per frame op 640x360**, fallback correct actief, **15 verschillende frames uit 20 polls** en een latency van **mediaan 0 ms / max 16 ms** naar de console. De console krijgt dus 12x kleinere frames en wacht nergens meer op. **Wat dit niet oplost blijft staan**: de robot→laptop-hop draagt nog altijd 474 KB per frame; alleen een `git pull` op de Pi haalt U188's downscaling naar de bron.
  **Daarna de update-flow** (vraag: "when newer version available notify user, and perform update autonomously", met een screenshot van een balk in de trant van "Versie X staat klaar om te installeren"). De oude flow onderbrak met een modaal venster op het moment dat er een update *bestond*, en begon **daarna** pas te downloaden — dus de eigenaar zat te wachten op iets waar hij al ja tegen had gezegd. Nu andersom: de download loopt **stil op de achtergrond** zodra er een nieuwere versie is, en pas wanneer de installer op schijf staat verschijnt er een rustige balk onder de titelbalk — één klik, klaar in seconden. Nieuwe IPC-brug (`onUpdateReady`, `installUpdate`, `dismissUpdate`), NSIS draait met `/S` en herstart de app zelf. **"Later" betekent later, niet nooit**: het verbergt de balk voor deze sessie en schrijft niets weg, zodat de volgende start hem opnieuw aanbiedt zónder opnieuw te downloaden — permanent overslaan blijft aan de About-dialoog. Op macOS/Linux is er geen stille installer voor een .dmg/.AppImage, dus daar blijft het eerlijk bij "open de releasepagina". Een mislukte achtergronddownload is stil van opzet: die mag de eigenaar niet onderbreken, de volgende controle probeert het opnieuw. 6 componenttests (verschijnt niet zomaar, noemt de versie, installeert bij klik, **toont waaróm het mislukte in plaats van stil niets te doen en laat de knop bruikbaar**, "Later" verbergt zonder over te slaan, en blijft stil in een gewone browser waar niets een installer kan klaarzetten). Console 78 groen, eslint schoon.
  **Twee stille fouten onderweg gevangen**: de eerste template-invoeging in `App.vue` mislukte zonder foutmelding — de import stond er wel, het gebruik niet, en een ongebruikt component wordt weggesnoeid, dus de bundel-hashes bleven identiek aan de vorige build. Opgemerkt door dat op te vallen in plaats van de groene build te geloven. En in mijn eerste versie beloofde de comment bij "Later" iets anders dan de code deed (die sloeg de versie permanent over).

- [x] **U198 — "Robot: offline" verzweeg wat de app allang wist** · `pending`
  Melding "blijft zeggen dat de robot niet verbonden is terwijl hij aanstaat, en er is ook geen video". Live nagemeten en de keten uit elkaar getrokken: **`reachy-mini.local` loste helemaal niet meer op** ("Host is onbekend") — terwijl diezelfde naam eerder in dezelfde sessie nog op 2 ms pingde. Daarna het hele LAN afgezocht: **geen enkel adres luisterde op 8001**. Twee onafhankelijke oorzaken dus, allebei onzichtbaar voor de eigenaar. (1) `.local` gaat via mDNS, dat op Windows regelmatig wegvalt en er precies uitziet als een dode robot. (2) `robot-runtime` wordt volgens de bring-up met de hand gestart en sterft met de shell — na een herstart van de Pi staat de robot áán terwijl er niets luistert. "Robot aan" en "robot bereikbaar" zijn twee verschillende dingen, en de app toonde er maar één.
  **De kern van de fix is niet code maar eerlijkheid**: de brain wist de oorzaak allang — de exception onderscheidt naamresolutie, geweigerde verbinding en time-out perfect — en gooide die weg om er "offline" van te maken, het enige wat de eigenaar zelf al zag. Nu vertaalt `_diagnose()` de fout naar de handeling die erbij hoort: *"de naam kon niet worden herleid — zet ROBOT_RUNTIME_URL op het IP-adres"*, *"de verbinding werd geweigerd — robot-runtime draait niet op de robot"*, of *"antwoordde niet op tijd — ander netwerk of WiFi weg"*, altijd mét de host die geprobeerd werd. Die zin komt mee in de 503 en staat nu in het Robot State-paneel. **De oorzaak zelf ook weggenomen**: `infra/robot-runtime.service` (systemd, `Restart=always`, wacht op netwerk én geluid want camera en audio zijn er niet op het moment dat het netwerk er is — te vroeg starten faalt op een manier die op een kapotte installatie lijkt) plus `CAMERA_STREAM_WIDTH=640` in de unit, zodat U188's downscaling meteen goed staat waar het telt: aan de bron, vóór de trage hop. Bring-up-doc uitgebreid met de unit, met de raad om een IP te pinnen in plaats van de `.local`-naam (met DHCP-reservering), en met het punt dat de desktop-app zichzelf bijwerkt maar **de Pi niet** — inclusief de drie commando's daarvoor. 3 nieuwe tests (elke oorzaak krijgt zijn eigen advies, de host wordt altijd genoemd, en de 503 draagt de reden plus de geprobeerde URL). Brain 281 groen, console 78 groen, lint schoon.
  **NB: niet op de robot zelf geverifieerd** — de Pi was tijdens dit werk onbereikbaar, wat nu juist de aanleiding was. De diagnosetekst is getest tegen de echte exceptions, maar of de systemd-unit op jouw Pi zonder aanpassing start (pad naar `uv`, gebruikersnaam) moet daar blijken.

- [x] **U199 — het robotadres instelbaar maken, want ik gaf advies zonder knop** · `pending`
  De diagnose uit U198 werkte meteen ("the name 'reachy-mini.local:8001' could not be resolved... set ROBOT_RUNTIME_URL to the robot's IP address"), maar daarmee viel mijn eigen gat op: dat *kon* de eigenaar helemaal niet. `ROBOT_RUNTIME_URL` stond alleen in een `.env` binnen de datamap van de app. Iemand vertellen iets te doen waar geen knop voor bestaat is slechter dan niets zeggen. Nu `GET`/`POST /robot/address`: het adres wordt weggeschreven naar de `.env` én **meteen toegepast** (`_robot._base_url`), dus geen herstart nodig om een adres te próberen; de probe of de robot `frame.jpg` kent wordt gewist en de camera-lezer gestopt, want een ander adres kan een andere versie zijn. De POST **test het adres direct** en meldt eerlijk terug: opgeslagen is niet hetzelfde als bereikbaar, en juist dat wil je weten. Het invoerveld staat in het foutkader zelf, voorgevuld met het huidige adres — niet weggestopt in instellingen, want daar kijk je niet als er net iets stuk is. Een ontbrekend `http://` wordt aangevuld (mensen typen `192.168.0.42:8001`), een pad wordt geweigerd (dat sloopt stilletjes elke route erbovenop). 4 tests, brain 285 groen, console 78 groen, lint schoon. Visueel bevestigd in de draaiende console met een nagebootste onbereikbare robot.
  **Diagnose van de melding zelf** ("blijft zeggen niet verbonden"): het hele subnet afgezocht — 254 adressen, 9 apparaten, **geen enkele met een Raspberry Pi-MAC en niets dat op 8001 luistert**. De laptop hangt bovendien op **Ethernet** (192.168.0.10) terwijl de Reachy draadloos is. De robot is dus simpelweg niet op dit netwerk; de app vertelt nu de waarheid in plaats van "offline". Eerder in dezelfde sessie was `reachy-mini.local` nog wél bereikbaar (2 ms, health OK, camera gaf frames) — dus dit is weggevallen, geen configuratiefout.

- [x] **U200 — de robot zelf opzoeken; hij stond al die tijd op 192.168.0.42** · `pending`
  "Still not working, restarted robot as well." U199 gaf een invoerveld voor het robotadres en liet de eigenaar dat adres vervolgens zélf uitzoeken — op een thuisnetwerk betekent dat een routerpagina of een poortscanner. Je kunt geen adres intypen dat je niet kent. De brain staat op hetzelfde netwerk en kan gewoon kíjken, dus dat doet hij nu: `GET /robot/discover` klopt op poort 8001 van elke host in het eigen /24 en vraagt `/health` aan wat opendoet.
  **En dat vond de robot meteen.** Mijn eerdere ARP- en ping-sweeps concludeerden "geen enkel apparaat op 8001" — **fout**, en op een leerzame manier: een Pi hoeft niet op ICMP te antwoorden, dus een ping-sweep ziet hem niet, en ARP toont alleen wie je recent hebt aangesproken. De poortscan vond hem in één keer op **`192.168.0.42`**, geverifieerd als echte hardware: `/health` online, batterij 100%, `/robot/status` compleet, en `/robot/camera/frame` gaf een PNG van 1,2 MB. De `.local`-naam bleef ondertussen onoplosbaar — het probleem was dus uitsluitend naamresolutie, niet het netwerk en niet de robot. Ook nuttig gebleken: de WiFi-adapter van de laptop had `169.254.244.48`, een APIPA-adres, oftewel niet verbonden; alleen Ethernet was actief.
  **Van 48 s naar 1,4 s.** De eerste versie bouwde per adres een HTTP-client en deed er 48 seconden over een /24 — onbruikbaar voor een knop die je indrukt terwijl je naar een foutmelding staart. Nu twee passages: een kale TCP-connect (die de meeste hosts in milliseconden afhandelt) en pas daarna HTTP op het handjevol met een open poort. Bewust begrensd tot het eigen /24, 1 s per host. Adapters met `169.254.x` en loopback worden overgeslagen — daar valt niets te vinden en het kost alleen seconden. Wat opendoet maar geen `robot`-sleutel in `/health` heeft, wordt genegeerd: een open poort is nog geen robot, en een printer aanbieden als robot stuurt de eigenaar achter een instelling aan die nooit kan werken. Gevonden robots verschijnen als klikbare knoppen die het adres meteen opslaan en testen. 4 tests, brain 289 groen, console 78 groen, lint schoon.
  **Testles onderweg**: mijn eerste testopzet startte uvicorn in de event-loop van de test terwijl `TestClient` de endpoint op zijn eigen loop draait — de stub stond dus bevroren en de test faalde om een reden die niets met de code te maken had. Vervangen door een gewone `HTTPServer` in een thread. En de eerste versie testte de interface-filtering via `getaddrinfo`-mocking, waardoor loopback moest worden toegelaten in code die dat juist hoort te weigeren; nu is de scanlijst de naad en heeft de filtering een eigen test.

- [x] **U201 — de update installeerde wél, maar de app kwam nooit terug** · `pending`
  Melding: "na klikken op installeren sluit hij, maar er gebeurt niets — geen download, geen installatie." **Bewijs eerst gezocht in plaats van de melding te geloven**: in `%TEMP%` stonden zeven gedownloade installers (elk 78,7 MB, netjes één per versie) en `AURA.exe` op schijf was al **v2.0.21** — de versie die de banner aanbood. De download én de installatie waren dus allebei gelukt. Wat níét gebeurde: terugkomen. De app sloot, installeerde stil op de achtergrond, en liet de eigenaar achter met een leeg scherm — vanuit zijn kant niet te onderscheiden van "er gebeurde niets". Mijn eigen comment uit U192/U197 beweerde dat NSIS met `/S` de app zelf herstart; **dat klopt niet**, en het stond er als vaststaand feit terwijl ik het nooit had kunnen testen.
  Nu stuurt een klein `.cmd`-script de hele reeks aan, omdat elke stap de vorige nodig heeft: wachten tot dit proces weg is (een installer kan geen bestanden vervangen die nog in gebruik zijn), stil installeren, dán de nieuwe build starten. Plus een log in userData, zodat een mislukte update terug te lézen is in plaats van te raden. Ontbreekt de gedownloade installer (temp wordt geleegd, schijf vol), dan zegt de banner dat — beter dan niets starten en afsluiten.
  **Drie keer misgegaan voordat het werkte, elke keer zichtbaar gemaakt door het script écht uit te voeren met nep-installer en nep-app in plaats van de code te lezen**: (1) de installer direct aanroepen geeft bij een script-doel de controle nooit terug — de app installeerde en kwam dus nooit bij de herstart-regel; (2) `start /wait` opent een consolevenster en liep in de test volledig vast; `call` is de juiste primitief: geeft altijd controle terug, zonder venster; (3) `echo ... exit=%errorlevel%>> log` liet de regel stil verdwijnen, want cmd leest `0>>` als een stream-omleiding in plaats van tekst — vandaar de blokhaken om de waarde. Eindmeting van de volledige keten: installer draait met `/S`, `exit=[0]` in het log, app herstart. Ook de knoptekst is nu eerlijk: "AURA sluit af en komt terug…" in plaats van "Bezig…", zodat het afsluiten geen verrassing is. Console 78 groen, eslint schoon.

- [x] **U202 — mijn eigen U191 legde de assistent stil; de echo verborg het** · `pending`
  Melding: "robot reageert niet meer op het wake word, doet de microfoon het nog? en in de chat echoot hij mijn vraag terug." Die `[echo]`-prefix was de verklikker. Live nagetrokken op de draaiende brain: `/orchestrator/config/llm` zei keurig `provider=openai, model=gpt-4o-mini, key set` — dus de configuratie klópte, en toch kwam er echo uit. Een directe POST naar `/orchestrator/turn` gaf **HTTP 500**, en de ingebouwde logviewer de echte oorzaak: **`404 – This is not a chat model and thus not supported in the v1/chat/completions endpoint`**.
  **Dat is een regressie van mijzelf.** In U191 beperkte ik de rol "Conversation" tot realtime-modellen, in de aanname dat die rol de spraakloop voedde. Fout: `pipeline.py:500` gebruikt `model_for_role("chat")` voor **ronde één van élke beurt** — getypte berichten incluis, via chat-completions. Mijn eigen UI bood daar dus uitsluitend modellen aan die die rol per definitie niet kan draaien; de eigenaar koos `gpt-realtime-2.1` en sindsdien faalde iedere beurt. Het wake word "deed het niet meer" om dezelfde reden: elke beurt liep dood. Nu krijgt Conversation weer chat-modellen, en staat het spraakmodel op een eigen regel (`REALTIME_MODEL`, dat altijd al bestond en apart wordt gelezen door de realtime-loop). De backend **weigert** bovendien een realtime-model voor CHAT_MODEL/AGENT_MODEL met een 422 die uitlegt waar het dan wél hoort — een UI-keuze mag geen onherstelbare toestand kunnen wegschrijven, en een geweigerde waarde wordt niet half toegepast (getest).
  **De diepere fout was de camouflage.** `_call_orchestrator` ving élke exception op, logde een warning die niemand leest, en gaf `[echo] <jouw vraag>` terug. Daardoor zag een kapotte configuratie eruit als een werkende assistent met een papegaai-tic, en zat de echte reden in een logbestand. Een assistent die niet kan antwoorden hoort dat te zeggen, niet er een na te doen. Nu vertaalt `_explain_failure()` de vier gevallen die de eigenaar zelf kan verhelpen — verkeerd modeltype, geweigerde API-sleutel, quota/rate limit, onbekend model — naar één zin met de plek waar je het repareert, en al het overige naar een eerlijke foutmelding. **Een bestaande test moest mee veranderen**: `test_text_turn_echo_fallback` legde precies het oude gedrag vast (de vraag moest in het antwoord zitten). Die is niet "gefixt" maar omgedraaid, met de reden erbij, en er staat nu ook een test op dat een mislukte beurt de vraag **nooit** teruggeeft. Brain 297, orchestrator 211, conversation-runtime 22, console 78 groen; lint schoon.
  **Wat jij moet doen na de update**: zet in Settings → Model per task type de rol **Conversation** terug op een chat-model (bijv. `gpt-4o-mini` of `gpt-5.4`) en zet `gpt-realtime-2.1` op de nieuwe regel **Voice**. Zolang CHAT_MODEL op een realtime-model staat, blijft elke beurt falen — het verschil is dat de app nu zégt waarom.

- [x] **U203 — voice standaard (mét tools), realtime per persona voor "meebabbelen"** · `pending`
  Vraag na U202: "is voice niet beter voor realistische conversatie, dus standaard voice?" — met als keuze "default voice, on-demand naar realtime, of in presentatiemodus waarin de robot meebabbelt". Eerst het onderscheid rechtgezet dat door elkaar liep: `VOICE_MODE` (luistert de robot: off/wake_word) staat los van `VOICE_ENGINE` (hóé een gesproken beurt verwerkt wordt: pipeline/realtime). De cruciale bevinding uit de code: `realtime_session.py` heeft **geen enkele tooltoegang** — geen skills, geen Spotify, geen geheugen, geen herkenning. Realtime is vloeiender speech-to-speech, maar een prater die niets kan dóén. Daarom nooit als globale standaard: dat zou precies breken wat de eigenaar net had gevraagd (Spotify, desktop-skills).
  De on-demand switch bestond al (Settings → VOICE_ENGINE, U132). Wat ontbrak was de kóppeling aan de persona. Nu draagt `CharacterPersona` een veld `voice_engine` ("" = erf de globale; anders pipeline/realtime), en resolvet de voice-loop de engine **per beurt** via de actieve character (`self._manager.character`), met de globale `VOICE_ENGINE` als terugval — live gelezen, dus van persona wisselen werkt zonder herstart. De meegeleverde **workshop_coach** (de presentatie-/demopersona) staat op `realtime`: die is bedoeld om mee te babbelen en geeft tools bewust op. Alle andere persona's en de standaard blijven pipeline, dus voice-met-skills. Persona-editor kreeg een keuze "Conversation style" (Default / Voice + skills / Realtime chat) met een expliciete waarschuwing zodra realtime gekozen wordt dat die persona tijdens het praten geen Spotify/skills/geheugen heeft. Ongeldige waarden worden geweigerd in plaats van weggeschreven — een UI-keuze mag geen toestand maken die elke beurt stilletjes de tools uitzet. 7 backendtests (standaard = pipeline, globale env schakelt alles, character overschrijft de globale in beide richtingen, lege waarde erft, de meegeleverde presentatiepersona staat op realtime, en een onzinwaarde wordt genegeerd). Brain 304, console 78 groen; lint schoon.
  **Zo gebruik je het**: dagelijks praat de robot via voice mét skills (niets te doen). Wil je puur natuurlijk kletsen of een presentatie waarin hij meebabbelt, kies dan de persona **Workshop Coach** (of zet `Conversation style` van een eigen persona op Realtime). De teller `~$` in Robot State laat zien dat realtime per beurt geld kost. **Nog open, eerlijk**: realtime bewijst zich pas op de echte robot met werkende echo-onderdrukking; full-duplex in-de-rede-vallen blijft uit tot de AEC stabiel is (bekend uit eerder werk). En het "flexibel scenario" dat je noemde (een script dat de robot in presentatiemodus volgt) heb ik nog niet gebouwd — dit legt de basis (een presentatiepersona op realtime); een scenario-stap is een volgende unit als je die wil.

- [x] **U204 — avatar per persoon (foto bij aanleren, of zelf kiezen); presentatievoorstel** · `pending`
  Twee dingen uit één vraag. **(1) Avatar.** `Person` krijgt een veld `avatar` — een `data:image/jpeg;base64,`-URI die in het versleutelde bundel van de persoon leeft, net als de facts (leeg → de console valt terug op initialen, dus oude data laadt onveranderd). Eén helper `aura_brain/avatar.py` maakt van elke bron (cameraframe of upload) een klein vierkant: center-crop, 128px, JPEG q82 (<30 KB), en her-encodeert álles naar JPEG zodat een PNG/webp-upload evengoed klein wordt en het formaat vastligt. Bij **face aanleren** wordt automatisch de eerste frame-mét-gezicht de avatar — maar alleen als de persoon er nog geen had (een bewust gekozen avatar wordt nooit overschreven), en best-effort: een mislukte avatar mag het aanleren niet doen falen. **Wijzigen** kan op drie manieren: `POST /recognition/people/{id}/avatar/capture` (nieuwe foto via de robotcamera — die overschrijft wél, want je vroeg erom), `PUT /knowledge/people/{id}/avatar {image}` (upload, her-geëncodeerd) en `{clear:true}` (terug naar initialen). In de console tonen de personenlijst en de hero nu de avatar met terugval op initialen, plus een camera-knopje op de hero met een menu Take a photo / Upload image / Remove. Ongeldige of te grote input wordt geweigerd (422) vóór opslag — een kapotte avatar hoort nooit in het profiel. Getest: 10 helper-tests (klein vierkant, center-crop van een 6:1-beeld, junk/te-groot geweigerd, data-URI genormaliseerd naar JPEG, slechte URI's afgewezen) en 2 API-tests (upload+clear rondreis, junk 422 en onbekende persoon 404). Visueel bevestigd in de console: persoon mét avatar toont de foto, persoon zonder toont de initiaal. Brain+schemas 442 groen, console 78 groen, lint schoon.
  **(2) Presentatievoorstel.** Je "flexibel scenario" (robot presenteert mee, met cues waarop hij spreekt of mag invallen) uitgewerkt tot een voorstel in `docs/presentation-mode-proposal.md`, gegrond op wat er al is: er bestaat een `PresentationManager` die een YAML-script laadt en per slide een verbatim `speech_cue` + gebaar afspeelt — lineair en scripted. Het voorstel breidt dat uit naar een **beat-model** met modes (`speak` verbatim / `improvise` vrij op een topic / `chime_in` gewapend, mag invallen als hij het topic hoort / `silent`) en triggers (handmatig "next" / `slide:N` / gesproken keyword). Voor de **slides** drie routes met afweging: (A) PowerPoint houden en beats met de hand doorklikken — minste werk, geen integratie met de slide zelf; (B) HTML-deck in de console — volledige integratie, maar je verlaat PowerPoint; (C) je bestaande PPTX naar beelden exporteren — inhoud hergebruiken mét `slide:N`-triggers. **Integratiepunten**: subtitles (de realtime-transcriptdeltas stromen al als `TranscriptUpdated` → grote presenter-view), camera (bestaat), en robot-audio via de laptopspeakers (de bytes zitten al in de brain vóór ze naar de robot gaan → te teeën naar de console). Gefaseerd plan (beats+handmatig → subtitles/camera/audio → slide-sync → chime_in) met eerlijke grenzen: `chime_in` hangt op stabiele AEC (nog niet), en realtime heeft geen tooltoegang (U203) dus een beat die live data nodig heeft moet `pipeline` zijn. **Voor jou drie beslissingen** (slide-route A/B/C, keyword-triggers vanaf dag één of niet, bestaande PPTX om mee te testen) — het voorstel wacht daarop; ik heb bewust nog niets van de presentatie zelf gebouwd.

- [x] **U205 — co-presenter: beat-model, runner, en de testpresentatie** · `pending`
  Je drie beslissingen (PowerPoint houden, all-in inclusief keyword-triggers, testpresentatie rond de titel uit de screenshot) omgezet in een geteste kern plus een draaiende testpresentatie. **Het beat-model** (`shared_schemas/presentation`): naast het bestaande slide→verbatim-script nu een `Scenario` van `Beat`s, elk met een **mode** (`speak` verbatim / `improvise` vrij op een topic / `chime_in` gewapend, valt in op een keyword / `silent`) en een **trigger** (`manual` / `slide:N` / `keyword:woord`), met validatie die de combinaties bewaakt (speak heeft tekst nodig, improvise/chime_in een topic, chime_in moét een keyword-trigger hebben, dubbele beat-id's geweigerd). **De runner** (`orchestrator/scenario_runner.py`) is bewust dun en dependency-injected: `next()` vuurt het volgende handmatige beat, `on_slide(n)` de slide-gebonden beats, `on_speech(text)` de gewapende keyword-beats (case-insensitive substring, `once`-guard zodat een herhaald topic hooguit één opmerking krijgt); elke mode wordt uitgevoerd via ingespoten `speak`/`generate`/`gesture`, en een mislukt beat (LLM plat) legt de talk niet stil. **De PowerPoint-watcher** (`aura_brain/pptx_watcher.py`, Windows + `pywin32`, nieuwe optionele extra `presentation`) pollt `SlideShowWindows(1).View.Slide.SlideIndex` — geen COM-add-in nodig, robuust tegen starten/stoppen van de show — en degradeert overal elders netjes naar "geen slides" zodat handmatige en keyword-triggers blijven werken. **De testpresentatie**: `docs/demo/robot-junior-dev.pptx` (7 slides, met python-pptx gegenereerd via een meegecommit script) + `robot-junior-dev.scenario.yaml` dat **alle vier de modes en alle drie de trigger-soorten** gebruikt, afgestemd op jouw talk (intro spreekt+zwaait op slide 1, valt in op "Java" en "agents", improviseert de these op slide 4, zwijgt bij de ongemakkelijke vraag op slide 6, sluit handmatig af). Getest: 5 modeltests, 7 runnertests, watcher-degradatie, en een **dry-run van de échte scenario-file** die de hele presentatie door de runner speelt en bevestigt dat elk beat op de juiste trigger precies één keer vuurt. shared-schemas 131, orchestrator 220, brain 317 groen; lint schoon.
  **Bewust NIET in deze unit, want niet zonder hardware te verifiëren** (staat ook in `docs/demo/README.md`): de API-endpoints om een scenario live te laden/sturen, het voeden van jouw gesproken tekst in `on_speech`, het inhaken van de PowerPoint-watcher op een lopende talk, en de **presenter-view** in de console (grote subtitles, next-knop, slide- en camera-indicator). Die vormen samen "Fase 2" en heb ik niet half-af willen pushen als "werkt". **NB ook**: keyword-invallen terwijl jíj praat hangt op stabiele echo-onderdrukking (nog niet), en `improvise` draait op realtime zonder tools (U203) — een beat met een live-lookup moet `engine: pipeline`. Zeg maar of ik Fase 2 (de presenter-view + live bedrading) als volgende unit oppak.

- [x] **U206 — presentatiemodus Fase 2: live bedrading + presenter-view** · `pending`
  De runner uit U205 nu écht aangesloten en bestuurbaar. **Backend** (`aura_brain/presentation_api.py`): één actieve sessie, met de `ScenarioRunner` bedraad aan de echte robot (`speak`/`execute_motion`), de LLM (voor `improvise`/`chime_in` — één completion zonder tools, zodat een beat niet midden in de talk in tool-calls verdwaalt) en de event-bus. Endpoints: `POST /presentation/scenario` (laadt YAML, valideert, start meteen de PowerPoint-watcher als die beschikbaar is), `POST /presentation/next` (handmatig beat), `POST /presentation/speech` (presenter-tekst → keyword-beats), `GET /presentation/status`, `DELETE /presentation/scenario`. **De PowerPoint-watcher** (U205) wordt bij load gestart en voedt `slide:N`-beats; **de voice-loop** geeft elke plausibele presenter-zin door aan de actieve presentatie vóór de wake-word-gate (want de robot valt in op je onderwerp, niet op aangesproken worden) — die feed verbruikt de beurt nooit. Nieuw event `PresentationBeatFired` (geregistreerd + broadcastbaar) draagt de gesproken zin naar de console als subtitle. **Presenter-view** (console, 🖥-icoon in de titelbalk): een volledig-scherm stage met een grote subtitle die zich vult uit de beat-events, de huidige slide, PowerPoint-status (linked/manual), de gewapende keywords, een camera-thumbnail (dezelfde één-frame-per-verzoek-lus als U195, zodat ook hier niets achterloopt), en een "Next beat"-knop met voortgang; een setup-scherm om het scenario te plakken en te starten. **Getest**: 7 API-tests (status inactief/actief, load meldt beats+keywords, slechte YAML 422 zonder sessie, next vuurt handmatige beats en meldt done, speech vuurt een keyword-beat én publiceert een subtitle op de bus, 409 vóór load, clear beëindigt). Eén echte vangst onderweg: `PresentationBeatFired` viel stil omdat `BaseEvent` een `session_id` vereist — de `_emit` slikte de ValidationError, opgemerkt door direct te debuggen i.p.v. het lege resultaat te vertrouwen. Visueel bevestigd in de draaiende console met een nagebootste backend: presenter opent, scenario start, een geïnjecteerd beat-event vult de subtitle, keywords/slide/next-knop kloppen. shared-schemas 131, brain 324, console 78 groen; lint schoon.
  **Zo draai je het** (staat ook in `docs/demo/README.md`): PowerPoint-show starten (F5), 🖥-icoon klikken, scenario-YAML plakken (bv. `robot-junior-dev.scenario.yaml`), Start. Slides doorklikken → `slide:N`-beats; een keyword zeggen → chime-in; Next beat voor de handmatige. **Eerlijke grenzen**: keyword-beats komen van wat de robotmic hoort terwijl jíj praat, dus ze hangen op echo-onderdrukking die nog niet stabiel is (de robot kan af en toe op zijn eigen stem reageren); `improvise` gebruikt de LLM voor tekst zonder tools. **NB: de volledige keten (echte robot + echte PowerPoint end-to-end) is niet op de hardware geverifieerd** — API, runner, watcher-degradatie en presenter-view zijn elk apart getest (fakes / preview / dry-run), maar de live-run op de echte stack moet jij bevestigen.

- [x] **U207 — scenario's bouwen in de app en opslaan (geen YAML meer plakken)** · `pending`
  Op je vraag "kunnen we een intuïtieve interface voorzien om scenario-YAML te maken?": ja. **Opslaan/laden** (`aura_brain/scenario_store.py`): één YAML-bestand per scenario in `SCENARIOS_DIR` (desktop → userData, dus een update wist ze niet; dev → `./scenarios`, gitignored want het is jouw talk-inhoud). CRUD-endpoints onder `/presentation/scenarios` (list/get/put/delete); een bestand wordt bij lezen tegen het `Scenario`-model gevalideerd zodat een kapot handmatig bestand een fout geeft i.p.v. een stukke presentatie, en één kapot bestand verbergt de rest niet. De endpoints accepteren nu zowel `{yaml}` (power users) als `{scenario:{…}}` (de bouwer), en `GET` geeft de gestructureerde vorm mee zodat de bouwer geen YAML-parser in de browser nodig heeft. **De bouwer-UI** (`ScenarioBuilder.vue`, met een Build/YAML-schakelaar in de presenter): per beat een kaart met mode-keuze (Speak/Improvise/Chime in/Silent), een leesbare trigger-bouwer ("When: I press Next / a slide shows / I say a word"), de juiste velden per mode (tekst voor speak, topic+guardrails voor improvise/chime_in), gebaar en engine; beats toevoegen/verwijderen/verschuiven; opslaan onder een naam en de opgeslagen scenario's als klikbare chips om te laden of te wissen. **Eén echte bug gevangen tijdens visuele verificatie**: chime_in dwingt een keyword-trigger af, maar het keyword-veld verscheen pas ná een extra actie omdat de mode-wissel de trigger niet bijwerkte — het scenario ging dan met een leeg `keyword:` weg. Nu werkt de mode-wissel meteen door; opnieuw geverifieerd in de draaiende console: chime_in kiezen toont meteen het keyword-veld, en het gestructureerde scenario (`keyword:agents`, topic ingevuld) gaat correct naar de backend. Brain 15 relevante tests (store-rondreis, slugify, ongeldig scenario nooit bewaard, kapot bestand verbergt de rest niet, save/list/load/delete via de API, 422 op ongeldig), console 78 groen, lint schoon.

- [x] **U208 — `improvise` volwaardig: mét tools (live data) via de pipeline** · `pending`
  Je vroeg de grens "improvise gebruikt de LLM zonder tools" weg te maken. Nu routeert een beat met `engine: pipeline` door de **volledige agentic loop** (dezelfde tools als een gewone beurt: agenda, muziek, opzoekingen) i.p.v. één kale LLM-completion — zodat een presentatiemoment live data kan ophalen en uitspreken. De valkuil was dubbel spreken: `pipeline.orchestrate` publiceert normaal `ResponseDrafted`, dat automatisch wordt uitgesproken. Daarom een minimale, schone toevoeging: `orchestrate(..., announce=False)` draait de loop maar publiceert niets, zodat de **runner** de tekst één keer uitspreekt (subtitle én robot blijven in sync). Een lege/andere engine blijft de snelle LLM-weg zonder tools. In de bouwer staat de keuze al als "Engine: default / with tools" bij improvise- en chime_in-beats. Getest: pipeline-beat gaat door `orchestrate` met `announce=False` en de runner spreekt het resultaat; default-engine gebruikt de LLM en raakt de pipeline niet; en op pipeline-niveau een test dat `announce=False` wél een reply teruggeeft maar géén `ResponseDrafted` publiceert. Orchestrator 221, brain 334 groen; lint schoon.
  **NB**: nog niet op de echte robot met echte tools tijdens een presentatie gedraaid — de routering en de niet-dubbel-spreken-garantie zijn bewezen met tests, de gevoelde werking (tool-latency midden in een talk) bevestig jij. Voor een strak getimede demo blijft `speak` met vooraf ingevulde data het veiligst; `improvise: pipeline` is voor de momenten waar je juist iets levends wil.

- [x] **U209 — robot-audio via de laptopspeakers + robuuste keyword-mic** · `pending`
  De twee toevoegingen die je vroeg, allebei in de presenter via de browser. **Laptop-audio**: een toggle die elke nieuwe gesproken regel via de laptopspeakers voorleest (`speechSynthesis`) — handig in een zaal waar de kleine robotspeaker niet volstaat. Het is de laptopstem, niet de exacte robot-audio, maar hoorbaar zonder backend-audioroutering. **Robuuste keyword-mic**: dit maakt de echo-grens weg door de bron te veranderen. In plaats van de robotmic (die zichzelf hoort) herkent de presenter nu keywords via de **laptopmic** (`SpeechRecognition`) — die staat dicht bij jou, en de herkenning wordt **gepauzeerd zodra de laptop zelf spreekt**, zodat hij nooit op zijn eigen chime-in triggert. Elke definitieve transcriptie gaat naar `/presentation/speech`. De robotmic blijft ook keywords voeden; de laptopmic is de betrouwbare weg voor een echte demo. Beide zijn optioneel en tonen zich alleen als de browser de API ondersteunt; netjes opgeruimd bij End/unmount (mic stopt, spraak geannuleerd). Geverifieerd in de draaiende console: laptop-audio spreekt een nieuwe subtitle uit (gevangen via een spy op de echte `speechSynthesis.speak` — de property is read-only, dus niet te vervangen), toggles verschijnen. De mic-logica is unit-getest met een nep-`SpeechRecognition`: transcripties bereiken de callback, tijdens muten worden ze **weggegooid** (dat is het hele punt — hij hoort de laptop niet), en de herkenning herstart wanneer de browser hem tussentijds stopt maar niet meer ná stop. Console 82 groen, build schoon.
  **NB**: de laptopmic-herkenning zelf vergt een echte microfoon en Chrome-toestemming — dat verifieer jij op de dag zelf; de muting-garantie en de bedrading zijn wél bewezen. Hiermee zijn beide eerlijke grenzen uit Fase 2 aangepakt: keyword-invallen hebben nu een betrouwbare bron (laptopmic i.p.v. de echo-gevoelige robotmic), en `improvise` kan met tools live data ophalen (U208).

- [x] **U210 — waarom er geen update kwam: een flaky test blokkeerde de release van U209** · `pending`
  Melding "ik krijg geen updatemelding, nog steeds oude versie" terwijl About v2.0.27 toont. Uitgezocht: v2.0.27 **is** de laatste gepubliceerde release, dus "up to date" klopte — er was simpelweg geen nieuwere. Oorzaak: de **Release-run van U209 faalde** op de `test`-job, waardoor `build` en `release` werden overgeslagen (de `screenshots`-timeout was al `continue-on-error`, dus onschuldig). De gevallen test: `test_gesture_publishes_event_with_cooldown` — `assert 0 == 1`. **Echte bug, geen testfout**: `_last_gesture_at` startte op `0.0`, en de cooldown-check is `monotonic() - last < cooldown`; `time.monotonic()` is seconden sinds boot (meestal groot), dus de **allereerste** gesture leek "binnen cooldown" en werd onderdrukt zodra de machine langer dan de cooldown aan stond. In CI flaky (alleen een net-geboote runner had `monotonic() < cooldown`), en op de **echte robot** zou de eerste palm-gesture na opstart stilletjes opgegeten worden. Fix: `_last_gesture_at = float("-inf")` → de eerste gesture vuurt altijd, de cooldown gate't alleen de tweede. Test 3x achter elkaar groen, brain 334 groen, lint schoon. Deze push levert de release die U209 (en deze fix) eindelijk publiceert → de app krijgt zijn updatemelding.
  **NB**: de screenshots-stap kan opnieuw time-outen, maar dat is bij ontwerp niet-fataal voor de release; enkel de release-notes missen dan de plaatjes.

- [x] **U211 — versie op het splash-scherm bij opstarten** · `pending`
  Het opstartscherm ("AURA is starting…") toont nu ook `version <x.y.z>` onder de subtitel, uit `app.getVersion()` (dezelfde bron als het About-venster). Handig om in één oogopslag te zien welke build draait — juist na de vorige verwarring over "welke versie heb ik nu?". Desktop-only stringwijziging in de bestaande `SPLASH_HTML`; syntax + eslint schoon. **NB: niet in een echte Electron-run gezien** (geen GUI hier), maar het is een triviale interpolatie in de al werkende splash-data-URI.

- [x] **U212 — camera hikte op één gemist frame; nu tolerant aan beide kanten** · `pending`
  Melding "camerabeeld valt soms uit, hervat na 1-2s". Oorzaak was tweeledig. **Console** (`VideoPanel`): bij **één** mislukte of trage frame-fetch zette de lus meteen `state='off'` (paneel toont "No camera feed") én wachtte 2 seconden — dus één hikje = 2s zwart, precies het symptoom. Nu houdt hij het **laatste frame** vast, probeert elke 400ms opnieuw, en toont pas "off" wanneer het beeld écht >2,5s weg is; plus een 4s abort per verzoek zodat een vastgelopen frame de lus niet tientallen seconden ophoudt. **Robot** (`reachy`-adapter): `get_camera_frame_jpeg` was single-shot, dus een `None` die de media-pijplijn **tussen** frames teruggeeft werd een 503 → zichtbare hik; nu pollt hij tot 1s (zoals `get_camera_frame` al deed), zodat een momentane leemte oplost i.p.v. te blippen. **Direct op de Pi gedeployed** (git pull + service-herstart): frames komen nu stabiel binnen — 200, ~32 KB, ~0,16s, 0 herstarts, geen 503's in de logs. De robot-fix helpt je huidige app meteen; de console-fix komt mee in de volgende release. Robot-runtime 85 groen, console 82 groen, lint schoon.

- [x] **U213 — gezicht aanleren: eerlijke feedback + avatar los van herkenning** · `pending`
  Melding "hoe weet ik dat hij het gezicht detecteert? en Take a photo werkt niet". Live gediagnosticeerd tegen de draaiende app (v2.0.31 — de auto-update wérkt inmiddels): de gebundelde Python-omgeving mist **insightface én Pillow**, want de `recognition`-extra faalde bij de installatie en de bootstrap viel terug op een kale sync. Gevolg: `embedder: 'null'` (herkenning draait zonder model) en de avatar-capture gaf 422 "could not read a picture". **Drie fixes.** (1) **Eerlijke melding**: enroll gaf met een null-embedder *"no face in frame — look straight at the robot"*, alsof het aan je houding lag; nu detecteert het de null-embedder en zegt het *"Face recognition isn't installed on this machine… reinstall/repair"* (503, `reason: embedder_unavailable`) — geen fantoom-positioneringsprobleem meer. (2) **Positieve bevestiging**: een geslaagde teach toont nu *"✓ Face detected — learned jan (N samples). Re-check confirmed."* i.p.v. een kaal "learned", met het echte aantal vastgelegde hoeken. (3) **Pillow is nu een KERN-dependency van aura-brain** i.p.v. verstopt in de recognition-extra — de avatar (U204) en de brain-side downscale (U196) hebben niets met gezichtsherkenning te maken, dus toen die zware extra niet bouwde brak de avatar mee. `BOOTSTRAP_REV` naar 3 zodat bestaande installs opnieuw syncen en de kale fallback-sync nu sowieso Pillow oplevert (avatar werkt dan, ook als insightface niet bouwt). Tests: null-embedder geeft de eerlijke 503, echte embedder rapporteert samples voor de bevestiging; brain 336, console 82 groen, lint schoon.
  **Wat dit voor jou betekent na de volgende update**: de avatar-foto werkt (Pillow komt mee), en teach zegt eerlijk of het model er is. **Gezichtsherkenning zelf (insightface) blijft de lastige**: op Windows wil die wheel/build weleens falen. Werkt "Teach face" na de update nog steeds niet en zegt hij "isn't installed", dan moet insightface/onnxruntime alsnog in de app-omgeving — dat vergt mogelijk build tools; zeg het en ik help je dat gericht installeren.

- [x] **U214 — personenfilter in de graph** · `pending`
  Vraag: in de graph kunnen filteren op personen. Boven de constellatie staat nu een chip-balk: **Everyone** plus één chip per persoon, **meervoudig selecteerbaar** — de interessante blik is meestal "deze twee naast elkaar", niet "alleen deze". Filteren toont enkel de gekozen personen, hún skills en hún facts; topics filteren zichzelf mee omdat ze alleen ontstaan uit een overlevend fact. **Bewuste uitzondering**: skills zónder persoon (de algemene bibliotheek) blijven staan — die gelden voor iedereen, en ze laten verdwijnen leest als dataverlies in plaats van als filter. De filterregel is uit de canvas-code getrokken naar `lib/graphFilter.ts` zodat hij te testen is: 6 tests (leeg = alles ongemoeid, alleen de gekozen persoon + zijn skills/facts, algemene skills blijven, meerdere personen tegelijk, hoofdletterongevoelig, onbekende id geeft een lege constellatie i.p.v. alles). Console 88 groen.
  **Eén echte fout onderweg in mijn eigen code gevangen**: ik gaf het filter door als `[...graphFilter]` inline, wat bij **elke** re-render van het paneel een nieuwe array is — dat hertriggert de watcher van de graph en bouwt de force-layout opnieuw op, dus de constellatie zou zichtbaar springen om redenen die niets met het filter te maken hebben. Nu een `computed`, zodat de identiteit alleen verandert als het filter écht verandert.
  **NB: het canvas zelf niet visueel geverifieerd** — het browserpaneel staat hier op `document.hidden`, waardoor `requestAnimationFrame` niet vuurt en de graph domweg niet tekent (bevestigd gemeten: 0 frames). Wat ik wél live zag: de chips renderen correct (Everyone/Jan/Tycho) en het aan/uit-zetten schakelt zoals verwacht (Jan → Jan+Tycho → Everyone). Of de knopen visueel verdwijnen bevestig jij in de app.

- [x] **U215 — security-audit: de kritieke transport-gaten gedicht** · `pending`
  Volledige audit (security/a11y/UI-UX/performance) parallel uitgevoerd; alle bevindingen geverifieerd tegen de code (samenvatting in `docs/audit-2026-08.md`). Deze unit pakt de vier zwaarste security-bevindingen, allemaal zelf nagetrokken. **S1 (kritiek)**: de brain bond op `0.0.0.0:8020` **zonder enige auth** — elke buur op dezelfde WiFi kon de kennis + OAuth-tokens lezen en had een RCE-keten (capabilities→auto-approve→run_powershell, keten geverifieerd). Nu `host=os.environ.get("HOST","127.0.0.1")` — loopback; de console draait op dezelfde machine dus verliest niets, en ik bevestigde dat de robot brain→robot is (de robot belt nóóit terug), dus loopback breekt de robot niet. **S2 (kritiek)**: `.env`-waarde-injectie — een newline in bv. `/setup/prefs` schreef extra env-regels (`AUTO_APPROVE_TOOLS=…`) → persistente RCE bij de volgende start. `_write_env` weigert nu ongeldige keys en str',t CR/LF uit waarden, zodat één setting altijd één regel is. **S4 (hoog)**: geen Host/Origin-validatie → DNS-rebinding omzeilt CORS volledig. Toegevoegd: `TrustedHostMiddleware` (alleen loopback + `testserver`) en een Origin-guard die state-changing methods met een vreemde Origin weigert (geen-Origin-calls zoals curl blijven werken; de console-origin is toegestaan). **S6 (hoog)**: `/recognition/merge` wíste een persoon zonder bevestiging; nu moet de bron-id als `confirm` worden meegestuurd (428 anders), pariteit met `forget_person`; de console stuurt dat mee. Tests: cross-origin POST → 403, eigen origin/geen origin door, verkeerde Host → 400, newline-injectie schrijft geen tweede env-regel, merge zonder confirm → 428 en niets gewist. 7 security-tests + 40 endpoint-tests groen, lint schoon.
  **Bewust NIET in deze unit** (staat in het auditdoc, deels grotere/risicovollere ingrepen): de Pi op `0.0.0.0` (S5) vergt een brain↔robot shared secret — mág niet op loopback want de brain bereikt hem over het LAN, en ik wil de net-werkende robot niet breken; de identity-token-HTTP-route (S3, nu enkel loopback bereikbaar) verwijderen; keyring i.p.v. passphrase-in-`.env` (S10); installer-handtekening (S11); scrypt-parameters + salt (S9). Die volgen als aparte units zodra jij akkoord bent. **NB: neemt pas effect na de volgende update; de brain draait nu nog op 0.0.0.0 tot je herstart met de nieuwe build.**

- [x] **U216 — twee ongedefinieerde design-tokens + faint-tekstcontrast** · `pending`
  Uit de UI/UX- en a11y-audits, beide zelf geverifieerd met een grep. **`--radius-md` (44×) en `--accent-contrast` (15×) werden nergens gedefinieerd** — een `var()` zonder fallback maakt de hele declaratie ongeldig, dus de hele nieuwere generatie componenten (presenter, scenario-bouwer, rail/hero, update-banner) rendeerde **vierkant** terwijl de oudere afgerond was, en de accent-tekst viel stil terug op `#fff`. Beide nu gedefinieerd in `tokens.css` (`--radius-md: 0.5rem`, `--accent-contrast: var(--on-accent)`) → ~60 plekken in één klap goed. **Contrast**: `--text-faint` zakte in beide thema's onder WCAG AA (licht `#94a3b8` = 2,4:1, donker `#64748b` = 3,1:1) voor kleine tekst als capability-uitleg, tijdstempels en de graph-legenda; omgewisseld naar `#64748b` (licht, ~4,8:1) en `#94a3b8` (donker, ~5,6:1). Console 88 groen, build schoon.
  **NB: één design-keuze bewust NIET zelf gemaakt** — wit-op-groen (het standaard-accent van U193, `#16a34a`) haalt 3,34:1 op knoppen, onder AA voor normale tekst. De fix (accent naar `#15803d`) verandert je gekozen groen zichtbaar, dus dat laat ik aan jou; staat als aanbeveling in `docs/audit-2026-08.md`.

- [x] **U217 — audit-quick-wins: graph stopt met tekenen, graph-open in één call, reduce-motion** · `pending`
  De veilige, hoogwaardige performance- en motion-bevindingen uit de audit die geen Pi-deploy of designkeuze vergen. **P3 (grootste client-win)**: `BrainGraph` bleef 60 fps hertekenen nádat de force-simulatie was uitgestabiliseerd (`ticks >= 260`), en `draw()` zet `shadowBlur` per knoop — de duurste canvas-2D-primitief. Een gedockt graph-tabblad brandde daardoor ~30-100% van een core voor niets. De lus stopt nu met herplannen zodra ze settelt; elke interactie (pan/zoom/hover/rebuild) roept `redraw()` aan, die alleen een nieuwe lus start als de sim nog loopt. **P5**: `selectGraph` deed N sequentiële `inspectPerson`-calls die bovendien `store.detail` overschreven (drie person-watchers vuurden N× en het personenpaneel wees daarna naar de laatste in de lijst — een echte bug); vervangen door één `GET /knowledge/export`, nul neveneffecten. **A11y (2.3.3)**: `prefers-reduced-motion`-mediaquery toegevoegd — bij "beweging verminderen" in het OS worden transitions/looping-animaties (pulserende mic/"thinking", spinners) vrijwel uitgezet. Console 88 groen, build schoon.
  **NB: P1/P2/P4 (perceptie stuurt 2 MB PNG i.p.v. JPEG, downscale-cache, gallery-RAM) staan bewust apart** — die raken de robot-runtime en vergen een Pi-deploy; ik pak ze als een aparte unit zodat ik ze op de robot kan verifiëren i.p.v. blind te pushen.

- [x] **U218 — gezichtsherkenning verdween na élke app-update; bootstrap controleert nu i.p.v. te vertrouwen** · `pending`
  Melding: "Face recognition isn't installed on this machine" bij een gezicht aanleren — precies de eerlijke melding uit U213, dus die deed zijn werk, maar de onderliggende oorzaak lag dieper. Live vastgesteld: app op 2.0.33, `embedder: null`, en in de gebundelde venv ontbraken **insightface + onnxruntime** terwijl **PIL er wél was** — dat laatste bewijst dat de U213-fix (Pillow als kern-dependency) werkte en tegelijk dat de zware extra opnieuw was weggevallen. Tijdlijn uit de bestandsstempels: 09:54 update installeert (NSIS vervangt de héle installatiemap, inclusief `.venv`), 09:55 bootstrap draait en schrijft `rev=3`, 10:02 venv wordt bij de brain-start opgebouwd — zonder recognition. **De echte fout**: de bootstrap-marker leeft in userData en overleeft de update, terwijl de venv in de installatiemap staat en er juist door gewist wordt; bovendien schrijft de bootstrap zijn "klaar"-marker óók wanneer zijn eigen `try/catch` is teruggevallen op de kale sync. Daarna claimt de marker voor altijd "gedaan" en krijgt de eigenaar nooit meer herkenning. Getest en uitgesloten wat het níét was: het bootstrap-commando zelf werkt (exit 0, installeert insightface), en `uv run` (waarmee de brain start) snoeit de extra niet weg. **Fix**: de bootstrap controleert nu de **capability** in plaats van een boekhoudvlag — `recognitionInstalled()` kijkt of insightface+onnxruntime in de venv staan (goedkope mapcheck, geen subprocess op het startpad) en draait de sync opnieuw zodra ze ontbreken, ongeacht wat de marker beweert. Dat heelt zichzelf na élke update. Met een grens: `recogFail` in de marker, na 2 mislukte pogingen stopt het opnieuw proberen (anders zou een machine die deze wheels écht niet kan bouwen bij iedere start minutenlang synchroniseren) — de eerlijke melding van U213 legt het dan uit. Syntax + eslint schoon.
  **Voor nu al hersteld**: ik heb de recognition-stack handmatig terug in de app-omgeving gezet (insightface 1.0.1 + onnxruntime), dus na een herstart van de brain werkt gezichtsherkenning meteen weer.

- [x] **U219 — P1/P2/P4: perceptie stopt met PNG hercoderen, frames worden gedeeld** · `pending`
  Alle drie gemeten **op de echte robot**, voor en na. **P1 (grootste verspilling in het systeem)**: het perceptie-pad haalde elke 2 s een frame op waarbij de robot zijn JPEG naar **PNG** hercodeerde, puur vanwege een oude comment ("contract says PNG") — terwijl élke consument (de embedder via `PIL.Image.open`, de gebarendetector, de avatar-encoder) JPEG net zo goed leest. Nulmeting: **1554 ms en 1366 KB per frame**, op een interval van 2 s — de Pi was dus vrijwel continu bezig met één plaatje. Perceptie haalt nu `/camera/frame.jpg?width=960` (bewust bréder dan de live-view, zodat een gezicht verderop in de kamer niet verloren gaat waar 640 px het kan missen). Gemeten na: **131 ms en 69 KB → 12x sneller, 20x kleiner.** **P4**: de sightings-galerij bewaarde zes vólledige frames per persoon in RAM terwijl er al een thumbnail was; nu een 640 px-kopie (met terugval op het origineel als verkleinen faalt — een kleiner plaatje is een optimalisatie, nooit een reden om de snapshot te verliezen). **P2 (twee keer moeten doen)**: mijn eerste versie cachete op de identiteit van het bronframe — en sloeg na deploy **0 van de 14** keer aan, ook 0 van 3 bij gelijktijdige clients. Oorzaak: elk verzoek pakt eerst zélf een vers frame (de dure stap) en pas daarna volgt de vergelijking, dus de sleutel verschilde altijd. Vervangen door een **tijd**-cache die vóór het ophalen ingrijpt, met een TTL (60 ms) korter dan één frameperiode (~83 ms bij 12 fps) — zo wordt nooit een ouder beeld getoond dan de camera zelf zou geven. Gemeten na: twee gelijktijdige verzoeken in **18-24 ms met gedeeld frame** (was ~180 ms), en verzoeken 0,4 s uit elkaar leveren nog steeds een vers frame. Daarbovenop een gedeelde 80 ms-cache in de brain, zodat camerapaneel en presenter samen één robot-hop kosten. Robot-runtime 85 groen (test herschreven naar het nieuwe contract: 5 snelle verzoeken = 1 grab, ná de TTL weer vers), brain camera/gallery-tests groen, lint schoon. **Op de robot gedeployed en geverifieerd.**
  **Over de gevraagde beeldvertraging**: de live-view zit nu op **~128 ms** mediaan. Wat overblijft is grotendeels de WiFi-hop zelf plus de camera-encode; de dubbele belasting bij twee open panelen is weg. Verder omlaag zou een structureel andere aanpak vergen (bv. WebRTC), niet nog een cache.

- [x] **U220 — S5: de robot geeft zijn camera en microfoon niet meer aan het hele WiFi** · `pending`
  De zwaarste openstaande security-bevinding. De Pi **moet** op `0.0.0.0` luisteren (de brain bereikt hem over het LAN), dus loopback was geen optie; in plaats daarvan een gedeeld geheim. `robot-runtime` weigert elk `/robot/*`-verzoek waarvan `X-AURA-Secret` niet klopt, met `hmac.compare_digest` zodat het geheim niet byte voor byte uit de responstijd te halen is. De brain stuurt het mee vanuit **één helper** die door élk uitgaand pad wordt gebruikt (commando's, camera-proxy, audio-stream, adres-probe) — een vergeten pad zou er precies uitzien als "de robot ligt eruit", dus dat mocht niet van de call-site afhangen. **Opt-in ontworpen**: zonder `ROBOT_SHARED_SECRET` verandert er niets, zodat deployen nooit een robot kan stranden waarvan de brain het geheim nog niet kent — precies zo uitgevoerd: eerst uitgeschakeld gedeployed en geverifieerd dat de camera bleef werken (200), pas daarna aangezet. `/health` blijft bewust open: de "Zoek de robot"-scan gebruikt hem en hij verklapt alleen modus/batterij. Het geheim staat op de robot in een systemd drop-in (`chmod 600`, overleeft herstarts en `git pull`) en op de laptop in de `.env` van de app. **Geverifieerd vanaf het LAN, zoals een buur het zou zien**: camera 401, microfoon 401, status/motoren 401, health 200, en mét het geheim camera 200. 4 nieuwe tests, robot-runtime 89 groen, lint schoon.
  **NB: de brain moet nog herstarten** om het geheim uit de `.env` te lezen — tot dan krijgt de app zelf 401 van de robot. Eén klik op ↻ (Restart brain) volstaat.

- [x] **U221 — security-restant: geen ruwe tokens naar de browser, wachtwoord-orakel dicht, Electron-links** · `pending`
  **S3**: de audit stelde voor de token-route te verwijderen, maar die bleek nog in gebruik — dus eerst gekeken wáárvoor. De console gebruikte `GET /identity/token/...` alleen om `resp.ok` te lezen en een verbindingsbadge te kleuren; hij leest het antwoord nooit uit. Er werd dus een **levende Microsoft-/Google-/GitHub-token naar de browser gestuurd om een bolletje groen te maken**. Nieuwe route `GET /identity/status/{user}/{provider}` geeft `{connected: bool}` en verder niets; de console gebruikt die nu. De tokenroute blijft bestaan voor connector-service (die de echte token nodig heeft om de API van de provider te bellen) maar is nu server-side-only, en de brain luistert sinds U215 alleen op loopback. De overige twee console-aanroepen zijn opslaan (PUT) en loskoppelen (DELETE) — schrijfacties, geen tokenlekken. **S14**: `/knowledge/unlock` was een gratis orakel — scrypt's ~50 ms houdt een woordenboekaanval niet tegen en succes levert álle profielen en gezichtsvectoren op. Nu `hmac.compare_digest` (een gewone `!=` lekt via responstijd hoeveel van de afgeleide sleutel klopte) plus exponentiële backoff na 5 pogingen (429 met `retry_after_s`). **S15**: `setWindowOpenHandler` opende élke http(s)-URL in de systeembrowser — en de console toont ook door agents ingelezen inhoud, dus een link uit een derde-partijpagina kon ongevraagd openen. Nu een allow-list van de plekken waar de app echt naartoe linkt; al het andere vraagt eerst bevestiging in een dialoog. DevTools staat niet meer in het menu van een verpakte build (debugtool, geen functie — in productie dient het vooral iemand die de eigenaar wil overhalen het te openen). 2 nieuwe tests (statusroute geeft geen token, unlock geeft 429 na 5 pogingen), brain 342 groen, console 88 groen, lint schoon.

- [x] **U222 — toegankelijkheid: de zwaarste WCAG-bevindingen uit de audit** · `pending`
  **Modals (2.1.2 / 2.4.3 / 2.4.7)**: vijf overlays openden zonder toetsenbordpad eruit — `@click.self` is muis-only, niets nam focus, niets gaf hem terug; een schermlezergebruiker landde in een dialoog die hij niet kon sluiten met de pagina er nog doorheen tabbaar. Eén composable `useModal` (niet vijf kopieën — zo zijn drie van de vijf juist uit elkaar gegroeid) regelt Escape, focus naar de dialoog bij openen en focus terug naar de trigger bij sluiten; alle vijf kregen `role="dialog" aria-modal aria-label tabindex="-1"`. **Geverifieerd in de draaiende console**: About opent met de juiste rol/label, focus landt op de dialoog, Escape sluit hem, en de focus keert terug naar de knop waar je vandaan kwam. **Toestand die alleen in kleur zat (4.1.2 / 1.4.1)**: de vier robot-toggles, de twee presenter-toggles en de graph-filterchips kregen `aria-pressed` — "Follow" en "Notify" hielden in beide standen dezelfde tekst, dus een schermlezer las ze identiek voor. Gemeten na afloop: alle vier melden nu hun stand. De capability-schakelaars waren **naamloos** (hun enige kind was een lege `<span>`) terwijl ze de rechten van de robot op de laptop verlenen — nu `role="switch"` met `aria-checked` en `aria-label`. **Live regions (4.1.3)**: het gesprek is nu `role="log" aria-live="polite"` (het antwoord van de robot — de kern van de app — was volledig stil), het presenter-ondertitelvlak `role="status"`, het robot-offline-blok `role="alert"`, en de goedkeuringsprompt `role="alertdialog"` (een blokkerende vraag mét aflopende teller die nooit werd aangekondigd). **De canvas-graph (1.1.1 / 2.1.1)** had geen tekstalternatief en geen muisloos pad: nu `role="img"` met een samenvatting die meebouwt met de graph ("Knowledge graph: 2 persons") plus een visueel verborgen maar **focusbare** lijst met dezelfde knopen en dezelfde open-actie — bevestigd werkend. Verder labels op placeholder-only velden, de zoomknoppen, het volume, de persona-keuze, en `aria-expanded`/`aria-haspopup` op het acties-menu. Console 88 groen, build schoon.
  **NB bewust nog niet gedaan**: toetsenbordbediening voor de aim-pad en de paneelsplitsers (2.1.1). Die vragen een echte interactie-ontwerpkeuze (pijltjes-stappen, stapgrootte) en zijn geen attribuut-fix; de panelen zijn wel volledig aan/uit te zetten vanuit de titelbalk, dus geen inhoud is onbereikbaar.

- [x] **U223 — UX: één taal, een echte bevestigingsdialoog, leesbaar accent** · `pending`
  **Eén taal.** De console sprak Nederlands en Engels door elkaar — soms binnen hetzelfde blok (een Engelse diagnose van de brain, dan een Nederlandse knop eronder), en het screen-control-bericht stond zelfs in twee talen tegelijk op het scherm (Electron-overlay NL, in-app strip EN). Gekozen voor **Engels overal**: de brain zendt zijn diagnoses al in het Engels, 15 van de 17 componenten waren het al, en de eigenaar kiest de taal van de robot los daarvan (dat is een andere laag dan de knoppen van de app). 12 strings in de console + 6 in de Electron-shell vertaald; geen Nederlandse UI-tekst meer over. **Bevestigingsdialoog.** De meest destructieve actie in de app — een persoon vergeten, wat profiel én gezicht wist — zat achter een kale `confirm()`: ongethematiseerd, negeert dark mode, en inconsistent met de goedgekeurde-stijl-prompt die er al was. Nieuwe `ConfirmDialog` (role="alertdialog", Escape annuleert, **focus op Cancel** zodat een losse Enter niets vernietigt). Live geverifieerd: titel "Forget Nora?", de gevolgen uitgeschreven, focus op Cancel, Escape annuleert. **Accent-contrast** (jouw goedgekeurde designkeuze): wit-op-groen haalde 3,34:1 en wit-op-amber 3,19:1 — onder AA voor knoptekst. Groen `#16a34a → #15803d` (4,6:1) en amber `#d97706 → #b45309` (4,7:1), met de hover een stap donkerder zodat die zichtbaar blijft (anders was hover gelijk aan de nieuwe accentkleur geworden — die viel me op ná de eerste wijziging). **Loading/empty-states** in de personenlijst: bij een koude start of een onbereikbare brain was die simpelweg leeg zonder uitleg. Console 88 groen (één bestaande test verwachtte nog de Nederlandse tekst — die hoorde mee te veranderen, niet omzeild te worden), build schoon.

- [x] **U224 — S11: de update-installer wordt geverifieerd voordat hij draait** · `pending`
  De app downloadde een installer en voerde die met verhoogd vertrouwen uit **zonder enige controle**. Drie echte risico's aangepakt. **(1) Naam-injectie**: `asset.name` komt uit de release en wordt geïnterpoleerd in het `.cmd`-script dat de installatie uitvoert — een aanhalingsteken of spatie breekt daar uit de quoting. `safeAssetName()` weigert alles wat geen kale bestandsnaam is. **(2) Staging in `%TEMP%`**: de installer lag daar tot vier uur te wachten op een klik, in een map waar élk proces mag schrijven; nu in `userData`. **(3) Geen integriteitscontrole**: de release-workflow publiceert nu `SHA256SUMS.txt` per release, en de app verifieert het gedownloade bestand daartegen vóór het staged wordt. Een niet-kloppende checksum betekent: bestand weggegooid, niets gestaged, de eigenaar houdt een werkende app. Een ontbrekende checksumlijst (oudere releases) wordt **gerapporteerd, nooit stil geaccepteerd** — dan valt hij terug op de releasepagina zodat je bewust zelf kunt bijwerken. Tests in `test-updater-verify.cjs` (plain node, geen testrunner in dat pakket) dekken precies waar het om gaat: kloppende hash → geaccepteerd, **gemanipuleerd bestand → geweigerd**, ontbrekende lijst → gemeld, asset niet in de lijst → geweigerd, en zes vormen van gevaarlijke bestandsnamen. In CI gehangen zodat dit niet stil kan verdwijnen. Alle asserties groen, eslint schoon.
  **NB**: de eerstvolgende release publiceert de checksums; updaten *naar* die release gebeurt nog door de huidige app (zonder verificatie), daarna is de keten sluitend.

- [x] **U225 — S9 + S10: de eigenaarssleutel zelf** · `pending`
  De laatste twee audit-punten, samen uitgevoerd omdat ze dezelfde sleutel raken — en op échte data, dus met een geverifieerde back-up vooraf en een terugweg die ik eerst op een kopie heb bewezen.

  **Wat er mis was.** (S10) De versleuteling belooft dat een kopie van je datamap waardeloos is zonder passphrase. Die belofte was hol: de passphrase stond in `%APPDATA%/aura-desktop/.env` — een *zustermap* van de ciphertext, met dezelfde rechten. Wie het ene kon lezen, kon het andere lezen; de encryptie beschermde dus tegen niets wat ze realistisch tegenkomt. (S9) De sleutelafleiding gebruikte scrypt `n=2**14` (drie verdubbelingen onder de huidige OWASP-richtlijn) en viel zonder `KNOWLEDGE_SALT` terug op de hardgecodeerde string `aura-knowledge` — elke installatie die de wizard nooit draaide deelde dus zijn salt met alle andere. Minimumlengte passphrase stond op 8.

  **De aanpak.** Constanten aanpassen kón niet: de OMK wrapt de per-persoon DEK's, dus een andere OMK maakt de bestaande store onleesbaar. De parameters zijn daarom *onderdeel van de opgeslagen staat* geworden — `key-params.json` naast de ciphertext (nieuw: `shared_schemas.knowledge.omk`). Bij het opstarten roteert een store die nog op de oude parameters staat ter plekke: alleen de gewrapte DEK's en de embedding-blobs worden herschreven, de kennisbundels zelf blijven ongemoeid — precies waar `wrap_dek` voor ontworpen was.

  **Crash-veiligheid**, want dit draait één keer op data die niet te reproduceren is: de oude parameters worden onder `migrating_from` weggeschreven **vóór** er één byte verandert, elke store wordt apart geprobed, en er wordt pas herschreven nadat de oude sleutel bewézen heeft de huidige inhoud te openen. `migrating_from` wordt bewust nooit verwijderd — het zijn publieke parameters, geen sleutel, en ze zijn het vangnet voor een store die deze keer gemist werd.

  **Twee scherpe randen die mijn eigen tests blootlegden**, allebei gerepareerd vóór ze data raakten: (1) `migrating_from` werd te vroeg weggegooid als niet álle stores meegegeven waren — een gemiste store was dan permanent onleesbaar; (2) één onleesbare entry (die in het wild al bestaan — `list_people` slaat ze over) blokkeerde de hele migratie voor altijd. En een derde bij de eerste echte testrun: een vreemd `recognition.enc.json` liet de hele brain weigeren. Nu is alleen de *knowledge*-store fataal — gezichtsvectoren zijn opnieuw op te bouwen, en een oud bestand van een vorige installatie mag nooit de reden zijn dat er niets meer start.

  **S10**: passphrase naar de OS-kluis (Windows Credential Manager/DPAPI) via `secret_store`, met **read-back-verificatie** vóór de oude kopie verdwijnt. `KNOWLEDGE_PASSPHRASE` wint nog steeds als hij gezet is — docker/CI/headless hebben geen kluis, en die breken om een desktopprobleem op te lossen is een slechte ruil. Wizard en `/setup/secure` schrijven voortaan naar de kluis (en melden eerlijk `remembered_in: keyring | env-file`). Minimum passphrase 8 → 12.

  **Een echt risico dat ik onderweg veroorzaakte en moest opruimen**: doordat de wizard nu naar de kluis schrijft, zette de testsuite bij de eerste volle run zijn eigen testpassphrase in de *echte* Windows-kluis van de ontwikkelaar. Geverifieerd (21 tekens i.p.v. 11), verwijderd, en dichtgezet met een autouse-fixture in `conftest.py` die een in-memory kluis injecteert. Er ging niets verloren omdat `.env` toen nog de echte waarde had — maar dat was geluk, geen ontwerp.

  **Uitgevoerd op de echte installatie** (`scripts/migrate_owner_key.py`, met guard die weigert zolang de brain op 8020 luistert): back-up gemaakt, 4 personen + 14 gezichtssamples geroteerd naar `n=131072` met een verse random salt, passphrase in de kluis, 2 regels uit `.env` verwijderd. **Geverifieerd, niet aangenomen**: brain geboot met de nieuwe code en een `.env` zónder passphrase → `passphrase from keyring`, `omk_loaded: true`, tier sensitive, 4 profielen decrypten via de API (owner/family/family/demo). Alle 14 embeddings ontsleutelen naar geldige 512-dim ArcFace-vectoren. Dat laatste ontdekte ik omdat mijn eigen verificatie te zwak was: `sample_count()` telt blobs zonder ze te ontsleutelen, dus "14 samples" bewees niets — het script telt nu alleen wat écht opengaat. Herhaald draaien is idempotent (bewezen). Kosten: scrypt 55ms → 422ms per afleiding, eenmalig bij boot en per unlock-poging — meteen ook een rem op online raden, bovenop de bestaande lockout. Shared-schemas 142 groen (11 nieuw), brain 343 groen, ruff schoon.

- [x] **U226 — de repo klaarmaken om publiek te worden** · `pending`
  De eigenaar wil de repo openbaar maken. Dat is onomkeerbaar en neemt de **volledige geschiedenis** mee, dus eerst een echte inventarisatie: alle 4106 objecten in de geschiedenis langs de regels van `scripts/privacy_scan.py`, plus handmatig zoeken naar wat een scanner per definitie niet ziet.

  **Mechanisch schoon, en dat is niet vanzelfsprekend**: **0** van de 4106 objecten zou door de padregels geblokkeerd worden — nooit een echte `.env`, database, `.enc.json`, audiofragment, snapshot, SSH-sleutel of persoonlijk `skills/*.md` gecommit. Geen enkele API-sleutel of token in de geschiedenis (2 treffers, beide nep-fixtures). Auteur-e-mail is het GitHub-noreply-adres, niet het privé-adres. De pre-commit hook en de CI-backstop uit U167 hebben precies gedaan waarvoor ze gebouwd zijn.

  **Wat er wél in zat — en waar geen scanner op aanslaat**: de echte voornamen van twee gezinsleden, als testfixtures én in het ledger. Niet neutraal gebruikt: één met rol `family` en een muziekvoorkeur eraan gekoppeld, de ander in een **gezichtsherkenningstest** met een `school`-fact en een huiswerk-skill — dus persoonsgegevens van een minderjarige. Plus het thuisnetwerk (robot- en laptop-IP, resultaat van een subnetscan). Gepseudonimiseerd via `git filter-repo` over de hele geschiedenis, niet alleen in HEAD: alleen in HEAD vervangen laat ze vindbaar in elke oudere commit, wat het punt mist.

  Eén valkuil die me bijna een corrupte documentatie opleverde: **"Nora" is óók gewoon het Nederlandse woord voor "iedere"**, en staat als zodanig aan het begin van zinnen in drie documenten. Een globale vervanging zou die zinnen onleesbaar hebben gemaakt. Daarom contextgebonden regels (`"Nora"`, `person_id="nora"`, `jan/Nora`, `Forget Nora?`, …) in plaats van één brede, met een controle achteraf op restanten.

  **Onderweg een echte bug gevonden die niets met publicatie te maken had.** De brain-suite bleef consequent hangen op test 22 van 343 — geen traagheid, een deadlock. `faulthandler_timeout` wees het aan: mediapipe's `HandLandmarker.__del__` sluit zijn dispatcher af door te blokkeren op een worker-future, en die finalizer vuurde midden in het opbouwen van een FastAPI-route. Oorzaak: `GESTURES_ENABLED` staat standaard aan, dus **elke** `create_app()` bouwde een echt hand-landmarker-model (8 MB + native threads) dat nergens werd vrijgegeven — honderden keren in de suite, en in productie één keer per brain-start zonder ooit te sluiten. Dat is een resourcelek, geen testartefact. `HandGestureDetector.close()` toegevoegd (idempotent, kan niet gooien — dit draait tijdens shutdown) en aangeroepen in de lifespan-teardown, plus `GESTURES_ENABLED=false` als default in de testconftest zodat de suite geen ML-model per app laadt. CI zag dit nooit: daar is de `gestures`-extra niet geïnstalleerd. Suite weer groen: **346 in 123s**.

  **En de drie openstaande auditpunten dichtgezet**, want een publiek auditdocument dat openstaande gaten aanwijst is een routekaart. **S3**: `GET /identity/token/{user}/{provider}` **verwijderd** — die gaf een levend Microsoft/Google/GitHub-token aan iedereen die de poort kon bereiken, en had geen enkele aanroeper meer (brain en connector-service halen tokens in-process; de console gebruikt `/identity/status` plus PUT/DELETE). De drie connectors hadden nog wél een HTTP-*fallback* naar precies die route — dode code die naar `identity-service:8006` wees, een container die sinds U2 in geen enkele topologie meer bestaat (compose draait alleen robot-runtime, aura-brain en de console). Die fallback is weg; zonder `token_fetcher` volgt nu een `ConnectorAuthError` die zegt wat er moet gebeuren, in plaats van een verwarrende 404 op een verwijderd endpoint. **S7**: `/robot/address` was een SSRF-primitive — de brain haalt dat adres periodiek op — dus `_blocked_target()` weigert nu link-local (169.254.0.0/16 en fe80::/10, waar elke cloudprovider zijn onbeveiligde metadata-service parkeert), inclusief hostnamen die daarheen resolven. Het privé-LAN en loopback blijven bewust toegestaan: daar wóónt de robot, en een neprobot op localhost is een ondersteunde dev-opstelling. Eerlijk over de grens: DNS-rebinding kan dit omzeilen, maar de Origin-guard uit U215 blokkeert de drive-by route al. **S12**: beide discovery-endpoints zijn POST — een GET die het LAN scant is af te vuren vanaf elke pagina die de browser laadt.

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
- 2026-07-13 — DEVICE DAY: robot found at reachy-mini.local (<robot-ip>); daemon initially hung (port 8000 bound, silent) — fixed by a reboot. U16 adapter built + **live-verified**: ReachyRobotAdapter (reachy-mini SDK 1.9, network mode) nodded and waved on the physical robot from the laptop; 12 stub tests + 3 live tests green. **Remaining: robot-runtime packaging ON the Pi (needs SSH), live media path (speaker/mic/camera → unlocks U18-camera + U22 live + U24), U26 budget guard.**
- 2026-07-13 (later) — daemon hung AGAIN ~15 min after reboot (needs on-robot diagnosis via SSH: user=pollen, journalctl -u reachy-mini-daemon). U18 completed in software: camera endpoint + RobotClient.camera_frame + PerceptionLoop (pluggable FaceEmbedder, insightface optional extra) + /recognition enroll/forget/status API + matcher disk persistence. **Remaining: Pi packaging + on-robot daemon debug (SSH key pending from user), live media verification, U24 voice wiring, U26.**
- 2026-07-14 — U38 FIXES: (1) SPRAAK: Electron permission-CHECK handler toegevoegd (getUserMedia checkt sync én vraagt) + robuuste client (MediaRecorder.isTypeSupported fallback, duidelijke fouten per NotAllowed/NotFound, zichtbare "Listening…/Transcribing…" status in Conversation) — server-endpoint werkte al (geverifieerd). (2) HERKENNING: drempel 0.6→0.4 (RECOGNITION_THRESHOLD env; 0.6 verwierp echte insightface-matches → eigenaar bleef "onbekend") + MULTI-SAMPLE per persoon (tot 8 shots, identify = max over alle samples, v1→v2 migratie) + enroll pakt 4 frames. (3) MOTION LOG: begrensde scrolllijst, ellipsis, tabular time, nette dot-uitlijning. (4) M365/ONEDRIVE: list_onedrive_files tool + mock-data + route + work/demo-mode → "wat staat er in mijn OneDrive?" werkt nu (live geverifieerd, NL). Spotify/Sonos → U39 backlog. Brain 82, orchestrator 138, connector 26, schemas 123, console 56 groen.
- 2026-07-14 — U36h TAAL + ROEPNAAM: brain /setup/prefs (assistant_name + language auto/en/nl/fr; env + persist naar .env; per-turn identity-prefix in pipeline `_identity_prefix()` zodat wijzigingen direct gelden; STT language-bias). Console prefsStore + Appearance-tab (naam-input + taaldropdown) + titelbalk toont de naam live. LIVE geverifieerd: naam→Richie + taal→nl, Engelse vraag kreeg NL antwoord als Richie; teruggezet naar AURA/auto. Basisrotatie: SDK-tracking beweegt bewust alleen de nek (mechanisch) → U37 body-yaw follow genoteerd. Brain 82, orchestrator 138, console 56 groen.
- 2026-07-14 — U36g HUMAN BEHAVIOR + TOOLS + SELF-MAINTENANCE: (1) Follow-me: daemon head-tracking auto-aan bij connect (HEAD_TRACKING env) + /robot/tracking + toggle in RobotPanel — robot kijkt omhoog naar je gezicht. (2) Luistergedrag: kleine knik zodra een voice-turn binnenkomt; spreekgebaren bestonden al (engine-timeline). (3) thumbs_up gebaar (landmark-heuristiek) → feestgebaar terug. (4) Quick Actions uitgebreid (Look around/Shake) + "Speak & Move"-combo-acties (Say hi/Introduce/Joke/Compliment) via /robot/say met motion_id (gather: spraak+gebaar tegelijk). (5) GELUID: hoofdoorzaak was Pi PCM op 62%/-23dB → 100%/0dB gezet + alsactl store; plus peak-normalisatie per utterance (0.95) vóór de volume-gain. (6) Laptop-tools: open_in_vscode orchestrator-tool (code -g pad:regel, shutil.which, work-mode) + DEV_AGENT_ENABLED default aan in desktop (writes blijven approval-gated; DEV_AGENT_BACKEND=claude beschikbaar voor Claude Code escalatie). (7) MaintenanceLoop: elke 5 min self-check (robot/LLM-key/TTS/knowledge-encryptie), auto-reconnect robot, MaintenanceReport event (broadcaster) in de console-eventlog. Brain 77, robot 45, orchestrator 138, schemas 123, console 56 groen. Live: tracking aan + speak-and-move geverifieerd.
- 2026-07-14 — U36f UNKNOWN-VISITOR LOG + TAGGING: SightingLog (in-memory ONLY — privacy: onbekenden gaven geen consent; merge op embedding-cosine, 15s cooldown, cap 12, 24h expiry, JPEG-thumbnails); PerceptionLoop logt onherkende gezichten (embedder draait nu vanaf boot, unknown-overlay werkt ook pre-secure); /recognition/sightings API (list/image/tag/dismiss) — tag = embedding versleuteld enrollen bij bestaande persoon + auto-purge van nu-herkende sightings → herkenning traint zichzelf; KnowledgePanel "Unknown visitors"-sectie (thumbnail, x-maal gezien, wie-is-dit dropdown, tag/dismiss, 15s auto-refresh). Brain 74 groen (11 nieuw). Live: recognition draait met insightface, "jan" enrolled door eigenaar.
- 2026-07-14 — U36e VOLUME + VOICE + GESTURES: (1) volumeslider in RobotPanel → brain /robot/volume → software-gain op elke PCM-sample in de adapter (live geverifieerd 0.8→0.5). (2) Spraakinvoer: mic-knop in ConversationPanel (MediaRecorder webm) → brain /voice/turn → OpenAI-transcriptie → TranscriptUpdated + pipeline-turn → antwoord hardop op de robot (embodiment); Electron mic-permission handler; end-to-end geverifieerd met gesynthetiseerde spraak ("What time is it right now?" correct getranscribeerd + beantwoord). (3) Gebaren: GestureDetected event + HandGestureDetector (mediapipe tasks-API, hand_landmarker ~8MB auto-download, open-palm heuristiek) in de PerceptionLoop (draait nu ALTIJD voor gebaren, matcher komt er bij secure bij; 8s cooldown) → open hand naar de camera = robot zwaait terug. python-multipart + mediapipe optional extra [gestures]. Brain 64, robot 45, console 56 groen.
- 2026-07-14 — U36c EMBODIED CONVERSATION + U34-slice: (1) elk assistant-antwoord wordt nu hardop gesproken + gebaar op inhoud (embodiment.py heuristiek: begroeting→wave, vraag/sorry→tilt, enthousiast→gesture, anders→nod; SPEAK_REPLIES toggle; live geverifieerd: robot sprak + gesticuleerde bij een echte turn). (2) MJPEG-stream: robot /robot/camera/stream (8fps multipart) + brain-proxy + VideoPanel <img>-stream met auto-retry — 22 frames/6s door de proxy i.p.v. 1fps-polling. (3) IN-APP SECURE (/setup/secure): passphrase in het Knowledge-paneel → live migratie InMemory→Encrypted store, judgment-swap, recognition start, opt-in .env-persist — geen CLI-wizard/herstart meer nodig. (4) Knowledge-UX: secure-banner, facts in mensentaal + suggestie-chips, "Teach face"-knop bij persoon. Brain 61, robot 45, console 56 groen.
- 2026-07-14 — U36b AUDIBLE speech: brain-side TTS (voice.py, OpenAI gpt-4o-mini-tts → PCM b64; robot houdt geen keys) → /robot/speak accepteert audio_b64 → Reachy-adapter resamplet 24kHz→device-rate (float32, push_audio_sample). Begroeting nu GEPERSONALISEERD: pipeline.orchestrate met judgment-context genereert de zin (fallback statisch), gesproken + wave. Nieuw brain-endpoint POST /robot/say {text}. **LIVE geverifieerd: robot sprak hoorbaar Nederlands ({"voiced":true}).** Robot 45, brain 50 groen.
- 2026-07-14 — U32 desktop app (`02f552c`): Electron shell (apps/desktop) — spawns aura-brain (uv, env from infra/dev/.env + desktop defaults: robot at reachy-mini.local:8001, text-first null voice), serves the console dist on :5173, splash → console window, tray, menu (browser/API docs/brain log), single-instance, kills the brain tree on quit. Brain on :8020 (Pollen's "Reachy Mini Control" app squats :8000 on the laptop!). Launched + verified live: health OK, console 200, robot online (Pi service), knowledge tier benign, real OpenAI turn "Hi Jan!" through the stack.
- 2026-07-14 — SSH key installed by owner → U16 FULLY DONE: uv installed on the Pi, repo transferred (git bundle → ~/aura), robot-runtime deployed as systemd service `aura-robot-runtime` (:8001, ROBOT_ADAPTER=reachy, no_media, boot-enabled). Live wave/nod/gesture through our REST API on the Pi ✅. Debugged: stale nohup instance held :8001 → service crash-loop (NRestarts=22) whose init spammed /api/media/release every 10s; killed stale proc, service stable. **Open: daemon media/WebRTC signaling (:8443) not listening → media acquisition fails; needed for live camera (U18-live), voice (U22/U24). Suggest dashboard firmware update + media debug next. U26 (budget guard) now buildable on-Pi.**
- 2026-08-11 — U228 BRAIN-DOCK BREEDTE + EERLIJKE HINT + GEÏSOLEERDE DEMO-STACK: (1) rechterdock default 520→780 (en de brain-tab-bump 600→780): de rail kost 12rem vóór het profiel één pixel krijgt, en de skill-kaarten halen pas twee kolommen boven ~560 contentbreedte — op 1600×1000 gaan de feiten nu op één regel en zijn er 11 zichtbaar i.p.v. 8; App.vue klemt dit op smalle vensters vanzelf terug (CENTER_MIN 320). (2) VideoPanel-hint: "zet een passphrase onder Secure profiles" werd óók getoond als de store al versleuteld was — dan is de oorzaak dat er geen face-embedder geladen is, en stuurde de tekst je naar een vakje dat niet helpt; nu twee takken op `omkLoaded`, en het paneel haalt zelf `fetchTier()` op omdat het op scherm kan staan vóór het brain-paneel ooit geopend is. (3) DEMO-STACK: `KNOWLEDGE_DB_PATH`/`RECOGNITION_DB_PATH` toegevoegd aan de screenshots-job. Beide defaulten naar `./data`, wat in CI leeg is maar op een ontwikkelmachine een ECHTE knowledge-store in de checkout is. Bij het lokaal herdraaien van de blog-screenshots draaide de demo-brain daardoor tegen `./data/knowledge.enc.json`, en een `/setup/secure`-aanroep met een wegwerp-passphrase schreef een nieuwe `data/key-params.json` vóórdat de migratie faalde op InvalidTag. Ciphertext bleef ongemoeid (alle bestanden in `data/` dateren nog van juli, %APPDATA%-store onaangeroerd) en het losse params-bestand is verwijderd — maar dat was geluk in de timing, niet een vangnet. De env-vars zijn het vangnet. Console 88 groen, vite build schoon.
- 2026-08-11 — U229 "DE APP TOONT EEN ANDER PROJECT" (geen corrupte release): eigenaar startte de geïnstalleerde app en kreeg de introductiepagina van een héél ander project (EasyPeasy) in het venster. Diagnose: `serveConsole()` bindt `127.0.0.1:5173`, maar er draaide een Vite-devserver van dat andere project op `[::1]:5173`. Twee adresfamilies = twee sockets, dus onze bind SLAAGT, geen EADDRINUSE, geen foutdialoog — en `mainWindow.loadURL('http://localhost:5173')` laat Chromium op Windows eerst `::1` resolven, dus het venster laadde de buurman. Bestaat sinds U32 (`226fd02`, de eerste desktop-app) en treft dus élke release gelijk; geen enkele build is corrupt en er valt niets te verwijderen — de trigger staat buiten de app. Fix: `CONSOLE_URL = http://127.0.0.1:5173` voor het venster én het tray-menu ("Open console in browser"), `CORS_ORIGINS` krijgt beide schrijfwijzen zodat een mens die `localhost` intikt in een browser niet geblokkeerd wordt. Regressietest `apps/desktop/test-console-origin.cjs` bewijst het mechanisme in plaats van de string: het bindt echt een IPv6-server, bindt daarna dezelfde poort op IPv4, en toont aan dat `127.0.0.1` bij ons uitkomt terwijl `[::1]` bij de ander uitkomt (slaat netjes over als de runner geen IPv6-loopback heeft) + een bronbewaking dat main.cjs de console nooit meer bij naam adresseert. In CI naast de updater-tests gehangen. Desktop-lint + beide testbestanden groen.
- 2026-08-11 — U230 SCREENSHOTS DIE KLOPPEN MET HUN BIJSCHRIFT: (1) 2x capture (deviceScaleFactor) in beide screenshot-scripts — de volledige vensterbeelden gaan alsnog naar 1600 breed, maar de uitsnedes van het brain-paneel zijn ~590 CSS-px breed en worden op ~690 getoond; op 1x kwamen die al onscherp binnen. (2) Nieuwe capture `06e-skills-panel-only`: de volledige-vensteropname van de skills was vrijwel identiek aan de openingsopname van de console (zelfde layout, zelfde dock, ander tabblad), dus de post die OVER skills gaat krijgt nu het paneel op zichzelf. (3) `05-app-logs` fotografeerde het verkeerde paneel: "App logs" is een ringbuffer op de Python-logger en een gezonde run schrijft daar niets in — het bijschrift beloofde "de loops rapporteren" en het plaatje toonde "No log records". Nu de Event Log-dock, waar de loops daadwerkelijk naartoe publiceren (RobotModeChanged, ResponseDrafted met tijdstempel). (4) `blog-offline-shot.mjs` was nooit opnieuw gedraaid na U227/U228: die opname toonde nog het smalle dock met skill-kaarten die per lettergreep afbraken ("desk/top-/ai-/assi/stan/ts") én de inmiddels gecorrigeerde passphrase-hint. Opnieuw vastgelegd met de robot gestopt. Zeven afbeeldingen in de blogserie vervangen.
- 2026-08-11 — U231 REPO KLAAR OM PUBLIEK TE GAAN: (1) `docs/diagrams/` — de acht handgetekende SVG's (trust boundary, één beurt, drie loops, kennismodel, envelope-encryptie, delegatiegrenzen, hook-volgorde, build-loop) plus een README die per bestand zegt wat het toont, waar het gebruikt wordt, én wat je moet bijwerken bij welke soort wijziging; inclusief de huisstijl (1000 breed, 19-22px type, één roestaccent per tekening) zodat een volgende tekening erbij past. (2) **Constitutie-principe IX** toegevoegd ("The Drawings Are Part of the Contract", versie 1.1.0) + dezelfde regel in `AGENTS.md`: een unit die de vorm van het systeem verandert — data over de vertrouwensgrens, wat de approval-gate dekt, de cadans van een loop, node/edge-types, de sleutelhiërarchie, de grenzen van een sub-agent — werkt de bijbehorende SVG bij in diezelfde unit. Een tekening die ooit klopte is erger dan geen tekening, want ze wordt geloofd. (3) README herschreven als introductie in plaats van als naslagwerk: foto van de gebouwde robot, drie screenshots uit de demo-stack (console, profiel, graaf) + de offline-toestand als voorbeeld van hoe een storing eruit hoort te zien, de twee kerntekeningen ingebed, en een **"What you need"**-sectie die de vraag beantwoordt die iedereen zal stellen: je hebt géén robot nodig — zonder robot verlies je precies drie dingen (beweging, camera dus herkenning/gebaren, en kamergeluid), de rest gedraagt zich identiek; met robot expliciet de **Wireless** (Pi + batterij + radio in de robot), want de twee-machine-opzet gaat daarvan uit. (4) De losse "Natural voice conversation (U84)"-sectie verhuisd naar `docs/voice-conversation.md` — dat was een implementatienotitie op een voorpagina. (5) `docs/architecture/overview.md`: de acht tekeningen bovenaan, plus een expliciete waarschuwing dat de mermaid-graven de vijf laptopservices als aparte dozen tekenen terwijl ze sinds ADR-007 in één proces draaien — modules, geen processen. Privacy-scan schoon.
- 2026-08-11 — U234 POORTEN WORDEN OPGELOST, NIET AANGENOMEN (structurele oplossing na U229): U229 nam het symptoom weg (adresseer op IP, niet op naam), maar de oorzaak bleef: **8020 en 5173 stonden vást**, in de Electron-shell én ingebakken in `.env.production` van de console. Draait er iets anders op die poort, dan start de app niet — of erger, praat hij met de buurman. Drie lagen aangepakt. (1) **Console: één plek beslist waar de backend staat.** `src/lib/endpoints.ts` met drie bronnen op volgorde: `window.__AURA_RUNTIME__` (runtime-injectie) → `VITE_*` (buildtijd) → gedocumenteerde default. De vraag "welke poort?" werd op **twintig** plekken los beantwoord met zes verschillende defaults (`:8000`, `:8002`, `:8003`, `:8004`, `:8006`, `:8020`) — restanten van vóór ADR-007 toen de vijf services nog apart draaiden. Alle twintig lopen nu via die ene module; `.env.production` gaat van zes variabelen naar twee, en van `localhost` naar `127.0.0.1` (de IPv6-val zat óók ingebakken in elke build). (2) **Shell: eerst binden, dan spawnen.** `serving.cjs` (uit `main.cjs` gehaald zodat het zonder Electron testbaar is) met `listenPreferring` (gewenste poort, anders eentje die de OS aanreikt), `pickFreePort` (voor de brain, die zijn eigen socket bindt — de race is bewust en eerlijk: verliest hij die, dan faalt de healthcheck luid in plaats van stil met een vreemde te praten) en `withRuntimeConfig` (injecteert de echte endpoints in `index.html`; dát is wat een statische build laat meebewegen met een dynamische poort). Opstartvolgorde omgedraaid: console binden → brain-poort kiezen → brain spawnen met een CORS-lijst die de bestaande console-origin noemt. (3) **Bewijs, geen aanname.** `test-console-origin.cjs` uitgebreid van 2 naar 6 checks: de dual-stack-val, verhuizen bij een bezette poort mét de buurman ongemoeid, een vrije voorkeurspoort ongewijzigd gebruiken, de injectie vóór het app-script, plus twee bronbewakingen (nooit bij naam adresseren; geen vaste poortconstanten meer). Daarnaast een end-to-end-repetitie met **beide** voorkeurspoorten bezet: console → 64278, brain → 64279, de geïnjecteerde config wees naar 64279, en beide buren bleven draaien. Console 88 groen, build schoon, eslint schoon, updater-tests groen.
- 2026-08-12 — U235 v2.0.58 STARTTE NIET — `Cannot find module './serving.cjs'` (regressie van U234, door mij): U234 haalde drie helpers uit `main.cjs` naar een eigen `serving.cjs` zodat ze zonder Electron testbaar werden. Wat ik niet controleerde: `build.files` in `apps/desktop/package.json` is een **expliciete allowlist** (`main.cjs`, `preload.cjs`, `updater.cjs`, `build/**`). De nieuwe module stond er niet in, dus hij ging niet mee de asar in. Vanuit een checkout draaide alles; de geïnstalleerde app viel om op de eerste regel van `main.cjs`. Drie dingen gedaan, in deze volgorde. (1) **Eerst de test geschreven, tegen de kapotte staat**: `test-packaging.cjs` volgt de lokale `require`-keten vanaf `main.cjs` en `preload.cjs` en toetst elk bestand tegen de globs uit `build.files` — hij faalde op precies `serving.cjs`, wat bewijst dat hij de fout vángt in plaats van hem te beschrijven. (2) **Fix**: `files` van drie losse namen naar `*.cjs` + `!test-*.cjs`, zodat een volgende module niet opnieuw vergeten kán worden. (3) **Echt geverifieerd, niet op globs vertrouwd**: `electron-builder --dir` gedraaid en `serving.cjs` uit `app.asar` teruggelezen, plus gecontroleerd dat de verpakte `main.cjs` hem daadwerkelijk requiret. **De diepere oorzaak was het releaseproces zelf**: de release-job draait de Python-suites en de console-suite, maar géén enkele controle op de Electron-shell — precies het ding dat hij bouwt. Die drie desktop-tests draaien nu in de release-job vóór `build` (die `needs: [version, test]` heeft, dus een kapotte shell blokkeert de installer) én in CI. Lint schoon, alle drie de desktop-suites groen.
- 2026-08-12 — U236 DE RELEASE-SCREENSHOTS FAALDEN AL WEKEN, ZONDER DAT IEMAND HET ZAG: bij het controleren van de v2.0.59-build viel op dat de `screenshots`-job faalde. Nagekeken over de laatste zes releases: **allemaal**. Oorzaak: `release-screenshots.mjs` navigeert met `waitUntil: 'networkidle'`, terwijl de console een WebSocket openhoudt voor de event-stream — het netwerk wordt dus nooit idle en de navigatie wachtte simpelweg zijn volle timeout vol. Precies de val die ik in het blog-screenshotscript wél had gedocumenteerd ("wait for content instead") en hier nooit had gerepareerd. Fix: `domcontentloaded` + de bestaande wacht op het conversatiepaneel. **De tweede helft is belangrijker dan de eerste**: de job staat op `continue-on-error: true` met de redenering "een release zonder screenshots is beter dan geen release" — verdedigbaar, maar in de praktijk betekende het dat de fout wekenlang onzichtbaar bleef en elke release stilletjes zonder beeld uitging. De job blokkeert nog steeds niets, maar een ontbrekende set schrijft nu één regel in de release-notes ("_No screenshots in this release: the demo-stack capture did not complete._"). Een afwezigheid die niemand kan zien is geen degradatie maar een blinde vlek.
- 2026-08-12 — U237 SLAAPSTAND HIELD GEEN STAND: "als ik hem op slapen zet gaat hij naar beneden, maar na een paar seconden komt hij weer omhoog". **Oorzaak: slapen bestond alleen als omgevingsvariabele op de laptop** (`ROBOT_ASLEEP` in de brain). De robot-runtime wist van niets — en juist dáár draaien twee lussen die bestaan zodat de robot nóóit bevroren lijkt: de `OfflineBehaviorLoop` (elke **4 s**, precies "een paar seconden") en de idle-fidget-lus in de behaviour-engine (elke 30 s). Beide bewogen vrolijk een robot die net was gaan liggen. Bovendien deed `ReachyRobotAdapter.connect()` onvoorwaardelijk `wake_up()` + `start_head_tracking()`, dus élke reconnect van de maintenance-lus zette hem rechtop. Fix in drie delen. (1) **De robot houdt de staat zelf bij**: nieuw `sleep_state.py` (een module, want de drie consumenten — offline-lus, behaviour-engine, Reachy-adapter — delen geen enkel object) plus `POST/GET /robot/sleep` op de runtime; de brain zet hem via `RobotClient.set_asleep()` **vóór** hij de slaaphouding commandeert. Slapen betekent *neem geen eigen initiatief*; een expliciet commando wordt nog steeds uitgevoerd, want anders werkt de wake-knop niet meer. (2) **Reconnect respecteert het**: motoren wel aanzetten (slapen is een houding, geen uitschakeling), maar `goto_sleep()` in plaats van `wake_up()`, en head-tracking blijft uit. (3) **Wake-word wekt hem**, zoals gevraagd: slapen zet de microfoon niet meer uit, en hoort de voice-lus het wake-woord terwijl hij slaapt, dan roept hij ín-proces dezelfde `wake()` aan als de knop (geen HTTP naar onszelf — dat zou de poort moeten raden die U234 juist wegnam). Wie liever een dove slaapstand heeft: `SLEEP_KEEPS_EARS=false`. **Tests eerst tegen het kapotte gedrag**: 5 nieuwe tests in `test_sleep_state.py` die het gedrág toetsen (bewoog de robot?), niet de vlag; met de guard eruit falen er precies 2 — de twee die de gemelde klacht beschrijven. Robot-runtime 94 groen, brain 346 groen, ruff schoon.
- 2026-08-12 — U238 "AWAKE/ASLEEP DOET NIETS MEER" — mijn regressie van U237, en een principiëlere fout dan het symptoom: U237 liet de brain `POST /robot/sleep` aanroepen op de runtime, als **eerste** stap in hetzelfde try-blok als de slaaphouding. **Gemeten op de echte robot** (niet beredeneerd): `reachy-mini.local:8001` antwoordt `404` op die route — de Pi draait nog code van vóór vanmiddag, want de laptop update zichzelf en de Pi wordt met de hand uitgerold. Gevolg: `raise_for_status()` gooide op regel één, `set_tracking(False)` en de slaap-motion draaiden nooit, de `except` slikte alles, en het endpoint gaf vrolijk `{"asleep": true}` terug. De app meldde succes terwijl de robot letterlijk niets deed. Fix: `set_asleep()` geeft nu `False` terug bij een 404 (met een logregel die zegt wat er aan de hand is) in plaats van te gooien, en staat in `sleep()`/`wake()` in een **eigen** try, zodat de houding en tracking altijd draaien. Het antwoord draagt nu `stays_down`, zodat de app kan zeggen dat dit de mindere slaap is — zonder de runtime-helft staat de robot binnen vier seconden weer op. 3 tests (`test_sleep_deployment_skew.py`) die tegen de gepubliceerde vorm falen en tegen de fix slagen. **Structureel**: constitutie-principe **X — "The Two Hosts Update Separately"** (versie 1.2.0) plus dezelfde regel in `AGENTS.md`: een brain die nieuwer is dan zijn runtime is de nórmale toestand van dit systeem, dus elke later toegevoegde brain→runtime-aanroep is optioneel, staat in een eigen try, en meldt de degradatie in plaats van blanco succes. Precedent dat het wél goed deed: U195 (camera-route met probe en terugval). Brain 349 groen, robot-runtime 94 groen, ruff schoon. **Let op: de volledige fix van U237 vereist een herdeploy van de Pi** — tot dan gaat hij netjes liggen maar komt hij vanzelf weer omhoog.
- 2026-08-12 — U239 PI HERUITGEROLD (U220 → U238): de robot draaide nog code van **74 commits geleden** — de laptop update zichzelf, de Pi werd sinds 14 juli met de hand gevoed. Daarmee was principe X geen theorie maar de dagelijkse toestand. Uitgerold via git bundle (2,5 MB) → `git fetch` + `reset --hard` in `~/aura`, rollbackpunt weggeschreven naar `~/aura-rollback.sha` (`b125add`) zodat terugvallen één commando is. **Eén valkuil gevonden vóór de herstart, niet erna**: `uv sync --package robot-runtime` snoeit de omgeving terug tot de basisdependencies en gooide de `reachy-mini`-SDK eruit — een herstart op dat moment had de robot offline gehaald. De draaiende service overleefde het (de import zat al in het geheugen), en `--extra reachy` zette hem terug; de commentaarregel in `pyproject.toml` zegt dit ook letterlijk, ik had hem alleen niet gelezen. Daarna herstart: service `active`, `NRestarts=0`. **Geverifieerd op de echte robot**: `/robot/sleep` bestaat nu (was 404), en met slaap aan 16 metingen over 32 seconden — langer dan de offline-lus (4 s) én de idle-fidget (30 s) — allemaal `behavior_state=idle`, nul bewegingen, en de runtime hield zijn staat vast. Daarna weer wakker gezet. Wat ik hiermee **niet** heb geverifieerd: camera, audio en spraak op de nieuwe runtime — die 74 commits raken ook het camerapad (U188/U195/U219) en dat kan alleen de eigenaar met eigen ogen en oren bevestigen.
- 2026-08-12 — U240 GUARDRAILS TEGEN DEPLOY-DRIFT (na U239): de Pi stond 74 commits achter en niets in het systeem kón die vraag beantwoorden — dus stelde niemand hem, en het eerste teken was een 404 die een knop stil liet doen alsof (U238). Vier lagen, van "meten" naar "niet meer hoeven onthouden". (1) **De robot zégt wat hij draait**: `build_info.py` leest zijn eigen git-SHA + commitdatum + dirty-vlag en `/health` draagt dat mee. Ontbreekt git (wheel-installatie), dan zegt hij dat eerlijk in plaats van te gokken. (2) **De brain vergelijkt élke onderhoudstick** (elke 5 min) via `deploy_skew.compare()` — op commit, niet op tellen, want de twee hosts delen geen betrouwbare klok en de Pi-historie is ooit herschreven; alles wat geen string-SHA is heet `unknown`. Bewust een **melding, nooit een weigering**: een oudere robot werkt meestal prima, en een versiecheck die dienst weigert is een ergere storing dan de drift die hij voorkomt. (3) **`scripts/deploy_robot.py`** met `--check` / deploy / `--rollback`: weigert bij een vuile working tree (anders draait de robot code die nergens anders bestaat), schrijft eerst een rollbackpunt op de Pi, en **verifieert dat de reachy-SDK importeerbaar is vóór de herstart** — precies de val van U239, nu vastgelegd op het enige moment waarop hij nog gratis is. (4) **Skill `.claude/skills/deploy-robot`** zodat een volgende sessie de procedure niet opnieuw hoeft af te leiden, inclusief beide vallen en wat je ná een deploy níét mag claimen (camera/audio hebben ogen en oren nodig). **Twee dingen die de tests vingen, allebei van mij**: een niet-string commit liet `compare()` omvallen — ín de onderhoudslus, die alles bewaakt — en `robot_build` in `checks` zette `healthy=false` op een verder gezond systeem, wat het waarschuwingslampje permanent aan zou hebben gezet. Drift staat nu in `actions` ("hier is iets te doen") in plaats van in `healthy` ("er is iets kapot"). Brain 357 groen, robot-runtime 94 groen, ruff schoon.
- 2026-08-12 — U241/U242 DE ROBOT UPDATET ZICHZELF: het sluitstuk op U240 — drift zichtbaar maken is goed, hem niet meer laten ontstaan is beter. Systemd-timer op de Pi (uurlijks, met spreiding) die **release-tags** volgt, dezelfde cadans als de desktop-app; nu de repo publiek is heeft de Pi geen sleutel of laptop meer nodig. Vier regels, elk het verschil tussen een onbewaakte update en een onbewaakte storing: (1) alleen tags, nooit master — de robot mag geen commit volgen die negentig seconden waar was; (2) nooit midden in een zin: een herstart knipt audio en beweging af, dus hij wacht op een idle robot en probeert het volgend uur weer; (3) altijd `--extra reachy`; (4) verifiëren ná de herstart en **zichzelf terugrollen** als de robot niet terugkomt. Opt-in via `--enable-auto-update`, want iets dat ongevraagd een bewegende machine in iemands huiskamer herstart hoort een beslissing te zijn. **Twee bugs die alleen een echte test kon vinden.** (a) Ik zette de robot één release terug om hem te zien klimmen — en het updatescript wás verdwenen, want het zat in de release die hij niet meer had. Het enige dat achterlopen moet overleven is het ding dat achterlopen repareert; het script installeert nu in `/usr/local/bin` en de unit draait díé kopie, die na een gezonde update ververst wordt. Dezelfde fout in het klein: `git reset --hard` vervangt bestanden terwijl bash het draaiende script nog regel voor regel leest. (b) Daarna faalde het met `env: 'bash\r': No such file or directory` — mijn Windows-checkout leverde CRLF via `scp` (de git-uitrol normaliseerde dat wél). Opgelost op twee plekken: een `.gitattributes` die `*.sh`, `*.service`, `*.timer` en de Python/YAML op LF pint, én normalisatie bij het kopiëren, want scp kopieert bytes en geen bedoelingen. **Live geverifieerd**: robot op `099fb33` gezet, timer gestart, en hij klom in 17 seconden zelf naar `v2.0.66` — update available → rollbackpunt → checkout → sync → sdk-check → herstart → gezond. Daarna `--check`: in step, `NRestarts=0`, en de slaapstand houdt nog steeds stand (32 s, nul bewegingen).
- 2026-08-12 — U243 "WAAROM STUURT AURA STEEDS BERICHTEN?" — vijf keer "Hoi hoi! Zullen we iets leuks doen?" in negen minuten, hardop, tegen een kind dat nergens heen was gegaan. Tussenpozen: 120s, 146s, 121s, 166s — de ondergrens exact `GREET_COOLDOWN_S=120`. **Twee fouten die elkaar versterkten.** (1) *De begroeting hing aan een cooldown in plaats van aan een aankomst.* Een cooldown beantwoordt "hoe lang geleden groette ik je" terwijl de vraag is "ben je net binnengekomen" — dat is hetzelfde antwoord alleen als mensen ook wéggaan. De gezichtsdetector verliest en hervindt dezelfde persoon voortdurend (wegkijken, een gemist frame, omdraaien), elke hervinding is een nieuwe `PersonRecognized`, en zodra de cooldown verliep mocht hij weer groeten: een metronoom. Nu `greeting_policy.py`: groeten bij aankomst — de eerste waarneming ná een échte afwezigheid (`GREET_ABSENCE_S`, standaard 10 min), met de oude cooldown alleen nog als ondergrens tegen pathologisch geflikker. Waarnemingen tijdens onderdrukking (slaapstand, stille persona) tellen mee als aanwezigheid, anders is een uur slapen een uur "afwezig" en groet hij bij het wakker worden. (2) *De persona-begroeting was een script.* `greeting_message` van Kids Companion werd letterlijk uitgesproken, wat elke hallo woordelijk identiek maakte — het meest robotachtige gedrag in een app die daar juist niet op wil lijken; het omzeilde bovendien de gevarieerde begroetingen van U85. Nu gaat die zin als **toon** naar het model ("match that warmth and register, but do NOT repeat it verbatim") in plaats van als tekst. 9 tests op de policy, waaronder één die de gemelde tijdstempels letterlijk afspeelt en vastlegt dat er nu één begroeting uitkomt in plaats van vijf. Brain 363 groen, ruff schoon.
- 2026-08-12 — U244 TIEN GEZICHTEN ZONDER PERSOON (het lek, de rommel, en waarom het niet alleen slordig was): de matcher kende twaalf gezichten (`jan`, `jappe`, `guest-1` t/m `guest-10`), de kennisbank kende vier mensen — alle tien de guests gaven 404. Ze waren automatisch aangemaakt door U181 en later door de eigenaar verwijderd, maar **`DELETE /knowledge/people/{id}` wiste het profiel en de snapshots en liet het gezicht staan**. Twee soorten schade, en de tweede is de ernstigste. (1) *Herkenning*: `identify()` neemt de beste cosine-score over ÉLK ingeschreven gezicht; een wees die ooit van de eigenaar onder een rare hoek is ingeschreven kan diens eigen samples verslaan. De pipeline krijgt dan een id dat naar niemand verwijst, `JudgmentLayer.build_context()` geeft `None` terug, en er gaat geen enkele persoonlijke context de prompt in — terwijl de console vrolijk de laatst geziene naam blijft tonen. (2) *Wissen*: een face-embedding is biometrie. Een profiel verwijderen en de embedding laten staan, nog steeds ontsleutelbaar onder de owner key, is geen erasure — dat is precies wat ADR-008 §9 belooft en hier niet gebeurde. Fix in twee lagen: het verwijderpad vergeet nu ook het gezicht (het lek), en `face_reconcile.py` ruimt bij het starten van herkenning op wat het lek al had gemaakt (de rommel). **De gevaarlijke rand is expliciet afgeschermd**: een store die nul mensen teruggeeft is veel waarschijnlijker eentje die nog niet geladen is dan een huis waar iedereen gewist is, dus bij een lege lijst wordt er niets gedropt — de kosten van die verwarring zijn elk gezicht in huis, zonder weg terug. 7 tests, waarvan er één (`test_deleting_a_person_also_erases_their_face`) tegen de gepubliceerde vorm faalt op precies de weggehaalde regel. **Live opgeruimd**: 12 → 2 ingeschreven gezichten, `jan` en `jappe` behouden, herkenningslus bleef draaien. Brain 372 groen, ruff schoon.
- 2026-08-12 — U245 DE SPRAAKWEG WIST NIET WIE ER STOND: gemeld met een screenshot waarop Richie om 19:58 "Hey Jan! Hoe was je dag?" zegt en om 20:07 tegen dezelfde persoon "Ik heb geen herinneringen aan wie iemand is buiten dit gesprek". **Beide antwoorden waren eerlijk — ze kwamen uit twee verschillende plekken.** De begroeting hangt aan `PersonRecognized` en loopt door de turn-pipeline, die via de JudgmentLayer "Talking to: Jan (owner)" plus zijn facts in de systeemprompt zet. De gesproken beurten liepen door een **Realtime-sessie** (het badge in de console telde ze: 3 turns, precies de drie beurten in het gesprek), en die kreeg in `voice_loop.py` letterlijk `instructions = character.character_prompt` — het karakterprompt van Richie en verder niets. Geen judgment layer, geen persona-systeemprompt, geen skills, geen live context. Het model wist het écht niet en zei dat ook. In het log staat het sluitstuk: om 20:08:17 `realtime session failed, using pipeline`, en vanaf dat moment kende hij hem weer. **Oorzaak achter de oorzaak**: die vier regels persoonlijke context stonden inline in de pipeline, dus een tweede pad kón er niet bij. Nu `OrchestratorPipeline.person_note()` — één publieke vraag met één antwoord, gebruikt door de getypte én de gesproken weg, zodat ze niet opnieuw uit elkaar kunnen lopen. De note komt bewust via de JudgmentLayer en niet uit de facts rechtstreeks, want dáár zitten de rolregels (een gast krijgt alleen een naam, een minderjarige alleen expliciete facts en nooit observaties — ADR-008 §10), en juist op dit pad stond "Kids Companion" aan. `voice_context.build_instructions()` plakt karakter en persoon aan elkaar: karakter eerst (wie hij ís), de persoon achteraan waar recency helpt, en expliciet gelabeld als eigen kennis — zonder dat kader leest het model een blok als iets dat de gebruiker net beweerde en gaat het hedgen, precies het gedrag uit de melding. **Een sessie leeft minuten, dus vastzetten bij het openen is niet genoeg**: `RealtimeSession` krijgt een `instructions_provider` die elke 5 s opnieuw gevraagd wordt (`REALTIME_CONTEXT_REFRESH_S`, 0 = uit) en alleen een `session.update` stuurt als de tekst écht veranderde — anders wordt er bij elke tick identieke ruis over de socket gepompt, en de note kost een ontsleuteling. Een provider die stukloopt kost de persoonlijke helft, nooit de sessie. 14 tests op de spraakweg + 5 op `person_note()`; met de gepubliceerde regel teruggezet falen er precies twee, de twee die de melding beschrijven. Geen tekening werd onwaar (geen enkele SVG doet een uitspraak over wat een Realtime-sessie te horen krijgt) — maar dát er twee paden naar een antwoord lopen staat nergens getekend, en dat is de volgende. Brain 384 groen, orchestrator 226 groen, ruff schoon. **Werkt pas na een herstart van de app.**
- 2026-08-12 — U246 DRIE KAPOTTE DINGEN, ÉÉN ONTBREKEND WOORD: op één avond gemeld dat (a) "speel radiohead op spotify" alleen Spotify opende en hervatte wat er al klaarstond, (b) "vraag het aan Claude" strandde op "het openen van de Claude-app lukte niet", en (c) "zoek het op in Chrome" alleen een Chrome-venster opstartte. Drie skills, drie domeinen, dezelfde muur: élke stap die een échte applicatie bedient loopt via `use_computer`, en die stond uit — `Computer Use enabled but backend unavailable (No module named 'pyautogui')`. **Oorzaak: `uv sync` snoeit wat je niet vraagt.** De bootstrap in `main.cjs` draaide `uv sync --all-packages --extra recognition`; pyautogui zit in de **`computeruse`**-extra, die nooit gevraagd werd, dus een installatie die hem ooit had raakte hem kwijt bij de eerstvolgende sync. Vandaar "vroeger kon hij dit nog" — dat was geen inbeelding maar een gepruned pakket. Exact dezelfde val als U239 op de Pi (`--package robot-runtime` gooide de reachy-SDK eruit) en als de recognition-extra daarvóór; derde keer, dus nu met een test in plaats van nóg een commentaarregel. Fix in drie delen. (1) De sync vraagt beide extra's, met **drie sporten** in plaats van twee: eerst beide, dan alleen recognition, dan kaal — want een wheel die niet bouwt in `computeruse` mag de gezichtsherkenning niet meeslepen. (2) De "al gebootstrapt"-controle keek alleen naar het markerbestand plus insightface; nu ook naar pyautogui, anders geneest een gesnoeide venv nooit — precies waarom deze installatie maandenlang zonder bleef draaien. `BOOTSTRAP_REV` naar 4, zodat bestaande installaties de sync één keer opnieuw doen. (3) `test-bootstrap-extras.cjs`: een tabel van elke extra plus één importnaam die bewijst dat hij geland is, met de eis dat één sync ze állemaal vraagt, dat de kale terugval blijft bestaan, én dat de skip-check elke extra controleert. Faalt tegen de gepubliceerde vorm, slaagt op de fix; in CI en in de release-job naast de andere desktop-tests. **Wat dit NIET oplost**: de muziekconnector staat nog op mock (geen `SPOTIFY_ACCESS_TOKEN`), dus `play_music` blijft het eerlijke NOT_PLAYED_VIA_API-antwoord geven en de weg naar echte Spotify loopt voorlopig via schermbesturing. Vier desktop-suites groen.
- 2026-08-12 — U247 DE LEERLUS NOTEERDE BEDOELINGEN, NOOIT UITKOMSTEN: aanleiding was de vraag "hoe zorg ik dat hij dit zelf leert?" na U246 — drie skills die avond doodliepen op dezelfde ontbrekende capability, terwijl de zelfoptimaliserende lus (U107) er dwars doorheen had gedraaid zonder er iets van te kunnen leren. **De ledger bestond al** (`skills/.metrics/<naam>.jsonl`, één regel per gebruik, cap 200) — hij noteerde alleen het verkeerde. Twee fouten. (1) *De regel werd geschreven vóórdat de beurt draaide*, met alleen het verzoek erin. De optimizer-prompt vraagt letterlijk om "guardrails for the failure/edge cases implied by the usage evidence", tegen bewijs waarin nooit iets mislukt. (2) *De helft van dat bewijs ging nergens over*: op de machine van de eigenaar waren **4 van de 7** geregistreerde "uses" van de Spotify-skill de robot die iemand begroette — begroetingen lopen via dezelfde `pipeline.orchestrate()`, matchen dus dezelfde triggers, en werden geboekt als gebruik van een skill waar ze niets mee te maken hebben. Vier delen. (a) `from_user=False` voor beurten die het *systeem* start (begroeting, presenter-beat, en de teach-frame — daar zou onze eigen boilerplate als "verzoek" in de ledger belanden); alleen echte vragen tellen. (b) De regel wordt ná de beurt geschreven, met de tools die draaiden en de capabilities die "kan niet" teruggaven; per beurt in een `trace`-dict meegegeven en niet op `self`, want beurten lopen door elkaar. (c) **`shared_schemas/tool_outcome.py`**: twee capabilities gaven onbeschikbaarheid als *proza* terug (`use_computer: not available` en de mock-muziekconnector), en proza is alleen leesbaar voor het model — voor de event-log, de observaties en de optimizer zag zo'n aanroep er identiek uit aan een geslaagde. Nu een expliciete `CAPABILITY_UNAVAILABLE:<naam>`-marker vóór dezelfde zin: het proza blijft precies zoals het was (dát is wat het antwoord eerlijk maakt), de classificatie is greppbaar in plaats van geraden uit bewoordingen die morgen anders staan. Meteen ook de mock-antwoorden eerlijker gemaakt: "Paused the music (mock)" → "Nothing was paused (mock)", want er werd niets gepauzeerd. (d) `summarize_observations` zet de mislukkingen **bovenaan** met een telling ("music: 2 of 3 uses hit this and stopped there") plus de instructie dat de optimizer om de ontbrekende capability heen mag schrijven of hem netjes moet weigeren — precies het gedrag dat in de melding ontbrak. **Retentie**: die regels citeren de eigenaar woordelijk en de aantal-cap bijt nooit bij een skill die zeven keer per jaar draait, dus er staat nu ook een termijn op (`SKILL_OBS_MAX_AGE_DAYS`, 180; 0 = uit). 17 tests, waarvan er twee tegen het gepubliceerde gedrag falen: de begroeting die een regel schreef, en de regel die geen uitkomst droeg. Eén bestaande test (`test_pipeline_beat_routes_through_the_agentic_loop_silently`) ving mijn signatuurwijziging via zijn fake — die legt nu vast dát een presenter-beat `from_user=False` is. Brain 384, orchestrator 243, connector-service 42, schemas 142 groen, ruff schoon. Geen tekening werd onwaar; de skill-leerlus staat in géén enkele SVG, wat op zich iets zegt.
- 2026-08-15 — U248 "IK GA NU CHROME OPENEN — EVEN GEDULD" WAS HET HELE ANTWOORD: gemeld met tijdstempels die de diagnose zelf doen. 00:19:16 vraag, 00:19:17 antwoord — één seconde, terwijl `launch_app` goedkeuringsplichtig is (dan was er een dialoog geweest) en `use_computer` tien seconden of meer kost. Er draaide dus **niets**; de beurt eindigde op een aankondiging en de pipeline was het ermee eens, want een modelantwoord zonder tool-calls beëindigt de lus ongeacht wat er staat. Dat is de spiegel van het thema van dit project: stil falen is erg, **aangekondigd slagen dat nooit gebeurde is erger**, want de eigenaar loopt weg in de overtuiging dat er iets loopt. Vier oorzaken, alle vier aangepakt. (1) *De skill loog.* `desktop-chrome` stap 1 zei woordelijk "There is no open-a-URL tool, so navigation itself needs use_computer" — maar `open_browser_url` bestáát, en de automatiseringsladder in de systeemprompt noemt hem als laag 4 mét de instructie "never start at the GUI". Twee tegenstrijdige verhalen; het model koos geen van beide en beloofde iets. Skill herschreven: URL zelf bouwen (`google.com/search?q=…`) en openen, één aanroep in plaats van drie stappen met een screenshot. (2) *Die laag bestond alleen op papier.* `open_browser_url` praat via het DevTools-protocol en een normaal gestarte Chrome luistert daar niet — live geverifieerd, de tool gaf netjes "Chrome is not reachable on its debug port". In `ALLOWED_APPS` stond `chrome=cmd /c start chrome`; nu mét `--remote-debugging-port=9222`. Eerlijk erbij in de skill én in de code: dit werkt alleen als AURA Chrome zélf start, want Windows hergebruikt een al draaiende Chrome met diens oorspronkelijke vlaggen. (3) *En dat falen was onzichtbaar* — het antwoord van de browserconnector was proza, net als de mock-muziek vóór U247; nu gemarkeerd als `CAPABILITY_UNAVAILABLE:browser`, zodat de skill-ledger het ziet. (4) **De structurele**: `promise.py` + een terugduwing in de lus. Eindigt een beurt met een zin die een handeling aankondigt terwijl er die beurt geen enkele tool draaide, dan is dat geen geldig eindantwoord — één extra ronde met een expliciete opdracht: doe het nu, of zeg klip en klaar dat het niet kan, benoem wat er ontbreekt, en stel de kleinste concrete ingreep voor. Precies één keer, zodat een model dat blijft beloven de lus niet kan laten rondtollen. De detectie is bewust smal: alleen op beurten waarin níéts draaide (een verslag van echt werk kan hem dus nooit triggeren) en een **aanbod is geen belofte** — "Zal ik Chrome openen?" is juist het goede antwoord als hij niet kan, en wordt met rust gelaten. Tot slot een alinea in de ladder over wat te doen bij een onbeschikbare laag: klim één stap, beloof nooit wat je niet deed, en vráág om wat je mist. 22 tests, waarvan er drie tegen het gepubliceerde gedrag falen. Brain 384, orchestrator 265, connector-service 42 groen, ruff schoon. **Let op: de gewijzigde skill zit in `skills/` van de repo; de kopie in %APPDATA% van een bestaande installatie wordt niet overschreven.**
- 2026-08-15 — U249 DE ASSISTENT MAG NU VRAGEN OF HIJ GEDEBLOKKEERD MAG WORDEN: gevraagd na U248 — "ik wil dat hij hieruit leert, naar oplossingen zoekt, en approval vraagt wanneer hij buiten zijn grenzen moet; ik wil begeleiden en corrigeren, maar hij moet er zelf uit komen". Alles wat deze week misging stond één schakelaar van werkend af: schermbesturing uit de omgeving gesnoeid (U246), Chrome zonder debug-poort (U248), muziek zonder token. Drie keer liep hij ertegenaan en drie keer kon hij er niets zinnigs over zeggen, **want de approval-gate kent maar één soort vraag: "mag ik dit doen wat ik al kan?"** Er was geen vorm voor "ik zit vast, dit is de kleinste ingreep, mag dat?". Drie delen. (1) **`unblocks.py` + de `request_capability`-tool.** De assistent kiest een *entry uit een catalogus* — nooit een sleutel, nooit een waarde. Hij kan geen instelling samenstellen, geen key noemen die er niet in staat, en levert überhaupt geen waarde aan. Dat is geen theoretische voorzichtigheid: **U215 was exact deze vorm** — een instelwaarde met een newline schreef een EXTRA env-regel en maakte `POST /setup/prefs` tot een persistente RCE bij de volgende start. Modelwaarden raken het env-bestand nooit meer; de test probeert letterlijk die vier aanvalsvormen, inclusief de newline-injectie, en eist dat er niets geschreven wordt. De tool staat in `APPROVAL_REQUIRED` (hardst gegate van allemaal, want dit is het enige verzoek dat zijn eigen grenzen kan verleggen) en in **élke** modus — een modus die niet kan vrágen is een modus die stilvalt bij een muur, precies het gedrag dat we wegwerken. Goedgekeurd betekent: meteen actief (niet na een herstart) plus de zin hoe je het terugdraait; heeft de ingreep mensenhanden nodig (Spotify-koppeling, Chrome opnieuw starten), dan zegt hij exact wát de eigenaar moet doen. (2) **De trigger kijkt naar falen, niet naar populariteit.** `/skills/suggestions` telde alleen gebruik, en dus stond op deze machine de Spotify-skill op de verbeterlijst (9 uses, werkt) en de Chrome-skill niet (2 uses, beide geblokkeerd) — precies andersom. `metrics()` telt nu de recente beurten die op een ontbrekende capability strandden; twee is genoeg, en falende skills staan bovenaan mét reden. (3) **Jouw correctie verdampt niet meer.** `steer()` injecteerde je zin in de volgende ronde en gooide hem weg — geen enkel spoor, dus begeleiden stapelde nooit op en dezelfde fout kwam morgen terug. Een steer landt nu in de ledgerregel en staat in de optimizer-samenvatting **bovenaan**, boven de mislukkingen: de eigenaar die in eigen woorden zegt hoe het had gemoeten is het sterkste bewijs dat er bestaat. 15 tests, plus 22 van U248. Orchestrator 280, brain 384, shared-policies 6 groen, ruff schoon.
- 2026-08-15 — U250 HIJ MELDT ZICH NU ZELF, EN STELT ZO NODIG EEN NIEUWE SKILL VOOR: sluitstuk op U247-U249. Alles wat hiervoor nodig was bestond al — U107 kon een herschrijving voorstellen, U247 gaf hem écht bewijs om uit te schrijven, U249 leerde de trigger falen zwaarder te wegen dan populariteit. Wat ontbrak was het kleinste stuk en precies dat wat de eigenaar vroeg: **niemand keek ooit**. Het voorstel wachtte achter een knop, dus een skill kon elke dag op dezelfde stap sneuvelen zonder dat er iets gezegd werd. (1) **`skill_review.py` — het beslissen, los van het doen.** Pure functies op tellingen, dus "verdient dit de aandacht van de eigenaar" is te testen zonder model, klok of console. Twee soorten voorstel: een HERSCHRIJVING van een skill die blijft misgaan, en een NIEUWE skill voor iets dat herhaaldelijk gevraagd wordt en dat niets afdekt. (2) **De onderhoudstick kijkt.** Die vraagt elke vijf minuten toch al "hoe staat het ervoor"; nu kiest hij daar hooguit ÉÉN ding uit om aan te kaarten, schrijft het uit en publiceert het als vraag (`SkillProposalRaised`). Drie regels tegen ruis: één tegelijk (een lijst van vijf is een backlog, één met een reden is een vraag die je kunt beantwoorden), een cooldown per onderwerp van 24 uur (anders wordt één signaal twaalf onderbrekingen per uur en leert de eigenaar ze te negeren), en — onveranderd sinds U59 — **er wordt nooit iets opgeslagen**; de eigenaar past het toe via het gewone opslagpad. "Niets te veranderen" is een geldig antwoord en onderbreekt niet, maar consumeert wél het bewijs, anders staat dezelfde skill bij elke tick weer in de rij. (3) **Nieuwe skills beginnen bij wat je vroeg en niets afdekte.** Verzoeken die géén skill raakten lieten tot nu toe geen enkel spoor, dus iets dat je elke week vraagt zonder procedure erachter was onzichtbaar. Die gaan nu in een `_unmatched`-log (zelfde cap en vervaltermijn als de rest; de naam kan niet botsen met een skill omdat `_NAME_RE` een leidende underscore verbiedt), en een bewust grove clustering op inhoudswoorden zoekt herhaling — iets slimmers zou een gelijkenismodel zijn waarvan niemand de fouten kan uitleggen, en de uitvoer hier is een suggestie die een mens leest. `worth_adding: false` is een echt antwoord en het gewone: de meeste herhaalde formuleringen zijn een gesprek, geen procedure, en een lus die elke keer een skill produceert bedelft de eigenaar — dezelfde fout als nooit vragen. (4) **De console laat het verschil zien**: "+9" op een werkende skill en "+2" op een kapotte zagen er identiek uit, wat precies is hoe de kapotte onzichtbaar bleef; een geblokkeerde skill leest nu als "2× blocked" met de reden in de tooltip. 27 tests (16 op het beslissen, 11 op het doen), waarvan er zes falen tegen het gepubliceerde gedrag. **Eén echte bug van mij die de suite ving**: `_topic_words` geeft een SET terug, en de iteratievolgorde van strings in een set verschilt per proces (hash-randomisatie) — via de Counter koos `most_common()` daardoor bij gelijke stand een andere winnaar per run. Een voorstelgenerator die vandaag "hockey" zegt en morgen "geven", op identieke invoer. Nu deterministisch gesorteerd, met een expliciete tiebreak op lengte, en een test die het in vijf losse processen naast elkaar legt. Orchestrator 295, brain 395, schemas 142, console 88 groen, ruff schoon, vite build schoon.
- 2026-08-15 — U251 EEN VOORSTEL DAT BLIJFT WACHTEN, EN ÉÉN KLIK OM JA TE ZEGGEN: U250 liet de assistent zelf een skill aankaarten en publiceerde dat op de event-bus. Dat bereikt een console die toevallig openstaat — en de onderhoudstick draait de hele dag elke vijf minuten, terwijl de eigenaar 's avonds tien minuten in de app kijkt. **Elk voorstel bestond dus precies zolang als het kostte om over de bus te gaan.** Voor een herschrijving viel dat nog mee (die kwam via `/skills/suggestions` alsnog boven), maar een concept voor een NIEUWE skill zat alleen in dat event: de volledige tekst schoot voorbij en was weg. Drie delen. (1) **`proposal_inbox.py`** — een klein wachtvak in het geheugen, expres géén database: het houdt een handvol openstaande vragen vast, niet een geschiedenis, en het verliezen ervan bij een herstart is correct want de tick kaart alles wat nog wáár is opnieuw aan. Twee regels erin: een onderwerp dat al op je bord ligt komt er nooit een tweede keer bij (bij een nieuw concept wordt de kaart vervángen, niet gestapeld), en er staan er hoogstens vijf open — meer is een backlog, en een backlog wordt in zijn geheel genegeerd. De proposer vraagt dat wachtvak nu vóór hij begint, dus na een herstart betaalt hij niet opnieuw voor een concept dat al klaarligt. (2) **`GET/DELETE /skills/proposals`**, gedeclareerd vóór `/{name}` zodat het pad niet door de skill-naam wordt opgeslokt — dezelfde val die `/suggestions` ooit had. (3) **De kaart in de console**, met drie antwoorden. "Add this skill" maakt hem aan uit het concept; "Apply rewrite" verandert alleen de procedure en laat triggers, persoon en persona's van de bestaande skill staan; en **"Edit first"**, dat er evenveel toe doet als de andere twee — een concept geschreven uit drie van je eigen zinnen is een goed startpunt en zelden het eindproduct, en iets goedkeuren dat je in zijn geheel moest slikken is hoe je eindigt met skills die je niet herkent. Bij alle drie verdwijnt de vraag uit het wachtvak; alleen bij de eerste twee wordt er iets opgeslagen. 8 console-tests (waarvan er zeven falen tegen het gepubliceerde gedrag) + 11 op het wachtvak. **Eén ding dat de suite ving**: het wachtvak is procesbreed, dus de U250-tests werden volgordeafhankelijk — de tweede vond de vraag van de eerste nog open staan en zweeg terecht. Dat is in productie precies goed en in tests een isolatiefout; opgelost met een autouse-fixture. Brain 406, orchestrator 296, console 96 groen, ruff schoon, vite build schoon.
- 2026-08-17 — U252 ÉÉN OPPERVLAK (de D2-console, en wat de dekkingswandeling nog vond): de complete console herbouwd naar het D2-ontwerp uit `design_handoff_aura_console_d2/` — één accent (AURA-groen, de vierkleurenkiezer is weg; `--present`-paars is een betekenis, geen voorkeur), IBM Plex zelf meegeleverd, licht warm papier / donker diep groen, een 52px-header waarin **Mode zwaarder weegt dan detailniveau** en Stop altijd op dezelfde plek staat. Panelen en modals werden acht views achter een inklapbare rail; de dockbare panelen en de eigen vensterknoppen zijn bewust NIET meegekomen (de detailknop vervangt het slepen, en de OS-titelbalk is van het OS — `frame:false` uit main.cjs, anders was het venster na het schrappen van TitleBar.vue niet eens meer te verslepen). Het waardevolste stuk zit onder de motorkap: **de modus-chips liegen niet meer.** `mode_policy.py` leidt per modus en per gereedschapsgroep allows/asks/blocked af uit de échte `MODE_TOOL_MAP`+`APPROVAL_REQUIRED` — en dus toont home géén mail, wat het ontwerp ook tekende. Eén regel die een middag kostte: **een afgeleide status is een samenvatting, alleen een expliciete keuze van de eigenaar heeft tanden.** De eerste versie liet een afgeleid "asks" de hele groep gaten — waarna de voltooide testsuite massaal in approval-timeouts bleef hangen; die hang staat nu als docstring op de test die de regel vastpint. Overrides landen in `mode-policy.json`, per-modus persona/stem/geheugen verhuisden uit env-vars naar de instellingen, en de moduswissel schakelt eindelijk óók de persona-manager. De dekkingswandeling langs alle 68 rijen van de Coverage Review vond drie gaten die de herbouw stilletjes had laten vallen — de model-per-taakrol (U90), de Slack-koppeling, en de live Realtime-kostenmeter (U129) — alle drie alsnog een huis gegeven (Settings › Intelligence, Settings › Connections, Talk-presence op Full). Nieuw t.o.v. het oude oppervlak: de zeven-staps wizard (met de eerlijke lege scanstaat, drie voorwaarden op volgorde van waarschijnlijkheid, en "doorgaan zonder robot" als gelijkwaardige keuze), de Mind-canvas op echte busevents, de kennisgraaf met camera-overdracht bij de eerste sleep, en "Wie typt er?" zodra er getypt wordt zonder gezicht. Live geverifieerd tegen een geïsoleerd demo-brein: chips uit `GET /orchestrator/policy`, moduswissel herkleurt, echo-beurt rondt, override overleeft een refetch, ↺ wist hem, beide thema's. Brain 406, orchestrator 319 (23 nieuw op mode_policy), console 94, ruff schoon, vite build schoon.
- 2026-08-17 — U252b DE TITELBALK HOORT BIJ DE APP, EN DE HAND AAN DE CAMERA WAS KWIJT (feedback op U252): drie dingen, alle drie gemeld met een screenshot van de native menubalk "AURA | View" erboven. (1) **Geïntegreerde titelbalk terug**: `frame:false` opnieuw aan, maar anders dan vóór D2 is er geen apart TitleBar-component — de D2-header zélf is nu de titelbalk. De header sleept het venster (`-webkit-app-region: drag`, elke knop erin meldt zich af), en rechts naast Stop staan de vensterknoppen (— □ ✕) via de preload-brug die er al lag; in een browser verschijnen ze niet. De menubalk blijft bestaan maar wordt nooit getoond — hij dient nog uitsluitend om de sneltoetsen (reload, zoom, DevTools in dev) in leven te houden. (2) **Handmatige camerabediening terug**: de U161/U162-aim-pad was bij de herbouw tot drie kijkknopjes versimpeld — de echte besturing (slepen op het beeld voor kop-yaw én -pitch, aparte torso-slider, expliciete Follow/Manual-schakelaar zodat richten en gezichtsvolgen nooit om de kop vechten, gecoalesceerde verzending zodat de kop stopt als jij stopt) staat nu integraal in Robot › camera. Manual is nog steeds gewoon "follow staat uit", afgeleid uit de gedeelde store, dus de Follow-minitoggle en de schakelaar kunnen elkaar niet tegenspreken. (3) **Thema-schakelaar in de titelbalk**: één klik zon/maan naast de detailknop — Settings › Appearance blijft bestaan, beide schrijven dezelfde store. Console 94 groen, vite build schoon; pad+torso en beide themarichtingen live geverifieerd.
- 2026-08-18 — U252c DE PERSONA-KEUZELIJST WAS LEEG (feedback op U252b, met screenshot): Robot › Persona toonde een lege select, en in de editor waren Verbosity en Humour ook leeg. Oorzaak: de D2-herbouw had de vorm van `/setup/characters` gegokt in plaats van gelezen — het brein stuurt `display_name` (niet `name`), en `verbosity`/`humor_level` zijn wóórden (`brief/normal/detailed`, `none/low/medium/high`), geen getallen. Dezelfde gok zat in de persona-dropdowns van Modes en Present (die toonden daardoor kale ids). Alle drie op de echte veldnamen en woordenschat gezet, plus de ontbrekende `off`-optie bij Interruptibility die het brein wél kent. Console 94 groen, build schoon.
- 2026-08-18 — U252d "TRY A MOVE" DEED VOOR ELKE KARAKTER HETZELFDE (feedback op de archetype-kiezer): de traits zeiden "reluctant motion" of "bouncy motion", maar de knop stuurde voor alle tien dezelfde generieke `gesture` op standaardsnelheid — de persoonlijkheid stond in woorden, niet in beweging. Elk archetype heeft nu een eigen **signature move**: een échte robotbeweging mét de snelheid en amplitude die hem als dat karakter laten lezen — Grump een kleine trage hoofdschud (0.75× · 0.4), Buddy de volle dans (1.2× · 0.8), Host de theatrale buiging op volle amplitude, Sentinel één minimaal knikje. "Hear him" gebruikt dezelfde beweging bij zijn openingszin, en de kaart toont het als een chip naast de traits met de reden als tooltip. `act()` kreeg daarvoor speed/amplitude als parameters (de "Ask him to…"-chips blijven op de standaardwaarden). Console 94 groen, build schoon.
- 2026-08-18 — U253 FOLLOW-ME STOND AAN EN VOLGDE NIEMAND (de tracker was dood, niet blind): gemeld met "in follow mode volgt hij de persoon in beeld niet". Status zei `tracking=true, face_visible=false` — precies het beeld dat U165 al onderscheidde als "tracker kapot óf niemand in beeld". Rechtstreeks bij de daemon (`/api/media/tracking/face`) bleek welke: `face_target.ts` stond al minuten bevroren op 4786.0 en bewoog ook niet na enable/disable. **De FaceTracker van Pollens daemon (wireless 1.9.0) was gestald**, en `start_head_tracking()` — het enige wat de U126-watchdog elke 5 s herhaalt — draait dan alleen aan een gewicht van een thread die niet meer loopt. Wat hem wél wakker kreeg, met de hand geverifieerd: media release → acquire → enable; daarna tikte `ts` weer elke ~2 s door. Dat zit nu in de watchdog: hij leest de tracker-klok mee, en pas als die langer dan `TRACKER_STALL_S` (30 s) stilstaat — niet als er gewoon niemand in beeld is, want dan tikt hij door — herbouwt hij de media via de SDK (`release_media`/`acquire_media`), hoogstens eens per twee minuten omdat een rebuild camera en audio een paar seconden wegneemt. Onderweg een echte race in de bestaande watchdog gedicht: een tick die de guard al voorbij was kon `start_head_tracking()` nog afvuren ná `set_tracking(False)` en zo de Manual-schakelaar van de operator stil ongedaan maken — de check zit nu ín de thread. Twee tests: bevroren ts → rebuild; tikkende ts zonder gezicht → géén rebuild. robot-runtime 96 groen, ruff schoon. Uitgerold naar de Pi.
- 2026-08-18 — U252e INSTELLINGEN LAADDEN NIETS, EN "UNKNOWN" WAS EEN LEUGEN (gemeld met een screenshot van vier connectorrijen op `unknown`): mijn eigen regressie uit U252. De herbouwde SettingsView riep `connections.fetchStatus()` en `fetchIdentityStatus()` aan — twee functies die de store **privé** houdt; alleen `refreshAllStatuses()` is geëxporteerd. Dat is een TypeError op de eerste regel, en omdat alle zeven laadaanroepen in één `onMounted`-pijl stonden, zijn de zés erna nooit uitgevoerd: connecties, capabilities, onthouden beslissingen, de kluisstatus én de spraakvoorkeuren bleven leeg. Op het scherm las dat als "de backend ligt eruit", terwijl `/connector/health` en `/identity/status/...` de hele tijd 200 antwoordden. Deze app heeft geen vue-tsc-configuratie (esbuild strípt types ongecontroleerd) en niets mountte deze view, dus noch de compiler noch de suite kon het zien. Drie dingen gedaan. (1) De juiste aanroep. (2) **Elke sectie laadt nu onafhankelijk** — een verkeerde methodenaam kost voortaan één grijze rij, geen zes; dat een enkele typefout een halve pagina stil uitschakelt is een ontwerpfout, geen pech. (3) Een test die SettingsView daadwerkelijk mount, geverifieerd dat hij rood wordt op de oude code. Onderweg nog een tweede, oudere fout: `refreshAllStatuses` draaide health en identity in `Promise.all`, terwijl identity juist overslaat wat health al beantwoordde — die overslag werkt alleen als health er ís. Parallel won identity de race en meldde m365 als "not connected" in plaats van "canned data". Nu sequentieel. Live geverifieerd tegen het draaiende brein: alle vijf rijen worden echte statussen. Brain 409, console 96 groen, build schoon.
- 2026-08-18 — U253b DE SCHERMBEDIENING NEGEERDE HET MODEL DAT JE KOOS: gemeld met "ik vroeg om claude code desktop app te gebruiken, niet api", gevolgd door `Your credit balance is too low to access the Anthropic API`. De keten: `create_default_agent()` koos de Anthropic-agent zodra er ergens in de procesomgeving een `ANTHROPIC_API_KEY` stond — en op Windows staat die in de gebruikersomgeving, jaren geleden voor iets anders gezet, nooit in AURA ingevoerd. Daarmee werd de bewust ingestelde **Screen control = gpt-5.5** stilzwijgend overruled. Erger: opgebruikt krediet faalt pas bij de áánroep, niet bij het construeren, dus de constructor slaagde en er was niets om nog van terug te vallen — élke schermactie eindigde op een 400 en de OpenAI-weg eronder werd nooit bereikt. Nu beslist de keuze van de eigenaar: staat er een schermbedieningsmodel ingesteld én is er een OpenAI-sleutel, dan wint die. Zonder expliciete keuze verandert er niets (Anthropic blijft de voorkeur), en een gekozen model zonder OpenAI-sleutel laat je niet stranden. Drie tests, geverifieerd rood op de oude volgorde. **Een expliciete instelling die de code stil overruled is erger dan geen instelling.**
- 2026-08-18 — U253c DE WEIGERING WAS VERZONNEN, EN DE SKILL HAD HEM DE ZIN AANGEREIKT: gemeld met een screenshot waarop op "kan je in claude onderhoren wat de regels zijn voor hockey jeugd" geantwoord werd met *"Ik kan Claude niet direct openen omdat het niet in mijn lijst met goedgekeurde apps staat"* — terwijl `claude` gewoon ín `ALLOWED_APPS` stond, naast vscode, code, notepad, spotify, chrome en chatgpt. Gemeten: `launch_app` is nooit aangeroepen. De oorzaak zat op twee plaatsen tegelijk. (1) **De tooldefinitie noemde de lijst niet** — alleen "e.g. 'vscode', 'spotify'" — dus het model kón niet weten wat er geregistreerd stond en moest gokken; het gokte mis. De beschrijving wordt nu per beurt opgebouwd mét de échte namen erin, plus de instructie om het gereedschap sowieso aan te roepen: registreer je een app in Capabilities, dan weet hij het bij de eerstvolgende zin, niet na een herstart. (2) **De skill reikte de weigerzin zelf aan**: stap 1 zei letterlijk "If the name is not in the allow-list, say so and point at Capabilities". Het model nam die tak zonder de voorwaarde ooit te toetsen. Nu staat er dat een weigering alleen mag worden doorgegeven als een écht toolresultaat hem gaf. **Een verzonnen weigering is erger dan een mislukte aanroep: je vertelt de eigenaar dat er een grens is waar er geen is, en slaat precies de aanroep over die dat zou hebben rechtgezet.** Daar bovenop een derde, dieper probleem: skills worden bewust één keer geseed (een default die zichzelf herstelt is geen default), dus deze fout zat in een tekst die op elke bestaande machine voor altijd zou blijven staan — een codefix bereikt hem niet. Nieuw: een **fingerprint per geseede tekst**. Is de opgeslagen tekst nog letterlijk de onze, dan mag een correctie hem vervangen; wijkt hij af, dan is hij van de eigenaar en blijft hij staan; is hij verwijderd, dan blijft hij verwijderd. Voor installaties van vóór dit mechanisme staat de fingerprint van de uitgeleverde tekst hard in de code, anders zou juist déze fix niemand bereiken. De schakelaars van de eigenaar (aan/uit, persoon, persona's) overleven een correctie — alleen de procedure is van ons. 10 tests op het seed-gedrag; live geverifieerd tegen een nagebouwde kopie van de echte store: oude weigerzin weg, nieuwe tekst erin, fingerprints weggeschreven voor alle vier de skills. Orchestrator 322 groen, ruff schoon.
- 2026-08-18 — U254 CONNECTIES DIE BESTAAN, AAN KUNNEN, EN VERANDEREN WAT HIJ KAN: gemeld met een screenshot van vier rijen die alle vier `unknown` zeiden naast een Connect-knop — "deze zijn nog niet geïmplementeerd/niet werkende, en kunnen nog niet door robot gebruikt worden". Gemeten bleek het tegendeel én erger: `google.py`, `github.py` en `slack.py` bestaan en praten met echte API's, maar `ENABLED_CONNECTORS` staat standaard op `"m365"`, dus de registry bouwde ze nooit, health noemde ze nooit, en de console had niets te tonen behalve `unknown` — precies de enige status waar een eigenaar niets mee kan. Vier lagen. (1) **`connector_state.py`** beschrijft nu élke connector die AURA kan spreken, aan of uit, met een eigen volgende stap: `not_enabled` (uit), `no_credentials` (aan, maar geen OAuth-app — mét de ontbrekende variabele én de portal erbij), `unauthenticated` (klaar, nog niet ingelogd), `mock`, `ok`. Dat onderscheid is de kern: een app registreren kost tien minuten in een browser, inloggen kost één klik, en één woord voor allebei maakte de pagina waardeloos. (2) **`connector_prefs.py`** — aanzetten kon alleen door `ENABLED_CONNECTORS` te bewerken in een env-bestand dat de desktop-app zélf genereert, en dan herstarten; dat is geen instelling maar een deploymentdetail. Nu een schakelaar per rij, persistent, en de registry herbouwt in dezelfde request. (3) **De hersenen brengen het in rekening.** `mode_policy.set_live_domains()` haalt gereedschappen weg waarvoor geen account leeft: geen mailconnector → geen `get_unread_mail`, want die aanbieden betekent beloven mail te lezen en dan een 503 uitleggen (U248, één laag dieper). Todos en reminders staan er expres NIET in — die zijn memory-service, lokaal, en die poortwachten op een Microsoft-account zou juist het deel breken dat zónder account werkt. Zoals bij de afgeleide modusstatussen geldt: niet-weten neemt niets af (`None` = geen filtering), alleen het brein — dat beide helften bezit — mag het zeggen. (4) **De chip zegt het.** Een groep die de modus toestaat maar geen account heeft leest nu `mail · no account` in plaats van een groene belofte. Live geverifieerd op een geïsoleerde stack: schakelaar uit → chips worden "no account" en `live_domains` krimpt; weer aan → alles terug, in dezelfde klik. **Wat ik niet kan doen en jij wel:** de OAuth-apps registreren in je eigen Azure/Google/GitHub-account — daarom noemt elke rij nu de portal en de exacte ontbrekende variabele. Brain 409, orchestrator 328, connector 49, console 96 groen, ruff schoon, build schoon.
- 2026-08-18 — U254b DE TESTKNOP VROEG IEDEREEN NAAR ZIJN AGENDA, EN "CONNECTED" WAS NIET VERDIEND: gemeld als "errors slack and github", met twee regels die er allebei dom uitzagen — `GitHub connector does not expose calendar` en hetzelfde voor Slack. Dat was de connector die gelíjk had en de probe die fout zat: `test_connector` riep voor élke connector `list_calendar_events_today()` aan, terwijl GitHub repos doet en Slack kanalen, en die twee agenda expres weigeren. Hun eigen Testknop kon dus per definitie nooit slagen, en de weigering werd aan de eigenaar getoond alsof de verbinding kapot was. Elke connector heeft nu zijn eigen goedkope leescall als probe (`list_assigned_issues`, `list_channels`, agenda voor m365/Google). Maar daaronder zat iets ergers, dat U254 pas zichtbaar maakte: beide meldden **"Connected — real calls are going out"** terwijl er helemaal géén token was. De registry markeert een connector OK zodra de constructor niet knalt, en bij GitHub en Slack wordt de sleutel pas bij de áánroep opgehaald — die bouwen dus vrolijk zonder account. Precies de leugen waar de kop van die sectie zelf tegen waarschuwt: *a green badge means a real call worked*. Connectors met een sleutel-bij-aanroep staan nu op `unauthenticated` tot een probe het echt heeft bewezen, en dragen tot dan niets bij aan wat hij kan. Live geverifieerd: github en slack melden nu "no token is stored", hun Test geeft de échte reden (`GitHub token not found`) in plaats van de agenda-onzin, en m365 telt netjes 2 agenda-items mét "MOCK data, not a real account" en ok=False. 3 tests erbij. Connector 52, orchestrator 328 groen, ruff schoon.
- 2026-08-18 — U255 GEREEDSCHAP DAT JE ZELF TOEVOEGT (MCP), EN PAS DAARNA AANZET: gevraagd na U254 — "voeg mogelijkheid toe om tools toe te voegen (mcp) die daarna dan kunnen geactiveerd worden". Er stónd een `GenericMCPConnector`, maar die postte `{"tool": …}` naar `/tools/call` — een vorm die geen enkele MCP-server beantwoordt — had geen manier om te vrágen wat een server aanbiedt, en werd nergens aangeroepen. "AURA ondersteunt MCP" was dus alleen waar in de zin dat er een bestand met MCP in de naam bestond. Vier stukken. (1) **`mcp_client.py`** spreekt het échte protocol: JSON-RPC 2.0 over Streamable HTTP, `initialize` → `tools/list` → `tools/call`, en accepteert zowel een JSON-antwoord als een SSE-stream (dat laatste weigeren zou een groot deel van de echte servers uitsluiten). Alles begrensd: een server die hangt of onzin praat kost één timeout en een zin, nooit een vastgelopen beurt. (2) **`mcp_servers.py`** — de registry, met drie regels erin gebakken. *Toevoegen is niet aanzetten*: bij toevoegen worden de tools ontdekt en getóónd, en pas daarna kun je de schakelaar omzetten; een lijst gereedschap van een derde hoort niet stilletjes onderdeel te worden van wat de assistent doet. *Aangezet is niet onbewaakt*: MCP-tools landen in een eigen policygroep die standaard op `asks` staat — ingebouwde tools zijn hier geschreven en nagekeken, deze niet, en dat verschil mag één klik kosten. *Geheimen gaan naar de keyring, nooit naar het JSON-bestand*, expres zónder plaintext-terugval: een bearer-token naast de config zetten is precies wat U225 voor de passphrase repareerde. (3) **De naamruimte `mcp__<server>__<tool>`** is gereserveerd, dus een toegevoegde tool kan nooit met een ingebouwde botsen of zich als `send_mail` voordoen — en in Present-modus doen ze helemaal niet mee, want een vreemde tool die middenin een talk afgaat is het laatste wat iemand wil. (4) **De console**: toevoegen, de ontdekte tools zien staan, aanzetten, verversen, verwijderen — plus de chip `mcp tools · asks` in de kop. Live geverifieerd tegen een echte spec-vormige MCP-server: ontdekken (2 tools), toegevoegd-maar-uit (0 in de gereedschapskist), aanzetten, ze verschijnen in de prompt, ze vragen toestemming, en de aanroep geeft echt antwoord. Daarna hetzelfde nog eens volledig via de UI, met een tweede server. 16 tests. Brain 409, orchestrator 344, connector 52, console 96 groen, ruff schoon.
- 2026-08-18 — U256 QUIET STOND AAN EN HIJ BEGON TOCH TE PRATEN (+ tijd in de chat): gemeld met een screenshot waarop de kop **HUSHED** zei en de presence-regel beloofde *"Awake but hushed — he answers when asked and never speaks first"* — en er onderaan alsnog een spontane begroeting stond: "Hey! Great to see you, and I hope you've been enjoying the cozy weather for your evening plans!". Gemeten oorzaak, en het is een pijnlijk simpele: **de Quiet-schakelaar bestond alleen in `localStorage`.** `toggleQuiet()` zette een browservlag en verder niets; het brein — dat de begroeting doet en het proactieve spreken — is er nooit over geïnformeerd. De begroetingshandler keek uitsluitend naar `ROBOT_ASLEEP`, dus er was letterlijk geen enkele plek waar Quiet iets tegenhield. Een schakelaar die een belofte toont die niemand nakomt is erger dan geen schakelaar. Quiet is nu échte, persistente policy-state in het brein (`quiet()` / `set_quiet()` / `speaks_first()`), meegestuurd in `/orchestrator/policy` en gezet via een eigen endpoint; de console post hem optimistisch en corrigeert zich op het antwoord, en leest hem bij elke policy-fetch terug — botsen browser en brein, dan wint het brein, want dat is wat de robot werkelijk gaat doen. Twee plekken poortwachten er nu op: de gezichtsbegroeting (registreert de waarneming nog wél, precies zoals bij slaap, zodat een uur stilte niet als "weggeweest" telt en hij niet alsnog begroet zodra je hem aanzet) en de ProactiveEngine (briefing en gesproken herinneringen). Wat expres NIET verandert: geen enkel gereedschap verdwijnt, want stil zijn betekent níét beginnen — een assistent die ook stopt met antwoorden is gewoon kapot. Daarnaast, zoals gevraagd, **tijd bij elk chatbericht**: alleen het uur voor vandaag (de datum op elke regel is ruis in een gesprek dat je nú voert), automatisch mét datum zodra een beurt ouder is, volledige tijdstempel in de tooltip, tabulaire cijfers, en weg in Calm-dichtheid. 5 tests. Live geverifieerd: klik op Quiet → brein meldt `quiet: true`, proactief spreken gaat van True naar False; en een echte beurt toont "22:54" bij beide bubbels. Brain 409, orchestrator 349, console 96 groen, ruff schoon.
- 2026-08-18 — U257 "HALLO" IS GEEN TAAL: gevraagd na een screenshot waarop op "hallo" geantwoord werd met *"Hallo! Wie kann ich dir heute helfen?"* — "waarop begint hij in duits te praten?". Er was niets stuk. Met Reply language op **Automatic** luidde de volledige instructie: *"Always reply in the language the user is using."* Dat werkt prima voor een zin en is waardeloos voor één woord: "hallo" is even goed Nederlands, Duits én Engels, en een kaal "hallo" wordt in trainingsdata vaker met Duits beantwoord dan met wat dan ook. Hij gooide dus een muntje op, en dat mocht hij van ons. Nu krijgt Automatic een **tiebreaker**: bij een boodschap die te kort is om het aan te zien antwoordt hij in de huistaal, en schakelt hij zodra je het wél duidelijk maakt. Die huistaal is expres géén gok — `LANGUAGE_FALLBACK` wint als je hem zet, anders de locale van de machine zelf, en onbekend blijft Engels zoals voorheen. Onderweg een echte val: `locale.getlocale()` geeft op een onaangeraakt proces `"C"` terug — truthy en nutteloos — dus de eerste niet-lege bron pakken verstopte de échte locale erachter; nu worden alle bronnen afgelopen tot er één een taal noemt die we kennen (jouw `nl_BE` → Nederlands). Een expliciete taalkeuze blijft absoluut: die krijgt geen terugval en wordt geen suggestie. Settings toont de regel alleen bij Automatic, met wat de machine oplevert erbij ingevuld, zodat het antwoord nooit een mysterie is. 4 tests. Live: leeg → effectief `nl`, overschrijven naar `fr` landt en leest terug. Brain 409, orchestrator 353, console 96 groen, ruff schoon.
- 2026-08-19 — U258 HIJ WEKTE ZICHZELF DOOR ZIJN EIGEN NAAM TE ZEGGEN: gemeld met twee screenshots vol groene gebruikersbubbels die de eigenaar nooit getypt had — "AURA?", "Ančapí.", "Erststück.", "Bu labosizki" — plus antwoorden in het Hindi en een realtime-teller die doortikte. "I never said anything, still robot is talking/responding." De keten, helemaal uitgemeten. De echo-guard rekende `min(12.0, 1 + len/15)`: het tempo klopt, **de cap was de bug**. Een antwoord van 400 tekens duurt ~27 seconden om uit te spreken, de guard dekte er 12, en de resterende **~15 seconden stond de microfoon wijd open terwijl de robot praatte — over "AURA", hardop, wat toevallig zijn eigen wakkerwoord is.** Hij wekte zichzelf; een kaal wakkerwoord opent volgens U93 een tweede luistervenster; dat venster keek alléén naar het volume en nam dus de robot zijn eigen stem van dichtbij op; die onzin werd een "gebruikersbeurt"; het antwoord daarop duurde weer lang, en rond ging het. Vandaar gesprekken zonder iemand in de kamer, afdrijvend door talen die niemand sprak, met realtime-minuten op de rekening. Drie reparaties. (1) De schatting krijgt een cap die **bóven** een echt antwoord ligt in plaats van onder de meeste (90 s, tempo instelbaar). (2) Het tweede luistervenster wacht eerst zijn eigen spraak uit — dat venster vraagt expres geen wakkerwoord, dus het openen terwijl hij praat is hem letterlijk zijn eigen stem voeren. (3) Zijn eigen naam, in zijn eigen stem, is geen wakkerwoord meer: "AURA?" is vijf tekens en dus te kort voor de bestaande woord-overlaptest. **En passant een tweede vondst: de U148-echobeschermingen stonden allemaal achter `in_followup`, terwijl `FOLLOWUP_S` standaard 0 is en Realtime hem sowieso uitzet (U149) — in de uitgeleverde configuratie waren het dus dode regels.** Die draaien nu op elke weg, de woord-overlaptest wel tijdgebonden zodat iemand die napraat niet gesmoord wordt. 6 tests, geverifieerd rood op de oude cap. Brain 415 groen, ruff schoon.
- 2026-08-23 — U259 HIJ KON HELEMAAL NIETS OPZOEKEN: gemeld na een gesprek waarin op "wanneer speelt Red Panthers" geantwoord werd met "kijk op de website van de hockeybond". Dat was geen ontwijking — gemeten: er was **geen enkel internet-gereedschap**. Geen zoekfunctie, geen manier om een pagina te lézen, en de onderzoeks-subagent had een toolset die volledig lokaal was (bestanden, git, agenda, mail, tabbladtitels). `open_browser_url` ópent een pagina in Chrome en geeft de inhoud aan niemand terug. Hij was eerlijk over een grens die er echt was. Nu twee werkwoorden, want één zonder de ander is een half product: **`web_search`** vindt pagina's, **`read_url`** leest ze. Een link vinden die hij niet kan openen helpt niemand. Backends worden op volgorde geprobeerd, precies zoals gevraagd: (1) de zoekfunctie van de LLM-provider zelf — geen nieuw account, en OpenAI, Anthropic én Gemini hebben er elk een, zodat overstappen van provider het zoeken meeneemt; (2) een MCP-zoekserver die de eigenaar via U255 heeft aangesloten; (3) de eigen Chrome als laatste redmiddel — die kan de tekst niet teruggeven, dus hij doet ook niet alsof: hij zegt wáár het antwoord nu staat. **Elke backend meldt waaróm hij afhaakte, en die redenen reizen mee met het antwoord**: een mislukte opzoeking mag nooit lezen als "niets gevonden", want dat vraagt een compleet ander antwoord van de assistent (dezelfde les als U248, één laag dieper). Grens zoals gevraagd: altijd toegestaan, in élke modus inclusief Present — juist tijdens een talk is een feit niet kunnen checken het pijnlijkst — behalve in **Work, waar hij eerst vraagt**, want een werkvraag kan iets vertrouwelijks het huis uit dragen. Daarvoor was een nieuw begrip nodig: `APPROVAL_REQUIRED` is globaal (altijd of nooit), dus per-modus-toestemming is een eigen, zichtbare regel geworden in plaats van een nep-override op naam van de eigenaar. **Live gemeten en meteen een val gevonden**: `gpt-4o-search-preview` en `gpt-4o-mini-search-preview` staan nog wél in de modellenlijst van het account maar antwoorden allebei 404 "has been deprecated" — één hardgecodeerde naam was dus "AURA kan niet meer zoeken" op een ochtend dat niemand iets veranderde. Daarom een lijst kandidaten die wordt afgelopen; `gpt-5-search-api` werkt en gaf op de échte vraag: "zondag 23 augustus 2026 om 20:30 tegen Spanje, in Wavre", mét bronlink. 14 tests. Brain 415, orchestrator 367, console 96 groen, ruff schoon.
- 2026-08-23 — U259b HIJ ZOEKT NU ZELF UIT WELK ZOEKMODEL NOG BESTAAT: gevraagd meteen na U259 — "modellen veranderen, ook in versie, zorg dat hij in staat is om dan de andere versie te nemen zoals je hier naar gpt-5-search-api ging". Terecht: de kandidatenlijst die ik in U259 opschreef verouderde precies zoals de losse naam ervoor, alleen langzamer, en het punt was juist dat niemand dat handmatig moet bijhouden. Nu **vraagt hij het de provider zelf**: de modellenlijst wordt opgehaald, de zoek-capabele namen eruit gefilterd, en gerangschikt op wat de náám zegt — hogere versie eerst (`gpt-6` slaat `gpt-5` slaat `gpt-4o`), een ongedateerde alias vóór zijn eigen snapshot (de alias volgt het huidige model), het volle model vóór zijn `mini`. Daardoor wint een model dat nog nergens is opgeschreven op de dag dat het verschijnt. Eén val die de eerste poging maakte: de datum werd als versie gelezen, dus `gpt-5-search-api-2025-10-14` leek versie 2025 en élke snapshot won van élke alias — de datum wordt nu eerst afgeknipt. Deep-research-modellen kunnen ook zoeken maar kosten minuten en euro's, dus die kiest hij nooit uit zichzelf; alleen als je er expliciet één noemt. Het model dat wérkte wordt onthouden (anders betaalt elke zoekopdracht een lijst-aanroep plus twee mislukkingen) en **vergeten zodra het faalt** — dat falen ís het signaal dat de provider verschoven is, en precies dan is een verse lijst zijn geld waard in plaats van pas over een uur. Werkt voor alle drie: bij Anthropic en Gemini is zoeken een tool die élk actueel model kan gebruiken, dus daar is "het nieuwste model" de juiste keuze in plaats van een naam met "search" erin. Live geverifieerd op het echte account: hij ontdekt zelf `gpt-5-search-api` als beste van tien namen en beantwoordt "wie won de laatste F1 Grand Prix" met bron; en toen ik het onthouden model verving door een ingetrokken model, viel hij vanzelf door naar de werkende en onthield die. 8 tests erbij. Orchestrator 375 groen, ruff schoon.
- 2026-08-23 — U260 HIJ BEGROETTE JE EN KON JE ANTWOORD NIET HOREN: gemeld met een screenshot waarop hij twee keer uit zichzelf "Hey Jan! Fijn om je te zien" zegt, de eigenaar gewoon terugpraat, en er niets gebeurt — alleen via de Talk-knop in de chat kwam het door. Gemeten: de begroeting bereikt de spraaklus prima (`note_spoken` hangt aan élke `ResponseDrafted`, dus ook aan een begroeting), maar het venster waarin je zónder het wakkerwoord mag antwoorden stond op **nul**. Twee keer dichtgespijkerd: U92 voor de pipeline, U149 nog eens apart voor Realtime — beide keren wegens spookgesprekken. De regel commentaar recht boven de constructie beloofde ondertussen letterlijk *"Each spoken reply opens a follow-up window so a greeting/answer becomes a conversation"*, terwijl de regel eronder `followup_s=0.0` meegaf. **Maar U258 vond gisteren waaróm die spoken ontstonden**: de echo-guard was afgetopt op 12 seconden terwijl een lang antwoord er ~27 duurt, dus de microfoon stond open terwijl de robot praatte — over "AURA", zijn eigen wakkerwoord. Met die oorzaak weg is de spijker niet meer nodig, en wat overblijft is een robot die je begroet en je antwoord niet mag horen. Een begroeting is een vraag; eerst "AURA" moeten zeggen voor je mag antwoorden is geen gesprek maar een formulier. Venster weer open, óók in Realtime (de eigenaar staat dáárop, dus alleen de pipeline repareren had voor hem niets opgelost), met alles wat het begrenst nog intact: het venster begint pas ná zijn eigen spraak, je antwoord moet duidelijk luider zijn dan de omgeving (`FOLLOWUP_PEAK_FACTOR`), de U258-guards tegen zelf-echo en zijn eigen naam draaien nu op élke weg, en na `FOLLOWUP_CHAIN_MAX` beurten zonder wakkerwoord is het wakkerwoord weer nodig — een spook kan dus twee keer tegen zichzelf praten, niet eeuwig. `FOLLOWUP_S=0` blijft de noodrem, live leesbaar. 5 tests, geverifieerd rood op de oude uitschakeling. Brain 420 groen, ruff schoon.
- 2026-08-23 — U261 HIJ BELOOFDE HET OPNIEUW, MET ANDERE WOORDEN: gemeld met een screenshot — "kan je claude vragen welke projecten ik openstaan heb" → *"Ik kan Claude voor je openen en hem de vraag stellen. Laat me dat even doen!"* → en in de Claude-app gebeurde niets. Exact de klasse die U248 zou vangen. De machinerie werkt ook nog: staat er een belofte in een beurt waarin **nul** gereedschap draaide, dan krijgt hij één duw ("doe het nu, of zeg plat dat je het niet kunt en wat er ontbreekt"). Alleen: die detectie is een wóórdenlijst, en "Laat me dat even doen!" stond er niet in. Gemeten en bevestigd — de zin uit de screenshot gaf `False`. Acht verwoordingen toegevoegd die hij nu gebruikt (`laat me …`, `ik doe dat`, `dat ga ik …`, `let me …`, `I'll go ahead`, `komt eraan`, `on it`). Eén valkuil expres apart opgelost: **"laat me weten" / "let me know" is het tégenovergestelde** — dat legt de bal juist bij de eigenaar — en die uitzondering zit ín het patroon in plaats van in de aanbod-lijst, want die laatste gooit een hele beurt weg en zou dus ook de echte belofte in *"Ik ga nu Chrome openen. Laat me weten of het lukt"* hebben laten lopen. Zes tests, waarvan één letterlijk de gerapporteerde zin. **Wat hieraan structureel zwak blijft, en ik niet ga verbergen**: dit is en blijft een woordenlijst, dus het model kan opnieuw een formulering vinden die er niet in staat. Wat het wél afdwingt is dat elke ontsnapping één regel kost in plaats van een discussie. Orchestrator 381 groen, ruff schoon.
- 2026-08-23 — U262 HET KRUISJE DEED NIETS, EN EEN TYPFOUT WAS VOOR ALTIJD: gemeld bij het profiel van Limme, met een feit dat letterlijk "likes colelcting jellycats" zei — "removeing/delting (cross) fact doesn't work, fix it, but also make it editable". Oorzaak stond in de docstring van de poort zelf: `_require_stepup` **auto-weigert wanneer `STEP_UP_WEBHOOK_URL` niet gezet is**, en `delete_fact` hing daar als enige aan vast. Een versleutelde kluis zonder telefoon-webhook — dus de normale installatie — kon dus géén enkel feit verwijderen. Stil, want de console toonde de 403 nergens: het kruisje deed simpelweg niets, de meest verwarrende uitkomst die er is. **Exact dit was in U185 al opgelost voor het vergeten van een PERSOON** (telefoon regeert als er een webhook is, anders een getypte bevestiging vanaf het eigen scherm) — feiten hebben die behandeling nooit gekregen. Nu wel, met dezelfde redenering: een zwakkere maar eerlijke poort is beter dan een functie die niet kan worden gebruikt, zeker bij deze, wiens hele doel is te corrigeren wat hij verkeerd gelooft. Daarnaast **bewerken**, en dat is de nuttigste helft: een `PATCH /knowledge/facts/{id}` die het feit ter plekke verbetert mét behoud van zijn id en herkomst — delete-en-opnieuw-toevoegen ziet er op het scherm identiek uit en verliest allebei stilletjes. Bewerken is niet destructief (het feit blijft, het wordt alleen juist) en heeft dus géén step-up: een vergissing rechtzetten hoort makkelijker te zijn dan ermee leven, anders stoppen mensen met rechtzetten. Onderweg bleek de console al een `updateFact` te hebben die delete-en-toevoegen deed — die leunde dus op precies de kapotte delete, waardoor bewerken net zo goed stuk was. In de UI: een ✎ naast het ✕, inline bewerken met Enter/Esc, een bevestiging vóór het verwijderen, en **een zichtbare foutmelding naast het feit** in plaats van stilte. 4 backend-tests (waarvan één de gerapporteerde situatie nabootst: versleutelde kluis, geen webhook) — geverifieerd rood op de oude regel. Live geverifieerd tegen een écht versleutelde kluis (`omk_loaded: true`): typo gecorrigeerd met hetzelfde fact-id, daarna verwijderd, kaarten 2 → 1, geen foutmelding. Brain 424, orchestrator 381, console 96 groen, ruff schoon.
- 2026-08-23 — U263 DE SLIDESHOW VOLGEN ZOALS EEN MENS DAT ZOU DOEN (+ Keynote, + uitleg): gevraagd na de drie zwakke plekken die ik zelf had opgesomd, plus Keynote en betere begeleiding. **(1) De volgorde-val.** `start_presentation` vroeg één keer of er al een slideshow draaide; zo niet, dan werd er géén watcher aangemaakt en was er geen herkansing. Het scenario is nu net wat je als eerste klaarzet, dus in de natuurlijke volgorde verloor je élke `slide:N` beat van je hele talk — zwijgend, met "manual" in beeld. De watcher draait nu altijd en wachten is een gerapporteerde toestand in plaats van opgeven vóór de talk begint. **(2) Welk deck.** `pptx:` was documentatie en werd nergens vergeleken; open het deck van vorige maand en je beats vuren op de verkeerde slides voor publiek. Nu een waarschuwing die vertelt wat verwacht werd naast wat er staat — en expres géén blokkade, want een co-presentator die twee minuten voor een keynote weigert te starten is erger dan een verkeerde opmerking. De vergelijking negeert map, extensie, hoofdletters en de "(2)"/"v3"/"final"-staarten die een normale week oplevert, want een waarschuwing die vals alarm slaat wordt genegeerd juist wanneer ze klopt. **(3) Hoeveel slides.** Voeg er één in het midden bij en de staart van je scenario wijst voorbij het einde; dat wordt nu benoemd mét de slidenummers die nooit kunnen vuren. **(4) Keynote.** Was volledig afwezig — de helft van de mogelijke presentatoren kon hier niets mee. Spreekt een ander dialect (AppleScript in plaats van COM) maar beantwoordt dezelfde drie vragen, dus beide zitten achter één `read_state()`; één AppleScript-aanroep voor naam, slide én totaal, want drie losse vragen geven antwoorden uit drie momenten en een slidenummer dat bij een ander deck hoort dan de naam ernaast is erger dan geen antwoord. **(5) De UI.** Een genummerde stappenkaart die zegt wat je moet doen — inclusief expliciet *"open je deck en start de slideshow (F5 in PowerPoint, Play in Keynote), niet alleen het bestand open hebben"* — met stappen die doorstreept raken zodra ze gedaan zijn, en die pas verdwijnen wanneer hij écht een deck volgt. Plus een statusbalk met drie eerlijke toestanden (`off` / `waiting` / `live`), waar er vroeger één vlag was die "watcher bestaat" verwarde met "er staat een slideshow op het scherm". 13 tests. Brain 436 groen, ruff schoon, build schoon.
- 2026-08-23 — U263b DE DECKNAAM WAS NERGENS IN TE VULLEN: gevonden op de vraag "hoe weet hij welke ppt/keynote?". Het antwoord is dat hij het aan de dráaiende app vraagt en dus nooit een bestand opent of kiest — maar de deck-waarschuwing uit U263 vergelijkt tegen `pptx:` in het scenario, en de ScenarioBuilder had daar helemaal geen veld voor. Die waarschuwing was via de UI dus onbereikbaar: alleen wie met de hand YAML schrijft kon hem ooit krijgen. Veld toegevoegd, expliciet gelabeld als optioneel en als náám (geen bestandskiezer, want er valt niets te kiezen), en het overleeft het herladen van een opgeslagen scenario. Console 96 groen, build schoon.
- 2026-08-23 — U264 "START PRESENTATION" LIET AL JE WERK VERDWIJNEN: gemeld met twee screenshots — na de klik was de hele builder weg en stond er alleen nog "No scenario loaded / Run presentation". Drie dingen die op elkaar stapelden. (1) `startScenario` zette **`builderOpen = false` als eerste regel**, nog vóór de aanroep; en omdat de builder achter een `v-if` staat wordt hij daarmee niet verborgen maar **vernietigd** — inclusief elke beat die je had ingetypt. (2) De aanroep faalde, en terecht: op de screenshot staat een `Speak (verbatim)`-beat met een leeg tekstveld, en een speak-beat zónder tekst is per validatie ongeldig. (3) De reden stond wél in de store en werd wél gerenderd, maar bovenaan de pagina — waar de builder net vandaan was gescrold. Je zag dus verdwijning zonder verklaring. Nu sluit de builder **alleen na een geslaagde start**, blijft je werk staan bij een fout, en verschijnt de reden náást de knop die je net indrukte in plaats van buiten beeld. Daar bovenop: die reden was een rauwe Pydantic-dump met veldpad, de repr van de hele beat en een link naar pydantic.dev — prima om te loggen, hopeloos om vijf minuten voor een talk te lezen. De validators schrijven zélf al de goede zin ("beat 'beat-1': speak mode needs 'text'"); die wordt nu uit de wikkel gehaald, meerdere fouten samengevoegd. Live geverifieerd: builder blijft open, beats blijven staan, en de melding leest als één zin. Brain 436 groen, ruff schoon, build schoon.
- 2026-08-25 — U265 DE OVERLAY: HIJ OP DE PROJECTOR, EERLIJK — GETEST OP HET ECHTE DECK: gevraagd als "werk overlay uit en start implementatie, test volledig met presentatie", met het eigen deck erbij (Outcoded_by_Our_Kids_Talk_v2-local.pptx, 231 MB, 137 slides). **De opzet.** Eén pagina, twee doelgroepen, gekozen via `#overlay?mode=`: `audience` toont alléén het gekozen karakter (levend op zijn échte spreektoestand) en ondertitels van wat hij zegt — ondertitels zijn geen decoratie, een robotstem in een zaal met slechte akoestiek is half verstaanbaar en dit is de helft die dat oplost; `presenter` voegt toe wat alleen de spreker mag zien (slidestand, volgende cue, deck-waarschuwingen). Wat hij dénkt rendert hier nooit — een half afgemaakte gedachte op een projector voor een zaal is een aansprakelijkheid. De pagina is de console-app zelf op een andere hash (zelfde origin, dus karakterkeuze, brain-URL en WS-bedrading gratis); Electron zet er een transparant, klik-doorlatend, altijd-bovenop venster omheen op een scherm naar keuze (zelfde recept als de U75-overlay, het enige deel dat al bewezen was op deze machine), en een gewone browser krijgt een gewoon venster als eerlijke fallback (sleep naar de beamer, F11). In Present kies je "voor wie is dit scherm" — niet "venster of fullscreen", want dat is de technische vorm, niet de keuze. **De volledige E2E op het echte deck**: PowerPoint via COM geopend en de show gestart; de watcher pikte hem zelf op (`waiting → live`), naam en 137 slides correct; echte slide-advances vuurden de beats in volgorde; de onmogelijke cue (slide 999) gaf keurig de U263-waarschuwing; de presenter-strip toonde live "slide 3 / 137"; de ondertitel rendert met het karakter erbij (14 SMIL-animaties actief in spreekstand) en de presenter-strip blijft weg in audience-modus. **Twee echte bugs eruit gevist.** (1) Bij een speak-beat was de spreek-aanroep onbeschermd: een robot wiens audio faalt at `beat_done` op, en dáár hangt het ondertitel-event aan — ondertitels verliezen op precies het moment dat de audio wegvalt is beide kanalen tegelijk kwijt. Gevonden doordat een beat als gevuurd stond terwijl er nooit een PresentationBeatFired uitging; nu afgeschermd, met test, rood geverifieerd op de oude code. (2) Een hash-navigatie herlaadt de pagina niet, dus de modus werd één keer gelezen en bleef daarna voor altijd hangen; nu live via hashchange. En passant: de PowerPoint-drift van de vorige sessies bleek deels doordat dit deck zichzelf advanceert (tijdstransities) — de watcher volgt dat gewoon. Suites hersteld na een venv-valkuil (`uv sync --all-packages` zonder de dev-extra sloopt pytest uit de omgeving; de twee "failures" waren dat, geen regressie). Brain 436, orchestrator 382, console 96 groen, ruff schoon.
- 2026-08-30 — U266 VIER KEER "ER GEBEURT NIETS", VIER VERSCHILLENDE OORZAKEN: gemeld in één sessie, met screenshots, tijdens het klaarzetten van een echte talk. Ze leken op elkaar en waren het niet. **(1) "Start presentation doet nog steeds niks."** De builder schrijft de cue van een beat als een **string** — `manual`, `slide:4`, `keyword:Java` — en de brain leest hem zo. Deze view las hem als een **object**, en `'keyword' in 'manual'` is in JavaScript geen onwaar antwoord maar een `TypeError`. Hij vloog eruit op de eerste beat, nog vóór de POST, dus de knop stuurde geen request, toonde geen fout en veranderde niets: "No scenario loaded" bleef staan. Bewezen door precies jouw scenario met de hand te POSTen — `HTTP 200, active:true`, de backend deed niets verkeerd. Deze app heeft geen `vue-tsc`-stap (esbuild strijkt types ongecontroleerd weg), dus de foute annotatie compileerde vrolijk en faalde alleen in een klik-handler, voor een deck. Nu tolerant gelezen én in een `try/catch`: een groene knop die zijn eigen crash opslikt is de ergste van de vier, want je klikt gewoon nog eens. **(2) "Ik kan de overlay niet terug deactiveren."** De Hide-knop verscheen alleen zolang déze view geloofde dat de overlay aanstond — een geloof dat reset zodra de view opnieuw wordt opgebouwd (Present staat achter een `v-if`), terwijl het Electron-venster rustig op de beamer bleef. Het hoofdproces is het enige dat het echt weet en zegt dat nu ook (`overlay:present:state`); Hide staat er bovendien **altijd**, want een Hide die niets verbergt kost niets en een overlay die je niet weg krijgt kost een talk. **(3) "Ik zag 'waiting for...', maar zelfs presenteren wordt niet gedetecteerd."** De vierde keer dat `uv sync` prunet wat je niet vraagt (na U179 recognition, U213 Pillow, U246 pyautogui). De bootstrap van de gebouwde app vroeg nooit om de `presentation`-extra, dus **pywin32 ontbrak in elke installatie** — en pywin32 is de enige manier waarop hij leest op welke slide PowerPoint staat. In de dev-tree, waar U263/U265 getest zijn, zit hij wél; daar werkte alles, dus de bug was onzichtbaar precies voor wie hem bouwde. Erger: "ik kán niet kijken" en "ik zie geen show" gaven dezelfde zin, dus de overlay stond je te vertellen F5 te drukken terwijl je deck fullscreen achter die tekst stond. Nu rijdt `--extra presentation` op elke sport van de sync mee, controleert de skip-if-done-stap op `win32com` (níet op `pywin32_ctypes`, dat is een keyring-dependency en iets anders), en zegt de status `slides_blocker` wanneer hij niet kán kijken, met wat je eraan doet. De bestaande U246-bootstraptest kende deze extra niet en is uitgebreid — rood geverifieerd op de oude code. **(4) "Waarom geeft hij 'I'm operating in limited offline mode'?"** De latency zei `llm 0ms / tools 0ms / total 0ms`: er was geen enkele LLM-aanroep. De pipeline kortsluit elke beurt naar de regex-fallback zodra de heartbeat DEGRADED/OFFLINE staat — en de brain bewaakte precies één signaal: `/health` van de robot. Een robot die negentig seconden van de WiFi valt zette de mode op DEGRADED en, als enig signaal, meteen door naar OFFLINE ("any failing" en "all failing" zijn dan dezelfde zin). Sleutel, netwerk en model waren de hele tijd in orde; je presenteerde vanaf een laptop waar de robot niet eens bij hoorde. **Een lichaam dat niet is ingeplugd is geen geest die niet kan denken**: alleen een geconfigureerde upstream mag hem nog degraderen (`essential`), de robot wordt nog steeds gepingd en gerapporteerd, en als hij tóch offline gaat noemt hij nu bij naam wát hij niet kan bereiken in plaats van "other requests require connectivity". Jouw installatie is meteen gedeblokkeerd: pywin32 erin gezet en geverifieerd dat de geïnstalleerde app je deck nu leest (`Outcoded_by_Our_Kids_Talk_v3.0.pptx`, slide 3/104) — het draaiende brain-proces houdt de mislukte import vast, dus dat vraagt één herstart van AURA. Brain 439, orchestrator 384, console 99 groen, bootstraptest groen, ruff schoon op de CI-scope.
- 2026-08-30 — U267 HET PRESENTATIESCHERM VERTELT NU WAT ER ÉCHT GAAT GEBEUREN: vijf vragen op één screenshot, en ze bleken vijf verschillende leugens van dezelfde soort — het scherm beschreef iets anders dan wat het systeem deed. **(1) "Moet ik advance beat drukken? zou automatisch moeten."** Zijn beat stond op `manual` ("I press Next"), dus ja — maar de lijst gaf hem het label **SLIDE**. Elke beat die geen keyword was kreeg dat badge, dus precies de soort die uit zichzelf nooit iets doet, droeg het teken van de soort die dat wél doet. Er zijn nu drie soorten (`manual` / `slide` / `keyword`), de cue-kolom zegt de cue in plaats van het rijnummer ("You press Next", "Slide 12", "«Java»"), en de "Advance beat"-knop is uitgeschakeld met uitleg wanneer geen enkele beat met de hand wordt gevuurd — want dan deed hij stilletjes niets. **(2) "Kan ik aangeven voor welke slide?"** Dat kon al, maar de keuzelijst zei "a slide shows" zonder te verraden wat het verschil ís; nu staat het gevolg in de optie zelf ("I press Next (nothing happens on its own)" tegenover "I reach a slide (fires by itself)"). **(3) "beat 2 of 1".** De teller haalde zijn positie uit `manual_pos` en zijn totaal uit `manual_total`, en die beschrijven allebei alleen de **handmatige** beats. Eén manual beat vuren zette de positie voorbij het eind; drie slide-beats erbij en de noemer bleef 1. Beide helften gaan nu over de héle show (`beats_total` uit de brain, gevuurde beats uit `fired`), en klaar is klaar in plaats van doortellen. En passant: "Run presentation" op een geladen scenario **bouwde het scenario opnieuw op uit de weergaverijen** (`{id, mode:'speak', text}`) en gooide daarmee elke trigger, topic en gesture weg — een deck vol slide-cues kwam terug als een stapel handmatige speak-beats. Hij vraagt de brain nu om het echte scenario. **(4) "Niet duidelijk wat rehearsal doet."** Omdat het niets deed. De knop stond er sinds D2 en beloofde "beats fire, but nothing is sent", maar `rehearsing` was een boolean in de browser die alleen een label omzette — de backend kende het woord niet eens en de robot sprak elke zin gewoon hardop uit. Rehearsal bestaat nu echt: beats vuren, emitten en genereren hun geïmproviseerde regels volledig (die regel wil je juist vooraf lézen), alleen de twee uitgangen die de zaal bereiken — stem en beweging — worden tegengehouden. Het is een toestand van de brain, niet van dit tabblad, met een banner die zegt wat de zaal wel en niet hoort. **(5) "Hoe bewerk ik een presentatie?"** Dat kon niet: "New scenario" opende een lége builder en was de enige deur naar binnen, dus één zin wijzigen betekende de hele talk opnieuw typen. Er is nu een Edit-knop en een `GET /presentation/scenario` die het geladen scenario teruggeeft in exact de vorm die de builder leest. Alle vijf met tests vastgelegd, rood geverifieerd tegen de oude code. Brain 444, orchestrator 386, console 127 groen, ruff schoon, build schoon.
- 2026-08-30 — U268 DE ROBOT OP DE PROJECTOR STOND STIL, EN ÉÉN REGEL SVG WAS DE OORZAAK: gevraagd als "the overlay robot should be animated like eyes rolling/moving, when speaking clear speaking animation, etc... (and depending on chosen character)". Twee dingen bleken kapot, allebei onzichtbaar voor de bouwer. **(1) De standaardrobot had nog nooit geknipperd.** Scout (Richie, wat de overlay toont tenzij je iets anders kiest) en Buddy animeerden `ry` op een `<circle>`. Een SVG-cirkel heeft `r`, geen `ry` — de browser accepteert het element, negeert het attribuut en zegt niets. De knipperanimatie stond er, zag er correct uit in de code, en deed nul. **(2) Zes van de tien karakters hadden bij `idle` letterlijk geen enkele animatie.** Bijna alle beweging zat achter `act !== 'idle'`, dus een robot die even niets zegt — en dat is verreweg het grootste deel van een talk — bevroor volledig. Naast een lopende slideshow op een projector leest dat niet als rustig maar als een venster dat is vastgelopen. Nu: één gedeelde `BLINK` (op het attribuut dat wél bestaat) en een `GAZE` die de hele **ooggroep** laat dwalen in plaats van de oogbol alleen — een oog verplaatsen en zijn lichtpuntje laten staan ziet er kapot uit, niet levend. De ritmes verschillen per archetype, want dáár zit de persoonlijkheid: Buddy's blik zwerft breed en vaak (2.8 / 4.4s), Host werkt de zaal (2.9 / 5.2s), Mender kijkt traag en geduldig (1.5 / 8.2s), Grump beweegt nauwelijks (1.1 / 9.5s). Tijdens het spreken krimpt de blik tot een derde — de aandacht ligt dan bij de zaal, niet bij het plafond. De karakters zónder ogen kregen hun eigen stille leven: Orb scant nu juist wél als hij zwijgt ("watches before it speaks" is zijn hele karakter en dat stopte precies wanneer het gold), Halo's schaduw blijft ademen, Slab gloeit langzaam na, Astro's lampje pulseert traag. **De test die dit soort fout vangt** parst elke `<animate>` uit alle tien de karakters in alle drie de toestanden en controleert of het attribuut op dat element bestáát — met een stack, niet met een lookahead, want mijn eerste versie koppelde de animaties helemaal niet aan hun element en testte dus zelf niets: exact dezelfde ziekte als die hij moest vangen. Rood geverifieerd: 9 van de 31 faalden op de oude kunst, met de `ry`-fout bij naam. Console 134 groen, build schoon.
- 2026-08-30 — U269 HIJ ZEI NOOIT IETS, EN DE OVERLAY WIST NIETS VAN DE SHOW: gemeld als "he never said anything, nor for the overlay did i see cues, warnings, subtitles or anything", met een screenshot waarop "all 1 beats done" stond. Drie losse oorzaken, één indruk. **(1) Presentatiebeats zijn nooit hoorbaar geweest.** `presentation_api._speak` riep `_robot.speak(text)` aan **zonder audio**, en de spreek-route van de robot behandelt een tekst-only verzoek als een **logregel**: hij speelt niets af en antwoordt `ok: true`. Elke andere spreekweg in de app — de voice loop, `/robot/say`, de streaming-antwoorden — synthetiseert eerst en geeft `audio_b64` mee; de presentatie was de enige die dat niet deed. Dus: beat vuurde, console vulde "all beats done" in, nergens een fout, en de zaal hoorde stilte. Nu wordt er echt TTS gemaakt, en falen **werpt** in plaats van te zwijgen — de show gaat nog steeds door (die U265-bescherming blijft), maar een stille robot mag er nooit meer uitzien als een geslaagde beat: `speech_error` staat in de status, in de HUD ("He was not heard — …, zet Laptop audio aan") en in de presenter-overlay. In de brain-log stond intussen keer op keer `All connection attempts failed` naar de robot, wat de U266-diagnose bevestigt. **(2) De overlay kón geen cues tonen.** Het is een **apart venster met een eigen Pinia-store**, en de bealijst die hij las werd alleen gevuld door `PresentView.startScenario` — in het console-venster. Op de projector was `presenter.beats` dus permanent leeg, `nextCue` altijd `''`, en de rij waar hij in hoort rendert dan niet. Hij vraagt het scenario nu aan de brain (de U267-endpoint), die beide vensters delen; de vertaling van een beat naar een schermregel is verhuisd naar `lib/beats.ts` zodat een cue niet twee betekenissen kan krijgen. **(3) De ondertitels wérkten wel** — live bewezen door de WS af te tappen en de overlay in de browser te openen: het `PresentationBeatFired`-event kwam binnen mét tekst en werd getoond. Maar de standtijd was 1,5 s plus leestijd, dus "tell a joke" flitste in nog geen drie seconden voorbij, zonder geluid dat je vertelde te kijken. Ondergrens naar 3,5 s. **Gevraagd en toegevoegd**: de camera in de overlay ("what he sees") als expliciete keuze — uit tenzij aangevinkt, want een live beeld van een zaal terugprojecteren in diezelfde zaal is een beslissing, geen detail. **En de formulering**: "I press Next" las als "wanneer ik naar de volgende slide ga", precies het omgekeerde van wat het doet; de optie noemt nu de knop ("I click «Advance beat» in AURA (your clicker will NOT fire it)"). De drie HUD-knoppen waar naar gevraagd werd doen alle drie iets echts: Laptop audio spreekt zijn regels via de laptopstem (en had dit hele probleem gemaskeerd), Laptop mic gebruikt de laptopmicrofoon voor keyword-beats, Camera off verbergt de preview. Brain 447, orchestrator 387, console 138 groen, alle regressies rood geverifieerd op de oude code, ruff schoon, build schoon.
- 2026-08-30 — U270 BATTERIJSTATUS, EN DE 100% DIE NIEMAND OOIT GEMETEN HAD: gevraagd als "kunnen we batterij status toevoegen (indien versie met batterij) van robot in scherm?". Dat "indien" bleek precies het probleem. **Wat ik aantrof.** `ReachyRobotAdapter.get_status` gaf `battery_pct=100.0` terug, met de opmerking ernaast: *"SDK exposes no battery reading yet"*. Het schema had `battery_pct: float = 100.0` als default. En de setup-wizard — het allereerste scherm dat een nieuwe eigenaar ziet — drukte dat af als **"battery 100%"**. Een volle batterij is het geruststellendste wat een statusregel kan zeggen, en dat maakt het het slechtste om te verzinnen. **Wat jouw robot echt zegt.** De daemon (firmware 1.9.0) op poort 8000 beantwoordt 93 routes en geen enkele gaat over batterij, power of charge; zelfs `/api/state/full` bevat alleen pose-data. Er ís dus geen meting. Maar `/api/daemon/status` meldt wél `wireless_version: true`, en dát beantwoordt jouw eigenlijke vraag: zit er een batterij in dit toestel. Live geverifieerd tegen 192.168.0.178 met de nieuwe code: `(True, None)` — batterij aanwezig, niveau niet gerapporteerd. **Wat er nu staat.** Drie toestanden, drie zinnen, nooit een verzonnen getal: een percentage zodra iets het meet, "mains powered — no battery" voor de bedrade versie, en "battery fitted · level not reported by this firmware" voor die van jou. Onbereikbare daemon zegt "unknown" in plaats van het oude 100%. In het Robot-scherm staat het als vierde feit onder Connection, naast Address/State/Mode/Following; een écht laag niveau kleurt rood, de "niet gerapporteerd"-melding blijft rustig — dat is een feit, geen alarm. De wizard zwijgt nu over de batterij tenzij er een meting is, want een eerste-start-scherm is niet de plek om een firmwarebeperking uit te leggen. De hele keten (schema → adapter → `/robot/status` → store → scherm) draagt het getal al, dus de dag dat Pollen een meting toevoegt verschijnt het vanzelf: `_read_hardware` leest `battery_pct`/`battery_level` mee als de daemon ze ooit stuurt. De fake adapter houdt zijn gesimuleerde batterij — dat is een simulatie en zegt dat ook. Vier tests, rood geverifieerd op de oude code (`'RobotState' object has no attribute 'has_battery'`), waaronder expliciet "een onbereikbare daemon zegt unknown, niet vol". shared-schemas 142, robot-runtime 100, brain+orchestrator 834, console 138 groen, ruff schoon, build schoon.
- 2026-08-30 — U271 EEN GEZICHT HERKENNEN OP 34 PIXELS: gemeld als "photos are quite small, on click picture ad larger preview to more easily recognize". De thumbnails bij **Unknown visitors** zijn 34×26 px, en het enige wat die rij van je vraagt is beslissen **wie** dat is — precies de handeling die op dat formaat onmogelijk is. Hetzelfde geldt voor de “recently seen”-snapshots, waar de vraag is of een opname überhaupt bij deze persoon hoort. Beide foto's zijn nu aanklikbaar en openen een `PhotoLightbox`: één foto groot, met zijn onderschrift, en weg via de knop, de achtergrond of Esc — een klik op de foto zélf sluit niet, want dan zou kijken hetzelfde zijn als wegklikken. Bij een onbekende bezoeker reist de **tag-keuze mee de lightbox in**: je vergroot hem juist om te beslissen wie het is, en die beslissing daarna moeten maken door te sluiten en dezelfde minuscule rij terug te zoeken is de vervelende helft van het werk. Vier tests, waaronder expliciet dat de achtergrond wél en het paneel niet sluit, en dat de Esc-listener bij unmount weer wordt opgeruimd. Console 142 groen, build schoon.
- 2026-08-30 — U272 ZIJN HELE GEHEUGEN ZAT ALS ÉÉN BOLLETJE IN DE GRAPH: gevraagd als "is graph only taking skills into account or also showing memory (these can be eg in other colouring/styling with key words?)", en daarna precies aangewezen: "currently memory is single bullet in graph". **Wat de graph tekende.** Feiten (plus hun `[[wiki-links]]` als gedeelde knopen), skills en signals. Geheugen zat er wél in, maar als **één knoop** — want langetermijngeheugen wordt bewaard als één enkele ProfileFact met key `memory` waarvan de waarde de hele bullet-lijst is, en de graph tekent één knoop per feit. Alles wat hij ooit over iemand geleerd had, afgekapt op 40 tekens: "memory: - Jan is actief en geniet van…". **Wat er nu staat.** Elke bullet is een eigen knoop in een eigen kleur (zacht violet, los van het feiten-blauw en het skill-groen), en het label is niet de zin maar de **woorden die die regel onderscheiden** — een zin is een waardeloos knooplabel. Woorden die in méérdere regels voorkomen worden zelf gedeelde knopen, en dát maakt er een web van: je ziet in één oogopslag dat drie losse dingen die hij onthouden heeft over hetzelfde onderwerp gaan. Bij hover neemt de volledige zin het label over, want een trefwoord alleen mag je niet laten raden. Geen LLM en geen netwerk: dit draait op elke frame van een graph die je zit te slepen, dus botte maar voorspelbare woordfrequentie wint van een slimme gok die tussen frames verandert. De eigen naam van de persoon wordt genegeerd — die staat in bijna elke regel en zou anders élk knooplabel winnen. Een woord telt één keer per regel, zodat herhaling binnen één zin geen thema wordt. Acht tests, waaronder stabiliteit over renders heen en een lege/rommelige notitie die geen knopen mag verzinnen. Console 150 groen, build schoon.
- 2026-08-30 — U273 DRIE SCHERMEN MET EEN "VOICE", EN GEEN ENKEL SCHERM ZEI WELKE WINT: gevraagd als "the default voice in settings, whats difference in between the one selected in robot? how are they used? can we make it more clearer". **Het eerlijke antwoord was ongemakkelijk.** De stem van de persona wint, en élk ingebouwd karakter komt mét een stem (Friendly Assistant is `coral`) — dus de Settings-keuzelijst die `alloy` aanwees was nog nooit gebruikt. Het bijschrift zei alleen "modes can override it in Modes": het noemde één van de twee dingen die er boven staan, en liet juist degene weg die in de praktijk beslist. **En de mode-stem werkte niet eens.** Modes schrijft `TTS_VOICE_<MODE>`, terwijl `resolve_voice` `TTS_VOICE_<PERSONA>` las. Die twee vallen alleen samen zolang een mode nog de persona gebruikt die naar hem vernoemd is — dus zodra je Home de persona "Friendly Assistant" gaf, was de stem die je in Modes had ingesteld onvindbaar geworden. **Derde vondst:** het Present-scherm heeft een eigen Voice-keuzelijst, maar de presentatie riep `synthesize_b64(text)` aan zonder mode én zonder persona, dus elke beat klonk in de Settings-standaard, wat de spreker ook had gekozen. Nu beslist één functie het, en die kan het ook uitléggen (`explain_voice` geeft de stem én waar hij vandaan komt): persona-stem → stem van de huidige mode → Settings-standaard → `alloy`. Beide sleutels worden geraadpleegd, mode eerst, dus een hernoemde persona breekt niets meer. In Settings staat nu de volgorde uitgeschreven én, daaronder, **met welke stem hij op dit moment echt praat en welke keuze dat besliste** — dat veld spreekt de keuzelijst ernaast regelmatig tegen, en dat is precies de bedoeling. De persona-keuzelijst in Robot zegt in zijn tooltip dat hij de andere twee verslaat, en de Present-stem zegt dat hij geldt tenzij de persona zijn eigen stem meebrengt. Zes tests, rood geverifieerd op de oude code. Brain 450, orchestrator 390, console 150 groen, ruff schoon, build schoon.
- 2026-08-30 — U274 PER PERSOON: IN WELKE TAAL, EN ALS WELK KARAKTER: gevraagd als "per person, add option to select default language and default robot" — met "robot" bedoeld als het karakter waarin hij verschijnt (nagevraagd; AURA kent één fysiek toestel, geen robotregister). Twee velden op een persoon, allebei leeg by default, en **leeg betekent "volg de huisinstelling"** — een instelling per persoon mag nooit stiekem een tweede globale instelling worden. `language` (bv. `fr`) wint van de huisinstelling in de systeemprompt: een gezin is zelden eentalig en één globale keuze kan hoogstens voor één van hen kloppen. `character` bepaalt als wie hij die persoon tegemoet treedt — de kindercompagnon voor een kind, de korte voor de eigenaar aan het werk — en wordt zowel in de begroeting als in de spraak/beweging toegepast; opgeslagen als het **id** van het karakter, niet de weergavenaam, zodat hernoemen geen profielen wees maakt. **Twee bugs onderweg gevonden, allebei in dezelfde endpoint.** (1) `PUT /people/{id}` beloofde in zijn eigen commentaar "omitted fields keep their current value", maar bouwde de Person opnieuw op uit drie met naam genoemde velden — dus alles wat er later bij kwam werd bij élke update op zijn default gezet: **iemands rol wijzigen wiste zijn foto**. Hij vertrekt nu vanaf de opgeslagen persoon, wat een veld dat later wordt toegevoegd niet kán vergeten. (2) Het personenscherm bood de rol **"kid"** aan. Die heeft nooit bestaan — de brain kent `owner/family/guest/minor/demo` — dus elke poging om iemand als kind te markeren werd met 422 geweigerd, en geluidloos, want een mislukte rolwijziging toonde niets: de keuzelijst sprong gewoon naar de nieuwe waarde alsof het gelukt was. Uitgerekend de rol die er het meest toe doet, want over een minderjarige wordt niets passief geleerd (ADR-008 §10). Nu `minor`, met een label dat zegt wat het betekent, en een zichtbare foutmelding als een wijziging wordt geweigerd. De test die dit afvangt leest de échte `.vue` en vergelijkt de aangeboden rollen met de enum van de brain — in béide schrijfwijzen, want mijn eerste versie begreep alleen `<option value="x">` en gaf daardoor groen op de kapotte code. Brain 450, orchestrator 390, shared-schemas 142, console 150 groen, ruff schoon, build schoon.
- 2026-08-30 — U275 "HEY RICHIE" EN GEEN REACTIE — HIJ HOORDE JE WEL: gemeld als "ik roep robot 'hey richie' met wakeword, maar krijg geen reactie". **Eerst gemeten, niet geraden.** Via `POST /voice/listen` één seconde opgenomen op de robot: transcript `"Richie"`, antwoord "Hey! Hoe gaat het vandaag?". Microfoon, spraakherkenning en pipeline werkten dus alle drie perfect — de fout zat in de poortjes van de luisterlus, en die aanroep slaat er precies twee over. **De oorzaak.** Roep je alleen zijn naam, dan hoort hij dat, en opent hij één extra venster om je opdracht op te vangen (U93/U96 verwijderden terecht het generieke "waarmee kan ik helpen" — dat gaf spookbeurten bij elke losse "Richie" die Whisper uit ruis viste). Maar hij gaf géén enkel teken dat de naam geland was. Jij wacht op een reactie, hij wacht op een opdracht, het venster loopt leeg, en hij geeft het stilzwijgend op. Van buitenaf niet te onderscheiden van doof. Nu knikt hij: kort, zonder geluid, zonder LLM-aanroep, en dus zonder dat het een gespreksbeurt kan wórden — het zegt alleen "ga door". `WAKE_ACK=off` zet het uit. **En het echte gebrek: het was van buitenaf niet te díagnosticeren.** De lus had geen status, zijn enige logregels staan op INFO terwijl de gebouwde app op WARNING logt, en een taak die via `create_task` sterft neemt zijn exception mee het graf in. Vijf verschillende oorzaken achter één stilte: nooit gestart, uren geleden gecrasht, de kamer onder de luidheidsdrempel (`VOICE_SPEECH_PEAK` gooit een venster weg vóór er ook maar getranscribeerd wordt), de naam gehoord maar geen opdracht erna, of hands-free gewoon uit. `GET /voice/status` vertelt nu welke: draait hij, luistert hij, wat was het laatste volume tegenover de drempel die het opat, wat verstond hij als laatste, hoe lang geleden, en waaróm ging de vorige uiting nergens heen — plus de exception als de taak is omgevallen. Zes tests, waaronder expliciet dat een dode lus als dood wordt gerapporteerd en niet als stil, en dat een onbereikbare robot de knik kost en niet de beurt. Brain 456, orchestrator 390, console 150 groen, ruff schoon.
- 2026-08-30 — U276 JE VERTELT HEM IETS EN HET WORDT STIL VERGETEN: gemeld als "terwijl ik (jan) vertel tegen robot geef ik informatie, maar ik zie dat hij niet gebruikt in zijn kennisopbouw". **De oorzaak.** De keuze bovenaan het scherm ("Jan · owner · tap to switch") verliet de browser nooit: `setSpeaker` zette een ref in een Pinia-store en verder niets. De actieve persoon van de brain kwam uitsluitend uit gezichtsherkenning — en op een profiel zónder aangeleerd gezicht, wat elk vers profiel is en precies de toestand waarin je zat, kende de brain dus niemand. Langetermijngeheugen hangt aan die persoon (`if hook and self._active_person_id`), dus alles wat je vertelde werd keurig beantwoord en daarna weggegooid — terwijl het Memory-tabblad er pal boven beloofde dat het "automatisch uit je gesprekken groeit". De console toonde een toestand die de backend niet deelde: dezelfde ziekte als U266 (overlay), U269 (spraak) en U273 (stem), nu op de plek waar het het meest kost. **Nu.** `POST /knowledge/speaker` vertelt de brain wie er zit, en `setSpeaker` roept dat aan; `GET /knowledge/speaker` zegt wie hij dénkt te spreken én — het eerlijke deel — of hij op dit moment überhaupt iets toeschrijft. Een gast is niemand om tegen te onthouden en zet de toeschrijving expliciet uit; een onbekende persoon wordt met 404 geweigerd in plaats van stil genegeerd. En het Memory-tabblad zwijgt niet langer: staat er niemand, dan staat er **"Nothing is being remembered right now"** met wat je eraan doet (kies wie je bent, of leer hem dit gezicht). Vijf tests. Brain 461, orchestrator 390, console 150 groen, ruff schoon, build schoon.
- 2026-08-30 — U277 WAAROM JE EIGEN, AANGELEERDE GEZICHT ALS ONBEKENDE BINNENKOMT: gemeld met "ik had dit gedaan maar bij unknown visitors kwam ik er ook op — ik ga er vanuit dat hier een mindere mate van zekerheid is en zo bij kan dragen tot trainen als ik hier tag met de juiste persoon". **Beide helften van die lezing kloppen**, en geen van beide was ergens te zien. Taggen doet inderdaad `_matcher.enroll(person_id, entry.embedding)`: dat schot wordt aan het gezicht van die persoon toegevoegd en herkenning wordt er meetbaar beter van — elke hoek die je tagt maakt de volgende herkenbaar. En een gezicht belandt in die lijst omdat zijn beste match ónder `RECOGNITION_THRESHOLD` (0.4) bleef: andere hoek, ander licht, verder weg. `identify()` rékent die bijna-match uit en gaf hem terug, maar de lijst gooide hem weg — dus een gezicht dat je tien minuten eerder had aangeleerd verscheen als vreemde, zonder enige aanwijzing waarom, en zonder manier om "dit ben jij in slecht licht" te onderscheiden van "dit is echt iemand anders". Nu staat er bij elke rij **"closest: Jan (0.34 of 0.40 needed)"**. Live berekend, niet opgeslagen, zodat een pas aangeleerd gezicht álle openstaande waarnemingen meteen opnieuw scoort in plaats van een verouderd getal te tonen. Daarvoor kreeg de matcher `closest()` — `identify()` antwoordt onder de drempel bewust "niemand", wat klopt voor herkennen en nutteloos is voor het uitléggen ervan — plus een leesbare `threshold`. En na het taggen zegt het scherm wat er gebeurd is: *"he now has 5 shots of that face"*, want de bevestiging dat er getraind is ontbrak volledig. Vier tests, waaronder expliciet dat de getagde hoek daarna wél herkend wordt. Brain 465, orchestrator 390, shared-schemas 142, console 150 groen, ruff schoon, build schoon.
- 2026-08-30 — U278 EEN CORRECTIE OP ZIJN GEHEUGEN WERD OPGESLAGEN, GETOOND NOCH GEBRUIKT: gemeld als "bij memory, wanneer ik aanpassing (correctie) maak lijkt hij niet te saven". Hij sloeg wél op — als een **tweede** feit. De Save-knop riep `addFact(person, 'memory', text)` aan, en dat voegt tóe; beide lezers (dit scherm én `PersonMemory` in de brain) pakten de **eerste** treffer, dus de oude. Je correctie werd bewaard, nooit getoond, en bereikte het model nooit — de ergste van de drie, want een correctie maak je juist op het moment dat het moet aankomen. De eigen graph van de eigenaar liet de schade zien: **acht knopen**, allemaal "memory: - Jan is actief e…", één per druk op Save. Vervangen is een andere handeling dan toevoegen en krijgt daarom een eigen route (`PUT /knowledge/people/{id}/memory`) in plaats van een feit-POST die toevallig een gereserveerde sleutel gebruikt. Die verwijdert **álle** memory-feiten en schrijft er één — dus een store die al dubbels had verzameld herstelt zichzelf bij de volgende opslag in plaats van er nog één bij te krijgen; `PersonMemory.set_memory` doet nu hetzelfde. Het scherm toont intussen de **laatste** notitie in plaats van de eerste, zodat een al vervuilde store meteen laat zien wat je het laatst schreef, en na opslaan staat er "Saved — this is what he reads from now on". **Onderweg gecorrigeerd:** mijn eerste versie van de route koos tussen twee stores (die van de router, of die van `ctx.person_memory`); los slaagden de tests, in de volledige suite schreef hij de notitie in een ándere store dan er gelezen werd. "Meestal hetzelfde object" is niets om op te bouwen — nu altijd de store van de router. Vijf tests, waaronder expliciet de acht dubbels die tot één moeten inklappen. Brain 470, orchestrator 390, console 150 groen, ruff schoon, build schoon.
- 2026-08-30 — U279 DE LEGENDA KENDE "MEMORY" NIET, EN DE GRAPH LAS DE VERKEERDE NOTITIE: gevraagd als "splits memory op met keywords (on hover krijg je de betere uitleg), en pas styling aan wanneer het memory item betreft; nu staat alles als '- memory: ...'". Het splitsen, de trefwoord-labels, de volledige zin bij hover en de eigen kleur zitten er sinds **U272** al in — het screenshot komt uit een build van vóór die release, en het volledige-scherm-scherm gebruikt exact hetzelfde `KnowledgeGraph`-component. Wat er wél nog ontbrak, waren twee dingen. (1) De **legenda** boven die weergave noemt People/Facts/Skills/Topics en had nooit een regel voor Memory gekregen: de knopen hadden dus een eigen kleur die nergens werd benoemd, en een kleur die niets uitlegt is geen styling maar ruis. De kleur staat nu als `MEMORY_COLOUR` naast de code die die knopen bouwt, zodat het doek en de legenda die hem verklaart niet uit elkaar kunnen lopen. (2) De graph las de **eerste** memory-notitie, en door de bug van U278 stonden er acht — precies zichtbaar op het screenshot, acht knopen die allemaal "memory: - Jan is actief e…" lezen, één per druk op Save. Hij leest nu de **laatste**, net als het Memory-tabblad, zodat een nog niet opgeschoonde store meteen toont wat je het laatst schreef in plaats van de notitie die je al gecorrigeerd had. Console 150 groen, build schoon.
- 2026-08-30 — U280 WAT HIJ OVER IEMAND ANDERS LEERT, HANGT NU AAN DIE PERSOON: gevraagd als "kan hij vandaag al linken leggen tss persona? bv. als ik praat als jan, over jappe, dan kan hij ook kennis opbouwen over jappe op dat ogenblik". **Wat er al was.** Hij onthield Jappe wel degelijk — "relationships" staat in de bewaarlijst van de distiller, dus "Jans zoon Jappe is 13" belandde netjes in Jans geheugen. En de graph kan `[[naam]]` al sinds het begin omzetten in een gedeelde knoop, en een naam die hij als persoon herkent in een aanklikbare persoonsknoop. **Wat ontbrak** was de verbinding tussen die twee: de distiller was nooit verteld dát die syntax bestond. Twee mensen die de eigenaar allebei zelf had aangemaakt zaten dus in één huishouden zonder één lijn ertussen. Nu krijgt de distiller de lijst van wie er al een profiel heeft, met de opdracht hun naam als `[[naam]]` te schrijven zodra het gesprek over hen gaat — en uitdrukkelijk nooit voor iemand die niet op die lijst staat. De spreker zelf staat er niet bij (een pagina naar zichzelf linken zegt niets) en het demo-profiel evenmin: fictie hoort niet in een echt huishouden geweven te worden. Aan de graph-kant leest een geheugenregel zijn `[[refs]]` nu uit en maakt er een echte rand van naar diezelfde gedeelde persoonsknoop waar de feiten al aan hingen; op het doek verschijnt de zin zónder de haakjes, want die zijn bedrading, geen tekst. **Bewust níet gedaan:** automatisch een profiel aanmaken voor elke naam die in een gesprek valt. Dat is een andere beslissing met een ander gewicht — zeker voor een kind, en deze app leert over een minderjarige principieel niets passief aan (ADR-008 §10). Dat blijft aan de eigenaar. Vijf brain-tests en vier console-tests. Brain 475, orchestrator 390, console 154 groen, ruff schoon, build schoon.
- 2026-08-30 — U281 HIJ MAG NU ZELF EEN PROFIEL AANMAKEN — ZONDER ER TWEE TE MAKEN: gegeven als "hij mag automatisch profiel maken (brain blijft lokaal binnen familie), maar indien persoon al bestaat (in dit geval is er al jappe persona), moet hij link kunnen leggen gezien context of voorstellen". Die voorwaarde ís de hele moeilijkheid: het model schrijft `[[Jappe]]`, het profiel heet `jappe`, en een naïeve aanmaak zet een tweede Jappe naast de eerste — waarna alles wat over één kind bekend is stilletjes over twee pagina's verdeeld raakt. Daarom wordt elke link **eerst opgelost** en zijn de drie uitkomsten bewust verschillend. Eén bekende treffer (op id, weergavenaam, of een unieke voornaam — "Priya" vindt "Priya Sharma") wordt herschreven naar het canonieke id, zodat de graph hem oppikt. **Meerdere** kandidaten (twee Jannen) worden **niet gegokt**: de haakjes verdwijnen en de zin blijft gewone tekst, want een verjaardag aan het verkeerde profiel hangen is erger dan geen link. Geen enkele treffer levert een nieuw profiel op, als `guest` en gemarkeerd met `auto_created`, zodat in People een chip "added by him" staat en een huishouden nooit hoeft te raden waar een profiel vandaan komt. **Eerlijk over de grens.** Alles wat het model tussen `[[…]]` zet wordt een profiel. De prompt zegt "only real people, never places, teams, products or pets", maar een prompt is een instructie, geen filter — mijn eigen suite bewees dat meteen door `[[Reachy Mini]]` tot een persoon te promoveren. Niets lokaals kan "Rik" betrouwbaar van "Reachy Mini" onderscheiden, dus de verdediging is wat óók werkt als hij het mis heeft: een plafond van drie per distillatie, en een zichtbaar merkteken dat in één klik te verwijderen is. Dat staat als test vastgelegd, zodat niemand de prompt later voor een filter aanziet. Acht tests. Brain 491, orchestrator 387, shared-schemas 142, console 154 groen, ruff schoon, build schoon.
- 2026-08-30 — U282 DE FOUT BIJ HET BEWAREN VAN EEN SCENARIO WAS EEN PYDANTIC-DUMP: gemeld met een screenshot van een muur rood onder de builder — veldpaden, de repr van elke beat, `[type=value_error, input_value={...}]` en een link naar de pydantic-documentatie. **De klacht zelf klopte**: beat-3 was een speak-beat zonder tekst en beat-4 een improvise-beat zonder topic; dat zijn echt ongeldige beats. Alleen de manier waarop hij dat zei was onleesbaar. Het pijnlijke: `_readable()` bestaat al sinds **U264** en is precies hiervoor geschreven — hij was toen op de laad-route aangesloten en op de bewaar-route niet, dus Save gaf al die tijd de rauwe dump terug. Nu leest er één zin: *"beat 'beat-3': speak mode needs 'text'; beat 'beat-4': improvise mode needs 'topic'"* — die zin schrijven de validators zélf al, hij moest alleen uit de wikkel gehaald worden. Daar bovenop: met vier beats op het scherm laat één zin onderaan je nog steeds kaarten tellen om te vinden wélke fout is. De melding noemt de id's, dus de console leest die eruit en **omrandt de betreffende beats in het rood**, met eronder welke dat zijn. Twee tests, rood geverifieerd op de oude code met exact de gemelde melding. Brain 493, orchestrator 387, console 154 groen, ruff schoon, build schoon.
- 2026-08-30 — U283 CI STOND ZES UUR ROOD EN IK RAPPORTEERDE GROEN: gemeld als "is er een probleem met releases? want wijzigingen komen niet door, laatste release is 6h geleden". Ja, en het was mijn schuld. CI was groen tot en met U268 en **brak op U269**; elke push daarna faalde, dus er werd geen release meer gebouwd — precies dat gat van zes uur. **De oorzaak.** U269 liet `_speak` echt spraak synthetiseren en werpen wanneer dat niet lukt (correct gedrag: een stille robot mocht niet langer op een geslaagde beat lijken). Maar drie bestaande presentatietests controleren dát de robot iets zei, en `synthesize_b64` geeft `None` terug zonder `OPENAI_API_KEY`. Op mijn machine stáát die sleutel in de shell — dus lokaal slaagden ze, terwijl ze stilletjes échte TTS-aanroepen deden — en op CI, zonder sleutel, faalden ze. Mijn "groen" hing dus aan toevallige credentials in mijn omgeving, en dat is geen test. De fixture stubt nu `voice.synthesize_b64`, zodat die tests meten wat ze horen te meten (vuurt de beat?) en niet of de machine een sleutel heeft — én zonder netwerk of kosten. Geverifieerd door alle negen pakketten te draaien exact zoals CI ze aanroept (`uv run --package … --extra dev`) mét lege `OPENAI_API_KEY` en `ANTHROPIC_API_KEY`: shared-events 5, shared-policies 6, shared-personas 5, robot-runtime 100, memory-service 17, orchestrator 387, conversation-runtime 22, connector-service 52, aura-brain 493 — allemaal groen. **Les:** "lokaal groen" is geen bewijs zolang de omgeving iets meelevert dat CI niet heeft; de suite hoort tegen lege credentials gedraaid te worden voordat er groen gemeld wordt.
- 2026-08-30 — U284 RELEASE-NOTES DIE EEN MENS WIL LEZEN — EN DIE NIET LEEG STONDEN: gevraagd als "maak voor release notes meer commerciele en gebruikersvriendelijke template die gebruikt wordt bij elke release (en pas deze onmiddellijk toe), behoud hierin ook zeker de screenshots". **Twee dingen waren mis.** Ten eerste las de pagina als een bouwlog: een kale "## AURA v1.2.3", een lijst unit-titels en een tabel met bestandsnamen; niets zei waaróm je die update zou willen, en de enige menselijke zin ging over notarisatie. Ten tweede — en dat was erger — **stond de lijst leeg**. De oude stap schraapte de ledger op `- [x] **Titel**`, het formaat van rond U180; alles wat sindsdien geschreven is leest `- 2026-08-30 — U283 TITEL: verhaal`, dus de sectie "Nieuw in deze release" renderde al maanden niets. Een changelog die stilletjes tot geen changelog verwordt is erger dan geen: hij ziet er onderhouden uit. Nu staat de pagina in `scripts/release_notes.py` in plaats van in veertig regels bash in de YAML, zodat hij te lezen, te reviewen en te **testen** is — met een CI-stap erbij, want precies het ontbreken daarvan liet de vorige versie wegrotten. De template leidt met wat er veranderde en hoevéél, houdt de screenshots (inclusief de U235-regel: staat er geen, dan zégt de pagina dat), en heeft een installatietabel per systeem, een "voor het eerst?"- en een "al een vorige versie?"-alinea (je mensen en herinneringen blijven staan), en een korte waaróm-AURA met de nadruk op lokaal. GitHubs automatische notities staan uit: die plakken er juist de muur `auto(U283): …` onder die deze template vervangt; de technische geschiedenis wordt in de voettekst gelinkt. **Drie bugs gevonden door de generator écht te draaien**: hij codeerde het pijltje niet op een cp1252-console (werkt toevallig op de runner, en dus onbetestbaar lokaal), "CI" werd "Ci" toen de hoofdletters eruit gingen, en een titel met een dubbele punt erin — U274's "PER PERSOON: IN WELKE TAAL…" — werd afgekapt tot "Per persoon". Twaalf tests. Droogdraai op de echte historie levert 15 punten op.
- 2026-08-30 — U285 RELEASE-NOTES IN HET ENGELS, GEBOUWD UIT DE COMMIT-LOG: gevraagd als "release notes altijd in engels". De template van U284 was Nederlands, en — belangrijker — zijn opsomming kwam uit de **ledger**, die Nederlands proza is. Dat vertaalt geen build-stap. Maar elke unit landt al als precies één commit met een Engelse titel (`auto(U284): release notes a person wants to read`), dus de **commit-log ís de changelog**: juiste taal, juiste granulariteit, en niets extra's om synchroon te houden. Het schrapen van de ledger was altijd de omweg naar dezelfde lijst — U284 deed het, en de versie ervóór deed het fout. Het unitnummer valt weg (dat zegt ons alles en de installateur niets), commits over de leidingen (`chore`, `docs`, merges) blijven van de pagina, en de lijst kapt op 25. De pagina zelf is nu volledig Engels: wat er veranderde en hoevéél, de screenshots (met de U235-regel: staan ze er niet, dan zegt de pagina dat), een installatietabel per systeem, een "first time?" en een "already on an older version?" — met de geruststelling dat mensen, herinneringen en instellingen blijven staan — en een korte why-AURA die op lokaal blijven leunt. Twaalf tests, waaronder expliciet dat er geen Nederlands meer in de pagina staat. Droogdraai over de hele oogst van vandaag: 16 punten, allemaal leesbaar Engels.
- 2026-08-31 — U285b "1 IMPROVEMENT, EACH ONE FROM…": de eerste Engelse release (v2.0.104) bevatte één unit, en de openingszin las daardoor "This release brings **1 improvement**, each one from something that went wrong" — meervoudsgrammatica op de enige zin die iedereen leest. Mijn test controleerde wél `"1 improvements" not in page` maar niet de zin eromheen, dus hij gaf groen op kromme copy. Nu twee formuleringen ("one improvement, from…" tegenover "N improvements, each one from…") en een test op béíde takken.
- 2026-08-31 — U286 DE OVERLAY BLEEF HET OUDE KARAKTER DRAGEN: gemeld als "when changing robot character, robot overlay is not changing accordingly". Dezelfde familie als U269 (de overlay kende de beats niet) en U276 (de spreker verliet de browser nooit): een **tweede venster met een eigen kopie** van iets dat het eerste venster wijzigt. Het gekozen archetype wordt in `localStorage` bewaard en werd **precies één keer** gelezen — bij het aanmaken van de store, dus bij het openen van dat venster. Kies je in de console een ander karakter, dan schrijft die zijn eigen venster bij en blijft de overlay de rest van de talk het oude gezicht op de beamer tonen. De browser meldt zo'n wijziging al aan élk ander venster van dezelfde origin via het `storage`-event; er luisterde alleen niemand. Nu wel, met de randgevallen erbij: een onbekende waarde wordt genegeerd (een rare waarde mag de beamer niet blanco maken) en een gewiste sleutel valt terug op de standaard. Binnen hetzelfde venster blijft Pinia het werk doen — een `storage`-event vuurt nooit in het venster dat de wijziging veroorzaakte. Vijf tests, twee ervan rood geverifieerd op de oude code. Console 159 groen, build schoon.
- 2026-09-01 — U287 HIJ VERSTOND NEDERLANDS ALS DUITS, EN DE TELEVISIE ALS ZIJN NAAM: twee meldingen die dezelfde oorsprong bleken te hebben — "robot vangt soms maar half op wat in het Nederlands gezegd wordt en springt dan naar een andere taal zoals Duits of zelfs Aziatische talen" en "soms wordt er op de achtergrond onnozel gedaan of speelt televisie, hij zou daar niet mogen op reageren". **(1) De taal werd bij élke opname opnieuw geraden.** `ASSISTANT_LANGUAGE=auto` betekende "geen taal vastzetten", dus de spraakherkenning detecteerde per fragment — en juist bij een korte of half opgevangen uiting gaat dat mis: "hallo" is even goed Duits, en ruis komt terug als wat het model het waarschijnlijkst vindt, inclusief schriften die hier niemand schrijft. `auto` betekent nu **de taal van dit huishouden**; `multi` is de expliciete uitweg voor wie écht binnen één zin wisselt (U130's reden, nu een keuze in plaats van de standaard). **Belangrijk detail:** de volgorde is expliciet → machine-locale → `LANGUAGE_FALLBACK`, want die twee beantwoorden verschillende vragen. Op de machine van de eigenaar stond de fallback op **`fr`** terwijl de locale `Dutch_Belgium` is; met de fallback eerst had ik de microfoon op Frans vastgezet en de klacht juist erger gemaakt. **(2) Een transcript in een ander schrift wordt weggegooid.** Han, Cyrillisch of Arabisch in een Nederlands huishouden is geen transcript maar het model dat woorden verzint uit tv of kamergeluid; het antwoord daarop is een antwoord aan niemand. "Meestal", niet "enig", zodat één geciteerd woord de zin niet kost. **(3) De televisie kon zijn naam zeggen.** De fuzzy wake-matcher accepteerde **elk woord dat met de eerste vier letters van het wake word begon** — met "Richie" dus de doodgewone Nederlandse woorden **"richting"** en **"richtlijn"**, plus "rich" en "riches". Een spellingsvariant van een naam is ongeveer even LANG als die naam; een ander woord dat toevallig zo begint niet. Prefix-regel plus lengteverschil ≤1, en twee bewerkingen alleen nog voor namen vanaf zeven letters (twee op zes was een derde van het woord). Geverifieerd: "hey richie", "ritchie", "richy" wekken hem; "richting", "richtlijn", "rich" niet meer. Twintig tests, rood geverifieerd op de oude code. Brain 507 groen (ook zonder credentials, zoals CI draait), orchestrator 387, ruff schoon.
- 2026-09-01 — U288 HIJ ZAG MAAR ÉÉN PERSOON, EN LUISTERDE IN DE TAAL VAN HET HUIS: drie vragen, één unit. **(1) Per persoon een taal bestond al** (U274) maar stuurde alléén het antwoord aan; de microfoon bleef luisteren in de taal van het huis. Nu geldt: wie hij zíet bepaalt waarin hij luistert. Dat kan, omdat herkenning van de **camera** komt en dus klaar is vóór er een woord getranscribeerd wordt. **(2) Hij zag maar één gezicht.** `embed()` gaf het **grootste** gezicht terug — al die tijd, stilzwijgend — dus iedereen behalve wie het dichtst bij de camera stond bestond niet. `embed_all()` levert nu alle gezichten, dichtstbij eerst; het dichtstbijzijnde bepaalt nog steeds tegen wie hij praat (ongewijzigd), de rest bepaalt of de kamer eenduidig genoeg is. Bestaande embedders (en elke testfake) hebben geen `embed_all`, dus de lus valt terug op de enkelvoudige aanroep in plaats van iedereen een methode op te dringen. **(3) De regel bij twee personen is bewust voorzichtig**: één herkende persoon → zijn taal; twee die dezelfde taal delen → die taal; twee die het oneens zijn, of niemand herkend → géén vastzetting, terug naar het huis. Eén van de twee kiezen is een gok die tégen de ander wordt gemaakt. Over de **wake word**-vraag: aanpassen is niet nodig — na U287 botst "Richie" niet meer met "richting"/"richtlijn", en `/voice/status` (U275) laat nu zien wat hij hoort en wat hij weggooit, dus dat is meetbaar in plaats van gokbaar. Zes tests. Brain 513 groen zonder credentials, orchestrator 387, ruff schoon.
- 2026-09-02 — U289 DE REALTIME-SESSIE HOORDE NEDERLANDS ALS SPAANS: gemeld met een screenshot — een vader die Nederlands praat tegen zijn dochter, en de transcriptie komt terug als "Papá, ¿cómo creciste?", vraag én antwoord in het Spaans. **U287 repareerde de verkeerde weg.** Die zette de taal vast in `voice.transcribe`, de pipeline-weg; deze sessie-weg bleef ongemoeid — en dat is nu juist degene die draait (`voice_engine=realtime`, zichtbaar als "realtime" rechtsboven in het gesprek). Zijn sessieconfiguratie noemde wél een transcriptie-**model** en géén taal, dus de API detecteerde per uiting: precies het gedrag dat U287 overal elders wegnam. In diezelfde configuratie staat "reply in the language the user speaks", maar dat is een verzoek over het **antwoord** en zegt niets over hoe de audio überhaupt gehoord is. Nu deelt de sessie dezelfde taalresolutie als de rest (`_stt_language`), inclusief U288's persoonstaal, en laat `multi` de sleutel gewoon weg. De tweede realtime-weg (`realtime_voice`) stuurt de transcriptie mee die er al is en was met U287 dus al gedekt. **Onderweg zelf iets gebroken en gerepareerd:** ik zette de nieuwe helper op modulniveau midden in de klasse, waardoor `run` een geneste functie werd in plaats van een methode. Het bestand parseerde nog gewoon — `ast` gaf groen — en alleen tellen hoeveel methoden de klasse nog had, liet zien dat hij kapot was. Vijf tests, waaronder één die vastlegt dat alle drie de wegen nu hetzelfde antwoord geven. Brain 518 groen zonder credentials, ruff schoon.
- 2026-09-02 — U290 "NOTHING IS BEING REMEMBERED" TERWIJL HIJ WÉL ONTHIELD: gemeld met een screenshot waarop de header "Jan · owner · tap to switch" zegt en de banner er pal onder beweert dat hij niet weet met wie hij praat. De brain rechtstreeks bevragen besliste het: `{"person_id":"jan","remembering":true}`. De backend deed het goed; de console loog. **De oorzaak is een fout van mezelf uit U276.** `_request()` geeft een **`Response`** terug, geen JSON — en mijn code las `body.remembering` rechtstreeks van dat object, waar het eeuwig `undefined` is. Die banner kón dus nooit uitgaan, wat de brain ook zei. Beide functies lezen nu de body echt uit. **Daar bovenop twee zwakheden die het maskeerden.** (1) `remembering` werd één keer opgehaald bij het mounten van de view; herkende hij iemand een tel later, dan bleef het antwoord "niemand" voor de rest van de sessie. Nu wordt het ververst terwijl het scherm open staat, en opnieuw zodra je het Memory-tabblad opent — het gaat over een levende toestand, dus één momentopname is per definitie te weinig. (2) De verzoening liep maar één kant op: een herstartte brain vergeet wie er is, terwijl dit tabblad de persoon nog gewoon in de header toont. Weet de brain niemand en heeft de eigenaar wél gekozen, dan wordt die keuze opnieuw doorgegeven in plaats van stilzwijgend te verschillen; een gast niet, want dat is niemand om tegen te onthouden. Vier tests, twee ervan rood geverifieerd op de oude code. Console 163 groen, build schoon.
- 2026-09-02 — U291 EEN PERSONA WISTE DE ENIGE TAALREGEL: gemeld als "is weer in andere talen aan het spinnen", met een screenshot waarop een Nederlands gesprek in het Portugees en het Spaans beantwoord wordt. **Waarom U287 en U289 het niet oplosten.** Die zetten de taal van de spraak*herkenning* vast, en dat werkte: het bestand met de U289-fix stond om 21:45 op de schijf, de brain herstartte om 21:54, en met de code van de geïnstalleerde app geeft `_stt_language()` netjes `'nl'`. De *antwoordtaal* is een andere zaak, en die stond in `build_instructions` als: `parts = [character_prompt] if character_prompt else [_FALLBACK]`. De enige zin over taal zat ín die `_FALLBACK`. Dus zodra de eigenaar een echte persona koos — Sentinel, op het screenshot — verdween die zin mét de fallback die hij verving, en had het spraakmodel géén enkele taalaanwijzing meer. Een persona-prompt zegt wie hij ís, niet welke taal hij spreekt; die twee tegen elkaar uitspelen wás de bug. De taalregel is nu een eigen blok dat **altijd** wordt toegevoegd, naast de persona in plaats van in de plaats ervan, en hij nóemt de taal ("ALWAYS reply in Dutch") in plaats van vier mogelijkheden op te sommen. Hij zegt er ook bij dat een transcript fout kán zijn — "when that happens the transcript is wrong, not the speaker" — want precies dat sleepte het antwoord mee de verkeerde taal in. Dezelfde of-of stond in de per-beurt realtime-weg en is daar ook weg. **Twee bestaande tests legden het oude gedrag vast** (`assert out == CHARACTER`: een persona-prompt ís de hele instructie) en zijn bijgewerkt met de reden erbij, niet stilzwijgend groen gemaakt. Zes nieuwe tests, alle zes rood geverifieerd op de oude code. Brain 524 groen zonder credentials, ruff schoon. En passant de antwoordtaal van de eigenaar expliciet op `nl` gezet: zolang die op `auto` staat leunt alles op de machine-locale, en expliciet is één afleiding minder.
- 2026-09-02 — U292 IK GAF HEM EEN ZIN OM ZICH ACHTER TE VERSCHUILEN: gemeld als "hij blijft continue praten, zonder duidelijke reden", met de uitgesproken tekst erbij — ruim twintig varianten van "Laat me even naar het fragment luisteren", "Momentje, ik haal de transcriptie op", "Sorry, ik ga nu echt de transcriptie uitvoeren", eindigend op bijna letterlijk de excuuszin die ik zelf had voorgeschreven. **Dit was U291, een uur oud.** Geverifieerd voor ik iets aannam: de tekst `mis-detects a short or noisy` staat in de geïnstalleerde app en de oude formulering is weg, dus mijn instructie draaide. Wat er misging: ik schreef die regel voor een model dat een **transcript leest** — "speech-to-text sometimes mis-detects a short or noisy utterance; when that happens the transcript is wrong, not the speaker". Dit model **hóórt**. Door hem te vertellen dat er een transcript bestaat dat fout kan zijn, concludeerde hij dat er een transcriptiestap ís die hij kan overdoen — en die kondigde hij aan, keer op keer, zonder hem ooit te kunnen uitvoeren. Daar bovenop had ik hem een kant-en-klare zin gegeven voor als hij iets niet verstond; een zin die je aanreikt wordt een zin die gebruikt wordt. **Twee regels die nu in de code staan als commentaar én als test:** beschrijf nooit machinerie waar het model niet bij kan, en geef het nooit een zin om op terug te vallen. De regel zegt nu alleen nog wat hij spreekt, dat hij daar niet van afwijkt, en dat hij niet aankondigt wat hij gaat doen maar het antwoord geeft. Vier nieuwe tests bewaken precies dat: geen woord over transcripts of audio, geen aangereikte excuuszin, wél een verbod op aankondigen, en de regel blijft onder de 400 tekens — elke extra zin over hoe hij werkt is er weer één om uit te spelen. Brain 527 groen zonder credentials, ruff schoon.
- 2026-09-04 — U293 HIJ KENDE JE HUISGENOTEN PAS NÁ HET GESPREK: gemeld met een screenshot waarin de eigenaar over Jappe, Elke en Limme praat — alle drie met een profiel — en hem dat ook zégt. Zijn antwoord: *"Ik ken de namen uit ons gesprek."* Waar, en precies het probleem. Nagevraagd als "leert hij dit zichzelf niet aan?" — dat doet hij, alleen achteraf. **Wat er misging.** Hij kreeg per beurt uitsluitend te horen wie er vóór hem stond (`person_note`). De ledenlijst van het huishouden bereikte wél de geheugendistillatie — dat is U280, die een onthouden regel aan de juiste persoon koppelt — maar nooit het lopende gesprek: `ContextBuilder` bevat geen enkel woord over mensen. Dus tijdens een gesprek kwam een vertrouwde naam binnen als een vreemde, en ná afloop wist hij het weer wel. Nu krijgt elke beurt een korte roster: **namen en rollen** van wie hij al kent, met de expliciete instructie nooit te zeggen dat hij een naam alleen uit dit gesprek kent. Ook de spraakweg krijgt hem, want die roept de pipeline nooit aan en doet dus zonder wat hij niet aangereikt krijgt — exact hoe deze bug ontstond. **Bewust alleen namen en rollen.** Wat hij óver ieder van hen weet blijft achter de judgment-laag, want daar wonen de rolregels: over een minderjarige wordt niets passief geleerd (ADR-008 §10), en ieders feiten in elke prompt stoppen zou een gast het privéleven van het huishouden laten meelezen. Gasten en het demoprofiel blijven eruit: de eerste wordt niet onthouden, de tweede is fictie. Zeven tests, waaronder dat een kapotte store de roster kost en niet de beurt. Brain 534 groen zonder credentials, orchestrator 387, ruff schoon.
- 2026-09-04 — U294 HIJ KAN NU ZÉLF GAAN KIJKEN WIE IEMAND IS: gevraagd als "is dit dynamisch? hij moet zich dit zelf aanleren bij de personen te gaan kijken (ook als er dan bv. nieuwe bijkomen)". **De eerste helft was al waar en is bewezen in plaats van beloofd**: de roster van U293 wordt élke beurt opnieuw uit de store gebouwd, dus iemand die je nu toevoegt staat er in de volgende zin bij — gedemonstreerd door Nora midden in een gesprek aan te maken en de twee opeenvolgende rosters naast elkaar te zetten. Geen herstart, geen cache. **De tweede helft ontbrak volledig.** Hij had geen enkele manier om iemand op te *zoeken*: hij kon het web doorzoeken, bestanden lezen, mail versturen — maar niet in zijn eigen kennisbank kijken. De roster zegt wie er bestaat, meer niet, en dat is bewust: ieders gegevens in elke prompt duwen zou een gast het privéleven van het gezin laten meelezen. Nu is er `look_up_person`, en die gaat **door de judgment-laag** in plaats van langs de store. Dat is geen detail: daar wonen de rolregels, dus een gast levert een naam en verder niets, en over een minderjarige komen alleen expliciete feiten en nooit waargenomen signalen (ADR-008 §10). Een tool die daaromheen las zou een gat in het toestemmingsmodel zijn, vermomd als gemak. Naamherkenning is die van U281 — id, weergavenaam, dan een eenduidige voornaam — waarbij een **exacte** treffer wint van een gedeelde voornaam ("Jan" ís iemands hele naam; "Jan Peeters" begint alleen zo), en twee gelijke voornamen leveren een wedervraag op in plaats van een gok. Iemand die hij niet kent levert een eerlijk "nieuw voor mij" op, geen storing. De tool staat in `_ALWAYS`, dus in élke modus inclusief presentatie: weten wie er besproken wordt is geen bevoegdheid die je eerst moet aanzetten, en voorgesteld worden aan iemand die je al kent is precies het moment om niet met je mond vol tanden te staan. **Onderweg zelf gebroken en gerepareerd:** ik schreef de tool-definitie met de hand als kale dict terwijl elke andere door `_fn()` gaat, en brak daarmee twee ongerelateerde tests die de schemalijst aflopen; nu vastgelegd in een test. Tien tests. Brain 544 groen zonder credentials, orchestrator 387, shared-policies 6, ruff schoon.
- 2026-09-04 — U295 DE VERBINDINGEN-PAGINA SPRAK ONTWIKKELAARSTAAL: gemeld als "don't we have more user friendly ways to connect? this is really dev like", met een screenshot van de Microsoft 365-rij: *"Set M365_CONNECTOR=workiq and register an Azure app for the real one"* en *"Set AZURE_CLIENT_ID or register the default AURA dev app"*. Twee omgevingsvariabelen en een Azure-registratie, in het paneel waarmee een gezin zijn agenda wil zien. De feiten klopten; het publiek niet. **Wat er nog erger aan was:** de tekst zei "paste its id here" terwijl er géén veld stond om iets in te plakken — de console verbergt bij ontbrekende gegevens juist álle besturing. De enige weg was het bewerken van een omgevingsvariabele. Nu staat dat veld er wel, met de app-id als gewone instelling (geen geheim: publieke client-id's, hetzelfde soort dat de gh- en Azure-CLI in hun binaries meeleveren), en Microsofts tenant wordt automatisch op `common` gezet — dat vragen zou een vraag met één antwoord zijn. De verwijzing naar de registratiepagina is nu een **klikbare link** in plaats van platte tekst: "registreer een app" zonder ergens heen te kunnen is geen instructie. En de teksten zelf zeggen wat er aan de hand is zonder één variabelenaam: *"Showing example data, not your real mail or calendar"*, en *"needs a one-time app ID before you can sign in. It is free, and you only do it once"* — want wat erop volgt is echt werk, en dat vooraf zeggen is het verschil tussen een taak en een muur. De variabelenamen reizen nog steeds mee in `missing`, want een diagnose die ze weglaat helpt niemand; het ging om de zin op het scherm. **Wat ik niet kon oplossen:** `defaults.py` bestaat al om meegeleverde client-id's te herbergen zodat je alleen op Connect hoeft te klikken — maar staat leeg met TODO's. Die apps registreren vraagt de accounts van de eigenaar en is geen codewijziging. Vier nieuwe tests, waaronder een regex die élke ALL_CAPS-variabelenaam uit de zichtbare teksten weert, rood geverifieerd op de oude tekst. Eén bestaande test toetste de letterlijke woorden "canned data" in plaats van de belofte eronder; nu toetst hij de belofte. connector-service 56, brain 544, console 163 groen, ruff schoon.

### U296 — de teach-knop deed niets, en zei dat ook niet

Gemeld als "werkt teach nog? lijkt niks te doen", met een screenshot van een
leeg tekstvak en het toga-knopje ernaast.

De route werkte. `POST /orchestrator/agent/feedback` draait een volledige beurt
en geeft het antwoord terug. De console gooide dat antwoord weg en wachtte op
een WebSocket-event. Drie manieren waarop er dus niets gebeurde, geen enkele
zichtbaar:

* het vak was leeg — `teach()` keerde meteen terug, de enige aanwijzing was een
  tooltip die niemand aanwijst;
* er liep nog een beurt — dezelfde stille terugkeer;
* de POST kwam terug met 503 ("pipeline not ready") of 422. `fetch` gooit
  daar geen fout op, dus de `catch` sloeg nooit aan; het antwoord moest van de
  WebSocket komen, en als dat niet gebeurde bleef de regel "🎓 …" van de
  eigenaar staan met niets erachter.

Een gewone beurt toont het antwoord uit de response en ontdubbelt tegen het
event dat er soms eerder is (U26). Teach doet dat nu ook, en een mislukking
zegt wat er misging in plaats van eruit te zien als een knop die niet is
aangesloten. Het knopje is uitgeschakeld zolang het vak leeg is — een
uitgeschakelde knop legt zichzelf uit — en de tooltip vertelt dan wat je eerst
moet doen.

Vijf tests, geverifieerd rood tegen de oude store.

### U297 — de screenshots in de README waren van de vorige app

Gemeld als "also update screenshots in readme, these are still from the old
app". Ze dateerden van 11 augustus: met de hand gemaakt, vier maanden oud, en
niets kon dat merken — een verouderde afbeelding rendert nog altijd prima.

Dus zijn ze niet opnieuw met de hand genomen. De release-pipeline fotografeert
al sinds U166 een wegwerpstack (nep-robot, echo-model, één verzonnen profiel);
dat script maakt nu ook de plaatjes voor de README, en `scripts/readme_shots.py`
zet ze om naar de .webp-bestanden waar de README naar wijst. "Screenshots
opnieuw nemen" is daarmee een commando in plaats van een namiddag.

Onderweg drie dingen rechtgezet:

* **De header loog over de robot.** `RobotConnected` wordt gepubliceerd wanneer
  de robot verbindt — normaal vóór de console openstaat. U152 schreef
  `syncFromStatus` precies daarvoor en hing hem alleen in het Robot-scherm, dus
  elke start zei "Robot offline" over een robot die gewoon antwoordde, en de
  waarheid verscheen enkel als je ernaar ging zoeken. Nu wordt de status
  gevraagd bij het opstarten en bij elke herverbinding. Het stond op onze eigen
  release-screenshot.
* **`model-roles.webp`** toonde een sectie die alleen bestaat bij provider
  OpenAI — wat een sleutelloze demostack nooit is. Het bestand heette naar iets
  dat er niet op stond en stond nergens meer in de README; vervangen door
  `settings.webp`, dat wél toont wat het belooft.
* **Elke opname begint nu op een verse pagina.** Navigatie in deze console is
  Pinia-state, geen URL: één mislukte klik liet alle volgende opnames op het
  verkeerde scherm staan, en die zagen er nog steeds uit als screenshots.

Vijf tests, waaronder één die controleert dat elke afbeelding waar de README
naar wijst ook echt bestaat, en drie op de robotstore. CI draait ze mee.

### U298 — nee, een app-ID is niet de enige manier

Gevraagd als "app-ids is enige manier? er niks gebruiksvriendelijker?" — een
eerlijke vraag na U295, waarin ik het veld had toegevoegd maar de stap zelf had
laten staan. Voor twee van de drie is er wél een kortere weg, en die zijn nu
gebouwd.

**Agenda via een link.** Outlook, Google Agenda en Apple Agenda geven elk een
privé-abonneelink: één URL die eindigt op `.ics` en de hele agenda als tekst
teruggeeft. Plakken duurt dertig seconden: geen app-registratie, geen
toestemmingsscherm, geen aanmelding, niets dat een beheerder ergens kan
intrekken. Het levert minder op dan een echt account — alleen lezen, alleen
agenda, geen mail en niets versturen — maar "wat staat er vandaag" is de vraag
die een gezin stelt, en die wordt nu beantwoord zonder iemand naar
portal.azure.com te sturen. De rij staat bovenaan, want voor de meeste
huishoudens is dit het hele antwoord.

Zelf geparseerd in plaats van met een bibliotheek: `uv sync` snoeit elke extra
die niet gevraagd is, en dat heeft dit project al vier keer gekost (U179, U213,
U246, U266). Wat een abonneefeed gebruikt is klein en stabiel. Achttien tests
uit het gedrag van échte feeds: DTEND is exclusief (anders staat elke
hele-dag-afspraak ook op de dag erna), Outlook schrijft TZID en Google een Z,
en een gezinsagenda bestaat vooral uit herhalingen — precies het stuk dat een
naïeve parser fout doet terwijl het werkend lijkt. `tzdata` toegevoegd, want
Windows heeft geen tijdzonedatabase: zonder dat zou `TZID=Europe/Brussels`
stilletjes op het verkeerde uur landen.

**GitHub had nooit een app nodig.** Een persoonlijk token is één klik op
github.com; de OAuth-app-registratie waar het paneel naar wees is tien minuten
voor hetzelfde resultaat. De store kon zo'n token al opslaan — alleen bood de
rij het veld niet aan.

Onderweg: **de Save-knop uit U295 deed niets op de Microsoft-rij.** Ik had de
map op de connectorsleutel van de brain gezet (`m365`) terwijl de rij zichzelf
`microsoft` noemt, dus de opzoeking gaf niets terug en de functie keerde
zwijgend om. Precies de fout die deze sessie blijft opleveren en precies de
soort die geen enkele test ving. Nu één map, op de rij-id, met een opmerking
erbij dat de twee naamgevingen elkaar alleen hier tegenkomen.

Wat hiermee níét is opgelost: mail lezen, mail versturen en Teams vragen nog
altijd een echte aanmelding, en daarvoor blijft één app-registratie nodig
zolang `defaults.py` leeg staat. Die kan alleen de eigenaar doen.

### U299 — de specs zijn 292 units lang niet meegegroeid

Gevraagd als "waarom zie ik in specify en docs folder geen wijzigingen? ... ga
na wat er is fout gelopen en fix it". Terecht, en het was erger dan het leek.

`.specify/` is in de hele geschiedenis drie keer aangeraakt: de scaffold, U231
en U238. Geen enkele spec noemde ooit een unit; alle veertien stonden nog op
`status: in-progress`, ook die van juni. De ADR's dateren van 21 juni. Wat het
product intussen geworden is, staat uitsluitend in
`docs/implementation-backlog.md`: 420 kB Nederlands proza, één entry per unit,
kloppend en gedetailleerd — maar een dagboek is geen contract. Wie wil weten hoe
het product zich vandaag gedraagt, hoort daarvoor niet de hele
ontstaansgeschiedenis te moeten lezen.

Drie oorzaken, elk op zich voldoende:

1. **De regel stond nergens in beeld.** `AGENTS.md` heet "GitHub Copilot Agent
   Instructions" en de grondwet staat onder `.specify/`. Claude Code laadt
   `CLAUDE.md`, en dat bestond niet. Elke unit in deze stroom is geschreven
   door een agent die principe I nooit gelezen had. Op de vraag "zat dit enkel
   in copilot instructions?": ja.
2. **Niets controleerde het.** De privacy-scan heeft een hook én een CI-job; de
   release notes hebben tests. Traceerbaarheid had geen van beide en verviel
   daarmee tot een gewoonte — en gewoontes overleven geen 292 units op tempo.
3. **Het ledger ving de druk op.** Elke unit een zorgvuldige entry schrijven
   vóélde als documenteren. Er ging moeite in; ze ging naar het verkeerde
   artefact.

Wat er nu ligt:

* `scripts/spec_drift.py` leest de units uit de commitlog en de claims uit de
  `units:`-frontmatter van elke spec, en meldt het verschil. Alleen de
  frontmatter telt: een spec die U263 in een alinea noemt, heeft er daarmee
  geen verantwoordelijkheid voor genomen.
* `.specify/coverage.json` houdt de basislijn bij — de eerlijke grens tussen de
  schuld die er al was en de discipline die nu begint. Het openstaande aantal
  wordt bij élke run getoond, de check zegt nooit "compleet" zolang het niet
  nul is, en een test weigert een basislijn die vooruit beweegt. Omlaag komt ze
  alleen door de spec te schrijven.
* `CLAUDE.md` — de ontbrekende schakel. Spec-first, wat een unit verschuldigd
  is (code + tests, spec, ledger, tekening, ADR), en de praktische valkuilen
  van deze repo.
* Een CI-job naast de privacy-scan, en een waarschuwing in de pre-commit hook
  wanneer er code wijzigt en geen spec.

Spec `015-spec-coverage` beschrijft dit en claimt U299 — meteen het eerste
uitgewerkte voorbeeld van het mechanisme. Zestien tests.

Wat hiermee **niet** is opgelost: de 292 units schuld zelf. Die staat nu geteld
en zichtbaar in beeld, en wordt in de volgende units afbetaald — telkens een
spec geschreven en de basislijn een stuk terug.

### U300 — de teller telde zichzelf te laag

De check uit U299 las één unit per commit-subject, want dat is sinds lang de
regel. De vroege geschiedenis bundelde er meerdere: `auto(U2,U3):`,
`auto(U19c+U20):`, `auto(U112-U115):`. Die tweede en derde unit werden gewoon
niet gezien.

Uitgerekend deze check mag dat niet doen. Een bewaker die zijn eigen schuld te
laag inschat, geeft precies de gerustheid die het probleem in stand houdt. De
werkelijke stand is geen 292 maar **321** units.

Onderweg liep ik in de valkuil die ik één commit eerder in `CLAUDE.md` had
opgeschreven: een heredoc at de `\b` uit de reguliere expressies op en liet er
een letterlijke backspace achter, waarna alles nul units vond. Opgelost, en
vier tests erbij voor de gebundelde vormen.

### U301 — spec 016: het lichaam, eindelijk beschreven

Eerste aflossing van de achterstand uit U299. `016-embodiment-and-presence`
beschrijft wat er in 36 units aan lichaam is gebouwd en nooit is
gespecificeerd: volgen met hoofd én torso, de waakhond en het heroriënteren,
Follow/Manual, slapen dat blijft slapen, stemming via hoofd en antennes, de
tien karakters, en de camera die stil kon vallen zonder dat iets het merkte.

Geschreven vanuit de code, niet vanuit een plan. Waar een beslissing onder druk
is genomen en nog steeds draagt, staat dat er ook bij — zoals dat gebaren met
trefwoorden worden gekozen en niet met een tweede modelaanroep, omdat een
gebaar dat ná de zin aankomt erger is dan een licht verkeerd knikje.

Schuld: 321 → 285.

### U302 — spec 017: stem en taal, en waarom het vier keer misging

Zestig units, de meest herwerkte kant van het product. Het belangrijkste dat
deze spec vastlegt is niet een detail maar een feit dat nergens stond: **er zijn
drie spraakpaden**, geen twee. Pipeline (goedkoop, en het enige pad dat tools
kan aanroepen), realtime per beurt, en de doorlopende realtime-sessie met
server-VAD.

ADR-005 beschrijft dat niet. Die beschrijft één pluggable pipeline met een
lokale fallback, en is op dat punt achterhaald — dat staat nu ook in de spec,
en de ADR zelf wordt in U309 bijgewerkt.

Dat ene ontbrekende feit verklaart vier taalbugs op rij (U287, U289, U291,
U292): telkens een correcte oplossing, toegepast op één pad, terwijl de andere
twee het oude gedrag hielden. Elke keer leek het klaar tot het volgende
gesprek. De spec eist nu expliciet dat een wijziging aan taal, wakegedrag of
instructietekst in alle drie landt, of hardop zegt op welk pad ze slaat.

Ook vastgelegd: de twee regels uit U292, die ik zelf nodig had. Beschrijf nooit
machinerie waar het model niet bij kan, en geef het nooit een zin om zich
achter te verschuilen.

Schuld: 285 → 225.

### U303 — spec 018: kennis, personen en de oordeelslaag

Eenenveertig units rond de kant waar de persoonlijke gegevens staan. ADR-008
beschreef het model in juni en klopt nog grotendeels; wat er niet in stond is
alles wat de laag sindsdien geleerd heeft: gezichten herkennen op woonkamer-
afstand, een profiel laten groeien uit een gesprek, wat je over de één zegt aan
de ánder hangen, en eerlijk zijn wanneer hij niets van dat alles doet.

Expliciet vastgelegd, omdat het echt is: er is **geen tweede kopie** van de
eigenaarssleutel. De wachtzin staat in de Windows-kluis en nergens anders; kwijt
is kwijt, inclusief de profielen en de gezichtsdata.

Ook vastgelegd wat drie keer misging op dezelfde manier — de console die een
kennisstand toonde die de brain niet deelde (U276, U278, U290) — en waarom een
laag-vertrouwen waarneming taggen géén correctie is maar training.

Schuld: 225 → 184.

### U304 — spec 019: vaardigheden, automatisering en de agentische lus

Tweeëndertig units rond het deel dat écht iets kan doen: een commando draaien,
de muis bewegen, een app openen. Alles daar staat onder grondwetsprincipe IV —
veiligheidspoorten zijn onaantastbaar — en de spec legt vast welke gereedschappen
per definitie níét afgesloten kunnen worden. `request_capability` is de
belangrijkste: als om deblokkering vragen zelf geblokkeerd kan worden, moet de
eigenaar logs gaan lezen om te weten wat hij wilde.

De interessantste les staat er ook in, uit U247: een leerlus is nooit eerlijker
dan het verslag waaruit hij leert. Die regel werd vóór de beurt geschreven, dus
hij bevatte de bedoeling en nooit de uitkomst — en het optimalisatieproces werd
gevraagd "guardrails toe te voegen voor de faalgevallen die uit het bewijs
blijken", over bewijs waarin geen enkel faalgeval stond.

Schuld: 184 → 151.

### U305 — specs 020 en 021: de app, de releases, en de robot bijwerken

Eenenvijftig units, in twee specs gesplitst omdat het twee verschillende
werelden zijn. De laptop werkt zichzelf bij bij elke release; de Pi in de robot
niet. Die asymmetrie is grondwetsprincipe X en geen tijdelijke toestand: een
gezin installeert de app zodra ze wordt aangeboden en raakt het
bestandssysteem van de robot ongeveer nooit aan.

De belangrijkste regel in 020 staat er omdat ze ooit ontbrak: alle eigendom van
de eigenaar — profielen, herinneringen, sleutels, instellingen — staat **buiten**
de installatiemap. In U177 stond het erin, en elke update wiste het.

021 legt ook de routine vast die ik vandaag zelf gebruikte: `--check` zegt dat
de robot achterloopt, maar "achter" telt élke commit, en de meeste units raken
`robot-runtime` niet aan. De diff beslist of het uitmaakt — deployen is niet
gratis, het herstart de runtime en dat hakt het gesprek af.

Schuld: 151 → 99. Onder de honderd.

### U306 — spec 022: veiligheid en privacy

Negen units, en het enige gebied waar de lat anders ligt: alles wat hier
misgaat is niet met een volgende release te herstellen. Een kennisbestand dat
van het LAN te lezen was, of gegevens van een gezinslid in een publieke
git-geschiedenis — dat haal je niet terug.

Het dreigingsmodel staat er nu in één alinea: geen statelijke aanvaller maar het
LAN zelf — een smart-tv, een buur op dezelfde wifi, een tabblad dat openstaat,
en een publieke geschiedenis.

`docs/audit-2026-08.md` blijft de levende lijst; de spec legt de vorm vast en
verwijst per punt (S1, S2, …) naar de audit. Ook vastgelegd waarom sommige
keuzes asymmetrisch zijn: de brain bindt op loopback, maar de robot-runtime
móet over het LAN bereikbaar zijn — die zit op een andere machine — en wordt
daarom met een gedeeld geheim bewaakt in plaats van door niet te luisteren.

Schuld: 99 → 90.

### U307 — spec 011 aangevuld: de presentatiecopiloot zoals hij echt is

De apriltekst blijft staan als eerlijk verslag van het oorspronkelijke plan;
eronder staat nu wat het geworden is, met een tabel die per aanname zegt waarom
ze in een echte zaal niet hield.

Het plan ging ervan uit dat de dia's de robot aansturen: dia wordt actief, cue
voor die index wordt uitgesproken. Een presentator praat niet in dia-eenheden.
De helft van de beats vuurt op iets dat gezégd wordt, niet op een overgang —
vandaar triggers `manual`, `slide:4`, `keyword:Java`. En niemand tikt YAML op
een podium, dus de scenario-bouwer in de app is de schrijfplek geworden; YAML
bleef alleen het opslagformaat.

Eén eis staat er scherper dan de rest, omdat U264 liet zien wat het kost:
**niets in het Present-paneel mag gooien tijdens het lezen van een scenario.**
Het werk van de presentator kwijtraken is het ergste wat deze functie kan doen.

Schuld: 90 → 76.

### U308 — specs 008 en 010 aangevuld: de console en de verbindingen

Vijfenveertig units. Voor de console was de vormverandering fundamenteel: het
plan beschreef een **operatorconsole** — panelen die een draaiend systeem
observeren. Wat er staat is het enige scherm dat het product heeft, het venster
dat een gezin opent. Daarmee veranderen de regels: geen icoontjessoep met vijf
schermvullende modals maar één navigatiebalk met namen, en drie dichtheden die
meebewegen met de persoon tegen wie hij praat.

Eén defectklasse staat er expliciet in omdat ze in deze spec het vaakst
terugkomt: **de console die een toestand toont die de brain niet deelt** —
U252c, U252e, U276, U278, U290, U297. De eis is nu dat elke status, capaciteit
en kennistoestand van de brain komt; de console maakt presentatie, nooit
waarheid.

Bij de connectoren was de kern dat `unknown` de enige status is waar de
eigenaar niets mee kan. Zes toestanden nu, elk een ander karwei, en elk met de
volgende stap eraan vast.

De basislijn is voor het eerst teruggeschoven: van U298 naar U224. Alles wat
daarna kwam is nu geclaimd.

Schuld: 76 → 31.

### U309 — de laatste eenendertig, en de schuld staat op nul

De overgebleven units zijn ondergebracht bij de oorspronkelijke specs, met per
spec een korte aanvulling die zegt wat er sinds april écht is gebeurd. De
interessantste:

**001** — de scaffold is geleverd zoals gepland en daarna **ingeklapt**. Zes
compose-services werden er drie; elke router draait nu in één FastAPI-proces en
de HTTP-sprongen ertussen zijn in-process naden geworden. Het zijn één
installatie: een gezin zet één applicatie neer, en een netwerkronde tussen twee
routers in hetzelfde proces is latentie en een faalmodus voor niets. De
modulegrenzen bleven staan — dat is wat de optie openhoudt ze ooit weer te
splitsen.

**003** — twee gevolgen van "één gedeelde bus" die latere units bleven
herontdekken, staan nu opgeschreven zodat het herontdekken stopt. Een event
bereikt alleen een abonnee die bestaat op het moment van publiceren; toestand
die een late abonnee moet overleven wordt **opgevraagd**, niet afgewacht. En de
projectoroverlay zit helemaal niet op die bus.

**013** — inclusief de fout die het waard is te bewaren: U202, waarin mijn eigen
U191 de assistent stil legde en de echo-provider dat verborg. Een schakelaar moet
getest worden tegen de provider waar hij op gaat draaien.

Daarmee is de teller leeg. `.specify/coverage.json` heeft geen basislijn meer:
er wordt niets meer vergeven, elke unit vanaf nu moet door een spec geclaimd
worden of CI valt om.

**331 units, 22 specs, schuld 0.**

### U310 — de ADR's ingehaald

Alle acht ADR's dateerden van april of 21 juni. Zeven zijn nu bijgewerkt, en
twee ervan stonden nog op **"Proposed"** terwijl ze al maanden draaiden —
ADR-007 (de topologie-inklap, uitgevoerd in U1–U11) en ADR-008 (de kennislaag,
waar het hele product op staat).

De belangrijkste is ADR-005. Die staat nu op **gedeeltelijk achterhaald**: de
beslissing beschrijft één pluggable pipeline met een lokale fallback, en dat
klopt alleen nog voor het pipeline-pad. Er zijn er drie, en welk pad je kiest is
een productkeuze in Settings, geen deploymentdetail. Dat ene ontbrekende feit
kostte vier taalbugs op rij.

Verder: ADR-002 kreeg de twee eigenschappen die latere units bleven
herontdekken (een event bereikt alleen wie op dat moment luistert; de overlay
zit helemaal niet op die bus), ADR-004 de lokale-model-trede en het feit dat een
404 van de Pi een verwachte toestand is en geen storing, ADR-006 waarom `unknown`
het echte probleem was en waarom groen verdiend moet worden, en ADR-008 de
verplaatste sleutelparameters plus de zin die er hoort te staan: er is precies
één kopie van die wachtzin en geen herstelpad.

### U311 — twee beslissingen die nooit zijn opgeschreven

**ADR-009 — Honest state.** Deze is laat vastgelegd omdat hij nooit *genomen*
is: hij stapelde zich op, incident na incident, tot bleek dat het de meest
herhaalde les uit driehonderd units was. Tien keer dezelfde vorm: een groen
badge boven verzonnen data (U52), "slapen: gelukt" bij een 404 (U238),
"volgend" terwijl de tracker dood was (U253), "batterij 100%" van een SDK die
geen batterij meet (U270), "er wordt niets onthouden" terwijl hij precies wist
wie er praatte (U290), "CI is groen" terwijl die zes uur rood stond (U283).

Geen enkele daarvan was een crash. Ze werden allemaal geloofd. De kosten zijn
asymmetrisch: "ik weet het niet" kost een moment teleurstelling, "het is in
orde" kost het vertrouwen in álles wat het systeem verder zegt.

Vier regels, en een vijfde voor de console: die maakt presentatie, nooit
waarheid. Toen ze toestand zelf afleidde had ze het zes keer mis.

**ADR-010 — De desktopapplicatie is de leveringseenheid.** ADR-007 klapte zes
services in tot één proces maar zei niet wat een gebruiker eigenlijk *krijgt*.
Het antwoord van de scaffold was docker-compose: een operator met een terminal.
De eigenaar is een gezin. Elke aanname uit dat operatormodel is er unit voor
unit uit gehaald, en telkens gemeld door de eigenaar in zijn eigen woorden. De
vier verplichtingen die eruit volgen staan er nu, inclusief de meest kostbare:
eigendom van de eigenaar staat buiten de installatiemap, want die wordt bij elke
update vervangen.

Het architectuuroverzicht is bijgewerkt: drie spraakpaden in plaats van twee
providers, zes connectoren in plaats van één, vier principes erbij, en een
leeslijst die niet meer stopt bij ADR-006.

### U312 — de grondwet naar 1.3.0

De grondwet staat amendementen expliciet toe, mits er een onderbouwing is en de
betrokken ADR's zijn bijgewerkt. Beide zijn er nu, dus:

**Principe I zegt hoe het wordt afgedwongen.** "Specs are living artifacts" was
waar en volstrekt machteloos: het principe stond 292 units buiten werking en
niets kon dat merken. Er staat nu bij dat traceerbaarheid wordt *gecontroleerd*,
niet vertrouwd, met de precedent erbij — want een principe zonder precedent
leest als een goede voornemen.

**Principe XI — Never report what has not been verified.** De onderbouwing is
ADR-009 uit U311. Tien incidenten, één vorm, geen enkele een crash, allemaal
geloofd.

**En het werkritme staat er eindelijk in.** De workflow beschreef alleen
geplande features met een branch per spec. De autobuild-stroom werkt anders: één
gemeld probleem, van begin tot eind opgelost, in één commit — en die commit is
pas af met de code én de spec én het ledger én de tekening als de vorm wijzigde
én een ADR als er een beslissing is genomen.

`AGENTS.md` is meegetrokken, zodat de Copilot-kant en `CLAUDE.md` hetzelfde
zeggen.

### U313 — de statussen kloppen nu ook

Vier specs stonden nog op `in-progress`. Drie daarvan draaiden al maanden
(gedragsengine, conversation-runtime, de OpenClaw-gateway) en staan nu op
`implemented`, met een notitie waar hun echte beschrijving intussen staat.

De vierde is de interessante: **014-zero-config-oauth staat nu op `blocked`,
niet op `in-progress`.** Dat is het verschil tussen "we zijn ermee bezig" en
"dit ligt stil en niemand wacht op code". De hele codekant is af — device-code
flows voor Microsoft, Google en GitHub, `defaults.py` als de plek waar de
meegeleverde client-ids horen te staan, de juiste voorrangsvolgorde. Wat
ontbreekt is geen code: drie OAuth-apps registreren onder een projectaccount,
met jouw accounts en jouw beslissing.

Er staat nu bij hoe je het deblokkeert, in één zin: registreer die drie apps
één keer, plak de ids in `defaults.py`, en Connect wordt één klik voor élke
installatie.

Dat is principe XI toegepast op onze eigen administratie: `in-progress` was
precies zo'n plausibele standaardwaarde als "batterij 100%".

**Eindstand: 22 specs, 335 units, schuld 0.**

### U314 — de blokkade verkleind tot twee minuten (niet opgeheven)

Gevraagd: "deblokkeer". Eerlijk antwoord vooraf: het échte deblokkeren — drie
OAuth-apps registreren onder een projectaccount — vraagt jouw accounts en jouw
beslissing. Dat is niets wat ik namens jou hoor te doen. Wat een unit wél kan,
is de stap die overblijft klein maken.

**Wat er nu ligt.** `connector_state` draagt per connector genummerde stappen
en een link die de **exacte** pagina opent, geen portaalvoordeur. Het paneel
toont ze achter "How do I get this?". De stappen benoemen de twee keuzes die
makkelijk fout gaan en stil zijn als ze fout gaan: het accounttype bij
Microsoft, dat standaard op single-tenant staat en daarmee élk thuisaccount
buitensluit, en Googles clienttype "TVs and Limited Input devices", het enige
dat met een device-code overweg kan.

Ook de mock-toestand krijgt die uitleg. "Showing example data" is precies het
moment waarop "hoe koppel ik dan de echte?" de volgende vraag is.

**`defaults.py` is nu een klaargelegde plek.** De registratiehandleiding staat
in de docstring van het bestand zelf, met de stap die iedereen vergeet
(*Allow public client flows: Yes*). Zes tests bewaken de faalvorm ertussenin:
een client-id zonder tenant, of een Google-id zonder secret, leest niet als
"nog niet ingesteld" maar bereikt de provider en komt terug als een
onbegrijpelijke fout — bij iemand die in zijn woonkamer staat. Volledig of leeg,
nooit half. Dat is principe XI.

Onderweg bleek `identity-service` **helemaal geen tests in CI** te hebben; die
map bevatte alleen een `__init__.py`. Nu wel.

Spec 014 blijft op `blocked`, met daarin wat er wél af is, wat er niet af is,
waarom geen unit dat kan, en de deblokkeerinstructie in vier regels.

### U315 — de ADR's nagelopen, en 25 links die nergens heen gingen

Bij het controleren van de ADR's bleek er iets pijnlijkers aan de hand dan
verouderde tekst.

**Vijf van de vijf paden in het "Key Interfaces"-blok van `AGENTS.md` wezen naar
bestanden die nooit hebben bestaan.** Inclusief `RobotAdapter` — het contract dat
de grondwet als niet-onderhandelbaar bestempelt. Dat blok vertelt agenten waar
de contracten staan, en het stond sinds april fout. Ik heb het zelf
overgeschreven in spec 016 zonder te kijken.

De echte plek is `packages/shared-schemas/.../robot/adapter.py`, niet
`services/robot-runtime/.../adapters/base.py`. Dat de ABC's níét naast hun
implementaties staan is precies wat de inklap van ADR-007 heeft overleefd — en
dat is de toets of een grens echt was.

Daarnaast: **24 links in de specs losten op naar niets.** Ze waren geschreven
vanaf de repo-root, terwijl Markdown ze relatief aan het bestand oplost. Sinds
april kapot. Niemand had geklikt.

`scripts/check_doc_links.py` controleert nu elke relatieve link in de
documentatie, met eigen tests, in CI. Verder: ADR-001 en ADR-003 aangevuld —
onder meer met het gevolg dat nergens stond, namelijk dat er geen `vue-tsc` in
de build zit en typefouten dus pas bij de eigenaar opduiken — en
`docs/adr/README.md` als index met een leesvolgorde voor wie hier binnenkomt.

### U316 — één werkafspraak, drie bestanden, en Copilot las een andere repo

Gevraagd: zorg dat zowel GitHub Copilot als Claude deze documentatie en specs
voortaan altijd bijwerken. Bij het uitzoeken bleek de Copilot-kant er nóg
slechter aan toe dan de Claude-kant.

**`.github/copilot-instructions.md` — het bestand dat Copilot automatisch laadt
— beschreef een andere repository.** Een generieke "Cognitive Hub" met `.apm/`,
`knowledge/`, `providers/` en `specs/`: vier mappenbomen die hier niet bestaan.
Het woord AURA kwam er nul keer in voor. En vier van de vijf bestanden in
`.github/instructions/` hadden `applyTo`-globs die op diezelfde afwezige mappen
wezen, dus ze konden nooit afgaan.

Dat is precies de tegenhanger van het ontbrekende `CLAUDE.md`: Claude las niets,
Copilot las iets verkeerds.

**De oplossing is niet drie bestanden bijhouden.** Dat is dezelfde weddenschap
die al twee keer verloren is. `docs/agent-working-agreement.md` is nu de bron;
`scripts/sync_agent_docs.py` injecteert die tekst in alle drie de bestanden
tussen markeringen, en CI faalt als ze uit elkaar lopen.

Verder:

* **`.github/instructions/source-change.instructions.md`** gaat af zodra je
  `apps/`, `services/` of `packages/` aanraakt, en zegt dan precies wat een unit
  verschuldigd is. Een tweede voor `.specify/**` legt uit dat je aanvult in
  plaats van herschrijft, en dat een status waar moet zijn.
* Een **PR-template** met dezelfde checklist, waarin met een ster staat welke
  punten CI afdwingt.
* Een test die eist dat elke `applyTo`-glob naar iets bestaands wijst, en dat
  elk pad in Copilots projectkaart echt bestaat. Die test controleert de kaart,
  niet een zinsnede — juist omdat het bestand nu bewust uitlegt wat er vroeger
  fout was.

Zeven tests erbij. Grondwet, ADR's, specs, ledger en drie agentbestanden zeggen
nu hetzelfde, en drie CI-checks houden dat zo.

### U317 — de releases publiceren al de hele middag niet

Opgemerkt tijdens het controleren van CI na U315: de Release-workflow faalt.
Niet de build — die is groen — maar het publiceren zelf, met
`403 Resource not accessible by integration`.

De laatste gepubliceerde release is **v2.0.126 van 08:45**. Alles daarna —
v2.0.127 tot en met v2.0.129, dus U314, U315 en U316 — is gebouwd, getest,
geïnstalleerd in artefacten, en nooit uitgebracht.

Precies de faalvorm waar dit onderdeel niet tegen kan: **hij is onzichtbaar.**
De build staat groen, de app biedt gewoon nooit een update aan, en de eigenaar
vraagt dagen later waarom er niets binnenkomt. Dat is eerder gebeurd (U236,
U283) en het is grondwetsprincipe XI in zijn duurste vorm.

De oorzaak zit niet in dit bestand. `permissions: contents: write` stond er al
op workflowniveau; ik heb het nu ook op het `release`-karwei zelf gezet, want
dat is de meest specifieke scope die GitHub kent. Maar de repo-instelling
overrulet beide:

```
default_workflow_permissions: "read"
```

Dat is één klik in **Settings → Actions → General → Workflow permissions →
Read and write permissions**, en het is jouw repository, dus die klik is aan
jou. Ik verander geen instellingen van je account zonder dat te vragen.

Wat ik wél kon doen: de mislukking laten praten. Faalt het publiceren, dan
schrijft de run nu in gewone taal welke instelling het is, hoe je hem
controleert (`gh api repos/<owner>/<repo>/actions/permissions/workflow`), en dat
de installers nog gewoon als artefact aan die run hangen — er is niets kwijt,
het is alleen niet uitgebracht.

Onderweg ook vastgelegd waarom sommige versienummers ontbreken: GitHub bewaart
per concurrency-groep maar één wachtende run, dus een snelle reeks pushes wordt
samengevoegd. De nieuwste run publiceert alles wat zich heeft opgestapeld; de
nummering heeft gaten, de inhoud niet.

### U318 — het werkte, en mijn verklaring klopte niet

U317 publiceerde. **v2.0.127 staat er**, om 17:29, en de repo-instelling staat
nog steeds op `default_workflow_permissions: "read"`.

Dat betekent dat wat ik in U317 schreef fout was. Ik zei dat de repo-instelling
beide `permissions`-blokken overrulet en dat één klik in Settings van jou nodig
was. Die klik is niet gebeurd en het werkt. Wat het oploste was het
**job-niveau**-blok dat ik er tegelijk bij zette.

Wat er nu feitelijk gemeten is, op deze repository, met de instelling
onveranderd op `read`:

| | |
|---|---|
| alleen `permissions: contents: write` op workflowniveau | 403 bij publiceren |
| datzelfde, plus een blok op het `release`-karwei | gepubliceerd |

Drie releases zijn aan de eerste toestand verloren gegaan (v2.0.127–129 in
nummering; gebouwd, getest, nooit uitgebracht).

Ik heb een oorzaak aangewezen voordat het bewijs binnen was, en die als
instructie aan jou doorgegeven. Dat is precies principe XI, maar dan toegepast
op een verklaring in plaats van op een statusregel: niet melden wat niet
geverifieerd is. De opmerking in `release.yml`, de diagnosestap en de
acceptatievoorwaarde in spec 020 zeggen nu wat er gemeten is, en niet wat ik
vermoedde.

De diagnosestap is blijven staan maar noemt nu twee dingen in volgorde: eerst
"staat het blok nog op het karwei?", dan pas de repo-instelling — met erbij dat
`read` op zichzelf geen blokkade is, want daar publiceert het nu vanaf.

### U319 — kiezen in plaats van doorklikken tot het klopt

Gemeld als "'who is this' -> tapping will cycle, but via arrow we should be
able to choose directly", en hetzelfde voor de robot op het Talk-scherm.

Het identiteitschipje tekende een pijltje omlaag en gedroeg zich als een
stapknop. Dat is het slechtste van twee werelden: de vorm belooft een lijst en
de klik geeft je de volgende. Bij een gezin van vijf is de laatste persoon vier
keer drukken, zonder ooit te zien waaruit je kiest.

De robot op het Talk-scherm was erger: dat is het meest voor de hand liggende
ding op het scherm om aan te raken, en er gebeurde **niets**. De karakterkeuze
lag twee schermen verderop.

Nu:

* **Het chipje is twee knoppen.** De body stapt nog steeds door — dat is de
  snelle weg als jullie met z'n tweeën zijn — en het pijltje opent de lijst met
  iedereen plus Guest, met een vinkje bij wie er nu praat.
* **De robot opent zijn eigen karakterkiezer**, alle tien met hun tekening en
  eigenschappen, waar je toch al kijkt. Het Robot-paneel blijft bestaan voor de
  volledige kaarten, de stemfragmenten en "Try a move".

Eén gedeeld `PickerMenu`-component in plaats van twee dropdowns, want het is
twee keer dezelfde taak — en twee schermen die uit elkaar groeien is in deze
console de meest terugkerende fout.

Twee dingen kwamen boven bij het verifiëren met een echte stack:

1. De `watch` op `open` was lui, dus een menu dat al open gemonteerd wordt kreeg
   nooit zijn Escape- en klik-buiten-luisteraars. In de app valt dat niet op;
   het stond klaar voor de eerste die het anders aanriep. Nu `immediate`, met
   opruimen bij unmount.
2. **"Nobody is in the brain yet." stond onder een lijst mét een persoon erin.**
   De console die iets beweert wat ze zelf kan zien dat het onwaar is —
   principe XI in het klein. Nu alleen bij een echt lege lijst.

Vijftien tests, geverifieerd tegen een draaiende demostack.

### U320 — het Present-paneel las als een lijst van zes losse dingen

Gevraagd: "improve ui/ux in present mode -> presentations", met de
instellingenkolom als voorbeeld.

Die kolom was één platte lijst. Twee instellingen, twee alleen-lezen waarden en
een overlayblok met zes bedieningen, allemaal met exact hetzelfde gewicht — dus
het ding dat de **zaal** ziet las als kleine lettertjes onder een dropdown. Nu
drie groepen: hoe hij klinkt, wat hij volgt, wat er op de projector staat.

Verder:

* **Wat Present-modus dichtzet** is een rij chips (mail · dev tools · screen
  control) in plaats van een zin die je moet ontleden.
* **Zaal of ikzelf** is een segmented control geworden. Een `<select>` verbergt
  de andere optie achter een klik, en de verkeerde keuze op een beamer betekent
  je eigen cue-notities geprojecteerd op het publiek. Dat mag geen keuze zijn
  die je pas ziet als je hem opent.
* **De knop zei "Run presentation" en opende de bouwer** wanneer er niets
  geladen was. Een label dat een andere handeling noemt dan het uitvoert, is
  principe XI toegepast op een knop. Hij zegt nu "Write a scenario".
* **Een lege staat waar je kijkt.** De twee deuren stonden rechtsboven; de
  pagina eronder was leeg met "No scenario loaded" bovenaan én "No scenario
  yet" eronder. Nu één uitnodiging, in het midden, met beide knoppen.
* **De vier stappen zijn hulp die je kunt wegklikken**, onthouden per machine.
  Ze hadden geen kop, dus ze lazen als de inhoud van de pagina in plaats van
  als uitleg — en leerden dezelfde presentator vóór elke talk hetzelfde.
* **Het overlayblok doet niet meer alsof het iets weet.** Dit venster kan het
  andere niet zien, dus het beweert niet of de overlay opstaat; "Take it down"
  staat er altijd, en er staat bij waarom.

Zes tests erbij. Eén bestaande test toetste het wóórd "Hide" in plaats van dat
er een uitweg is — die toetst nu de uitweg, en overleeft de volgende hernoeming.
Geverifieerd tegen een draaiende demostack.

### U321 — "gebruik gpt-live1 voor natuurlijke stem" — gemeten, en niet omgezet

Gevraagd als "voor voice gpt-live1 is now available, use this one for natural
voice", en even later "kunnen we gpt-live-transcribe ook gebruiken? andere
doeleinden misschien?".

De voor de hand liggende uitvoering was één regel: `REALTIME_MODEL` op het
nieuwe model zetten, zoals `gpt-realtime-2` er nu op staat. Eerst gemeten, op
jouw eigen sleutel, met `gpt-realtime-2` als controle door hetzelfde script:

* de naam is `gpt-live-1`, met streepje — `gpt-live1` bestaat niet;
* de Realtime API **weigert** hem: "not supported in realtime mode", op alle
  drie de sessievormen die AURA verstuurt. De controle slaagde op alle drie;
* chat-completions weigert hem ook, Responses geeft een 500;
* hij draait alleen op een aparte **Live API** (`v1/live/sessions`), met een
  ander protocol — en de geïnstalleerde SDK kent die nog niet.

Had ik de pin omgezet, dan viel elke realtime-beurt via de stroomonderbreker
terug op de pipeline: je stem wordt stilletjes minder natuurlijk en niets op het
scherm zegt waarom.

**Wat er wél al misging.** Het model stond al in de modellijst van je account,
en de classifier — een substring-test op `realtime` of `-audio` — deelde het in
als chatmodel. Je Settings bóden `gpt-live-1` aan als Conversation-model: exact
U202, elke beurt een 404 en een echo. De U202-bewaker ving het ook niet, want
die hield een eigen, zwakkere kopie van de classifier bij. Nu gebruikt de
bewaker dezelfde classifier als het aanbod, en `gpt-live-*` en
`*-realtime-translate` (verbindt, antwoordt nooit) worden voor geen enkele rol
meer aangeboden of aanvaard — met de reden erbij.

**`gpt-live-transcribe`.** Eerst mat ik hem als trager (2,6 s tegen 0,9 s). Dat
was een meetfout: ik gooide de hele clip in één keer in de buffer, en mat
daarmee het enige waar een streaming-model niet voor gemaakt is. In echt
tempo aangeleverd is de eindtijd **gelijk** (±1,1 s na het einde van de zin),
en met `delay: minimal` komt het eerste woord na **0,5 s** — terwijl je nog
praat — tegen 7,4 s vandaag. Alleen het live-model aanvaardt `keywords`.

Maar: op het pipeline-endpoint geeft hij een 404. En pipeline én sessie lazen
dezelfde `STT_MODEL` — wie na dit nieuws `STT_MODEL=gpt-live-transcribe` had
ingevuld, maakte Richie doof op de pipeline, want `transcribe` slikt fouten. De
pipeline negeert nu een realtime-only transcriber, en zegt dat één keer; de
sessie kreeg een eigen `REALTIME_STT_MODEL`. Niet als standaard: de sessie
publiceert vandaag alleen de volledige transcriptie, dus die 0,5 s zou worden
weggegooid.

**De beslissing staat in ADR-011.** GPT-Live is geen modelwissel maar een vierde
spraakpad, en een interessant: delegatie van tools gaat naar ónze server, dus
natuurlijke stem mét tools terwijl de approval gate de enige weg naar actie
blijft. Op jouw vraag ("moet beschikbaar zijn, bekijk hoe we kunnen gaan
gebruiken") wordt dat pad aangesloten — als eigen engine, niet als
modelnaam. De vijf dingen die dit project al kent — full-duplex op een robot
zonder echo-onderdrukking (U156), taal alleen via instructies (U287, U289),
geen einde-van-antwoord-event, geen SDK-ondersteuning in onze versie,
facturatie per minuut — zijn nu de acceptatiecriteria van die integratie in
plaats van redenen om te wachten.

Twaalf tests, eerst rood gezien tegen de oude code.

### U322 — de OpenAI-SDK naar 3.13, een majorsprong, eerst bewezen

GPT-Live bestaat alleen op de Live API, en de SDK waarop AURA draaide — 2.33 —
had daar geen client voor: `AsyncOpenAI().live` bestond niet. De eerste versie
die het wél heeft is 3.13. Dat is een majorsprong, dus eerst bewezen vóór hij in
de lock ging, in een overlay zonder de lockfile aan te raken:

* alle zeven pakketten slagen erop (aura-brain, orchestrator,
  conversation-runtime, connector-, identity- en memory-service, robot-runtime);
* AURA's drie realtime-sessievormen werken er echt op, tegen `gpt-realtime-2`;
* een echte chat-, TTS- en transcriptie-aanroep ook.

Twee dingen naast de versie:

* **`aura-brain` declareert `openai` nu zelf.** Hij importeert het op vijf
  plekken maar kreeg het alleen via de orchestrator binnen — precies de vorm
  van de `uv sync`-snoeival die al vier units heeft gekost.
* **Een contracttest** pint wat AURA van de SDK gebruikt: de Live-client die
  U324 nodig heeft, én alles wat de andere paden en de orchestrator al
  aanroepen, zodat een volgende majorsprong niet stil een resource weghaalt.
  Rood gezien op 2.33 (3 van de 4), groen op 3.13.

### U323 — de privacy-hook drukte "FAILED" af en committe toch

Bij het committen van U322 meldde de pre-commit-hook een bevinding in de nieuwe
contracttest — een nep-`api_key` van achttien tekens leek voor de scanner een
sleutel met een waarde — en daarna stond de commit er gewoon, en was hij al
gepusht. CI draait dezelfde scanner over de hele boom en zou master rood maken.

De bevinding zelf was vals alarm. Wat níet klopte, was dat de hook hem liet
passeren. Een shellscript eindigt met de status van zijn **laatste** commando.
Tot U299 was dat de scan. U299 zette er de spec-waarschuwing achter (een `if`
die 0 teruggeeft als er niets te waarschuwen valt), en vanaf dan eindigde de
hook altijd met 0. Van U299 tot hier drukte de lokale privacygate dus netjes
"PRIVACY SCAN FAILED" af boven een commit die toch doorging. Alleen de CI-scan
over de hele boom blokkeerde nog; die is op elke push groen gebleven, dus er is
in die periode niets persoonlijks binnengeglipt.

Waarom niemand het zag: de tests van de scanner bleven groen, want de scanner
was in orde. Niets testte de **hook**.

* `.githooks/pre-commit`: `privacy_scan.py --staged || exit 1`, met uitleg
  waarom die twee woorden er staan.
* `scripts/test_privacy_scan.py`: een test die in een tijdelijke repo commit
  via een kopie van de echte hook, en daarna aan git vraagt of er een commit
  bestaat. Rood gezien tegen de oude hook (returncode 0, HEAD bestond), groen
  met de fix — en een schone commit gaat nog steeds door.
* De contracttest schrijft `api_key="x"`, zoals zijn eigen regel 50 al deed.
* GPT-Live, eerder aangekondigd als U323, wordt daardoor U324.

### U324 — GPT-Live als vierde engine: natuurlijk praten, en toch dingen doen

De eigenaar: "go voor full implementatie". Tot nu toe moest je kiezen: de
pipeline kan tools gebruiken maar klinkt niet natuurlijk, de realtime-sessie
klinkt natuurlijk maar kan niets opzoeken. GPT-Live is het eerste ontwerp dat
allebei kan — en met *client delegation* komt het werk terug bij óns, zodat het
in AURA's eigen orchestrator loopt, achter AURA's eigen goedkeuringspoort.

**Wat er gebouwd is** (`live_session.py`, vierde keuze in Settings en per
personage, opt-in):

* **Hij hoort het commando waarmee hij gewekt werd.** Live heeft geen
  tekstinvoer, dus de audio van het wekvenster gaat eerst de sessie in; daarna
  luistert hij verder zonder wekwoord tot het stil wordt.
* **Stilte is geen spraak.** Het model stuurt ononderbroken audio, en 74–81 %
  daarvan is digitale stilte. Die afspelen — of meetellen als "hij praat" —
  zou de microfoon eeuwig dicht houden. Dus een luidheidspoort met 0,6 s
  naloop, zodat pauzes binnen een zin blijven. Omdat Live geen
  einde-van-antwoord-event heeft, is een langere pauze het einde van een
  uiting: dan wordt het antwoord gepubliceerd en krijgt de echo-bewaker het.
* **Hij hoort zichzelf niet.** De Pi heeft geen echo-onderdrukking, dus terwijl
  hij praat (plus de naklank) krijgt de sessie `session.input_audio.mute`, en
  daarna `unmute`. `LIVE_BARGE_IN=true` alleen met AEC.
* **Opzoekwerk gaat naar de orchestrator.** `session.delegation.created` bevat
  geen taaktekst, dus de sessie houdt zelf bij wat de persoon zei en geeft dát
  door, met `announce=False`: tools en goedkeuring zoals altijd, maar de
  Live-stem zegt het resultaat. Mislukt het, dan krijgt het model een feit via
  `thinking` — geen verzonnen resultaat, geen zin om voor te lezen (U292).
* **Geld.** Live rekent per open minuut. Een stille sessie sluit na 45 s (een
  opzoeking die loopt telt niet als stil), er is een plafond van 600 s, en
  sluiten stuurt `session.close` en wacht op `session.closed` — het rekenen
  stopt op het woord van de server. `/voice/realtime-cost` toont de open tijd
  apart, en zegt dat de eigen modelaanroepen van de orchestrator er niet in
  zitten.
* **Wie er in de kamer is**: verandert dat, dan wordt alleen de nieuwe
  kamernotitie toegevoegd — Live-instructies worden aangevuld, niet vervangen.
* **Faalt Live**, dan antwoordt de pipeline; na twee keer staat Live uit tot
  een herstart, en het log zegt dat.
* **Settings** zegt bij elke engine wat je opgeeft, en *Test Live access* opent
  een sessie even en sluit ze weer.

**Onderweg gevonden: U203 werkte nooit in de dispatch.** De resolver
`_engine()` gaf het personage voorrang op de globale instelling, en had daar
tests voor. Maar `_realtime_turn` keek alleen naar de globale
`VOICE_ENGINE`. Een presentatiepersonage op realtime werd dus door de pipeline
beantwoord zolang de globale instelling pipeline zei. Nu vraagt de dispatch de
resolver; de test daarvoor was rood op de oude code.

**Gemeten tegen de echte API** (echte `LiveSession`, echte SDK, een nep-robot
die kamerstilte streamt op 16 kHz in echte tijd): de Nederlandse zin werd juist
gehoord en gepubliceerd; de delegate kreeg exact die tekst; het resultaat ging
terug via `commentary`; hij zei agenda en weer correct in het Nederlands. 9,5 s
spraak in 10 segmenten naar de robot, 11 van 94 vensters stil (pauzes binnen
zinnen), 4× mute en 4× unmute, sessie gesloten na 8 s stilte, 36,7 s open,
$0,031. Stemmen: `marin`, `cedar`, `coral`, `verse`, `ash`, `sage` en `alloy`
aanvaard, `nova` geweigerd — dus alleen die zeven worden van een personage
doorgegeven, anders `marin`.

Tests eerst rood gezien: de Live-sessietests (module bestond niet), de
dispatch-, prefs- en personagetests (9 rood). Daarna aura-brain 595 groen, de
console 198 groen.

**Wat overblijft is van de eigenaar:** de test in een echte kamer, op de robot,
met de televisie aan. De fakes bewijzen de logica, de smoke run het protocol;
alleen de kamer bewijst de akoestiek. Tot dan blijft Live opt-in en blijft de
pipeline de standaard. Nog niet gedaan: de meter in Talk tonen voor Live
(het eindpunt heeft hem; de view heeft geen mounttest om hem aan te hangen).

### U325 — "hij blijft soms statisch staan, zeker wanneer iemand passeert"

Gevraagd: waarom staat hij stil, en zou hij iemand die passeert niet moeten
opmerken en volgen? Nagekeken in de code en tegen de draaiende robot (die op dat
moment `tracking: true, face_visible: false` meldde — volgen aan, niemand
gezien). Drie oorzaken, en ze versterken elkaar:

1. **De app weet nooit wáár je staat.** De herkenning draait elke twee seconden
   op een camerabeeld en berekent per gezicht het kader — maar gebruikte dat
   alleen om op grootte te sorteren, en gooide de positie dan weg.
   `PersonRecognized` draagt identiteit, geen coördinaten.
2. **Niets in de brain kon de kop richten.** De enige beschikbare primitief was
   `aim`, en die pauzeert follow-me met opzet (U161: de joystick mag niet tegen
   de tracker vechten). Kijken naar iemand zou dus het volgen uitschakelen.
   Gevolg: al het kijken lag bij de tracker van de daemon, en de brain — die
   als enige weet dát er iemand staat — deed niets met de kop.
3. **Kwijt is kwijt, tot de volgende zwaai.** Raakt de daemon een gezicht kwijt
   (na ~2 s uit beeld), dan blijft de kop staan tot de idle-zwaai. Die liep op
   een vaste klok van 25 s, en wordt overgeslagen tijdens praten en gebaren.
   Iemand die door de kamer loopt is dan al lang weg.

Wat er nu is:

* **`gaze`** — een *duwtje* in plaats van een overname: relatief ten opzichte
  van waar hij al kijkt, follow-me blijft aan, en hij weigert beleefd (mét
  reden) wanneer bewegen tegen iemand zou vechten: follow-me uit (dan is de
  kop van de operator, U162), de daemon heeft al een gezicht vast (die doet het
  sneller dan wij), of er loopt een beweging. De daemon componeert ons
  `goto_target` met zijn eigen gezichtsaim — precies wat de idle-zwaai al
  aantoonde. `body_yaw=None`, anders zet elk duwtje de torso stiekem terug naar
  het midden (U158).
* **De positie die we al hadden** — dezelfde detectiepas die de embedding maakt,
  geeft nu ook waar het gezicht in beeld staat (geen tweede pas: dat is een
  tweede seconde Pi). De lus duwt hem naar de dichtstbijzijnde persoon, met een
  dode zone, want ruis najagen leest als een tic in plaats van als aandacht.
* **Een zwaai die de kamer volgt** — niets zolang hij iemand ziet; binnen
  `IDLE_SCAN_LOST_S` (6 s) nadat hij iemand kwijtraakte; en terug naar de rustige
  `IDLE_SCAN_S` (25 s) als er al `IDLE_SCAN_RECENT_S` (90 s) niemand was.

Dit is bewust de **trage** tracker (één beeld per twee seconden). De daemon
blijft de snelle en wint zodra hij een gezicht vast heeft; de onze verdient zijn
plek precies wanneer die jou kwijt is — of dood is (U253).

Oudere Pi: `/robot/gaze` bestaat daar niet. De lus vraagt het één keer, hoort
404, zegt het in het log en vraagt het niet meer (constitutie X).

Tests eerst rood: 11 op de robotkant (gaze bestond niet), 3 op de brainkant.
Daarna robot-runtime 112 groen, aura-brain 603 groen, ruff schoon. **Nog niet
in een echte kamer getest** — dat vraagt de robot: de versterking (`GAZE_GAIN`)
en de aanname over het camerabeeld (`GAZE_FOV_YAW_RAD`) zijn beredeneerd, niet
gemeten, en de robotkant vereist een flash van de Pi.

### U326 — meeleven in het gesprek: als jij praat, en als hij praat

Gevraagd na het bewegingsrapport: hij moet meeleven terwijl er gepraat wordt —
in beide richtingen. Uit datzelfde rapport kwamen de twee gaten:

* **Terwijl jij praat** stond hij volkomen stil. De knik bij zijn naam (U275) en
  de denkhouding (U147) vallen allebei *rond* een beurt, nooit erin — en in een
  realtime- of GPT-Live-gesprek is er geen wekwoord en geen denkpauze, dus daar
  gebeurde helemaal niets.
* **Terwijl hij praat** stuurden de streamende paden geen enkele beweging aan.
  Het wiegen van de kop is de SDK die op audioniveaus reageert (U157); dat weet
  niets van wat hij zegt. En op het pad dat wél een gebaar maakt, werd dat
  gebaar *afgewacht* vóór de synthese begon — dus elk antwoord was: bewegen,
  stilte, dan pas stem.

`body_language.py` doet nu beide, voor elke engine:

* **`heard()`** — een klein "ga door" terwijl iemand tegen hem praat, met een
  pauze ertussen, want transcriptiedeeltjes komen meerdere keren per seconde
  binnen en een cue per deeltje is een tic. De realtime-sessie krijgt alleen
  begin en einde van een beurt, dus die blijft knikken zolang jij aan het woord
  bent en stopt als je stopt; GPT-Live krijgt een stroom deeltjes en gebruikt
  de pauzeteller.
* **`replying(tekst)`** — bewegen met wat hij zegt, via dezelfde
  trefwoordheuristiek als het getypte pad (groet → zwaai, vraag → kantelen,
  spijt → kantelen, enthousiasme → gebaar, anders knikken), ongeveer één gebaar
  per antwoord.
* **Alles blijft binnen de gebaren die het volgen intact laten**, anders kijkt
  hij van je wég om een gebaar over jou te maken. En niets wordt afgewacht op
  het spraakpad.
* **Het antwoordgebaar op het getypte pad wordt nu gestárt in plaats van
  afgewacht**, zodat het over de TTS-wachttijd heen valt in plaats van erbovenop.

**Eerlijk over wat niet kan:** het pipeline-pad neemt vaste vensters op en meet
pas achteraf of er spraak in zat. Er ís daar geen signaal midden in jouw zin,
dus daar blijft het bij de wekknik en de denkhouding. Dat staat nu ook zo in de
spec, zodat de afwezigheid een beslissing is en geen vergetelheid. (Een echte
backchannel daar vraagt streaming-VAD op het pipeline-pad — een eigen unit.)

Onderweg: mijn eerste patch landde op de verkeerde `listen()`-aanroep — die
regel komt twee keer voor — en brak de inspringing van de hoofdlus. Gezien
doordat zes testbestanden niet meer te importeren waren; teruggedraaid en op de
juiste plek beoordeeld (en daar dus bewust niet gezet).

Tests eerst rood: de helper (module bestond niet) en drie van de vier
bedradingstests tegen de oude sessiecode — de vierde slaagde vanzelf, want er
knikte sowieso niets. Daarna aura-brain 620 groen.

**Nog niet in een echte kamer getest**: of een knik tijdens jouw zin de
microfoon stoort, is de reden dat de bewegingen klein zijn (U147 koos de
luisterleun precies daarom), maar gemeten is het niet.

### U327 — "in quiet mode praat hij nog steeds"

Met een schermafbeelding erbij: twee opgewekte openers om 09:43, onder een
koptekst die *HUSHED* zei en "he answers when asked and never speaks first".

Niet geraden maar nagemeten, want beide bekende "hij begint zelf"-paden
(begroeting bij herkenning, proactieve lus) checken `quiet()` netjes:

* de draaiende brain zei `quiet = true`;
* het beleidsbestand onder `%APPDATA%` zei `quiet: true` — geschreven op
  **1 september**;
* maar er stond een twééde bestand, ín de installatiemap, aangemaakt
  **vandaag om 15:25** — het moment waarop de eigenaar Quiet opnieuw aanzette
  nadat hij hem hoorde praten;
* de app start de brain met de installatiemap als werkmap, en zet wel
  `KNOWLEDGE_DB_PATH`, `RECOGNITION_DB_PATH`, `DATABASE_URL`, `SKILLS_DIR` en
  `SCENARIOS_DIR`, maar niet `MODE_POLICY_PATH`.

Dus: de standaard `./data/mode-policy.json` landt binnen de installatie, en die
map wordt bij élke update integraal vervangen. Quiet stond sinds september aan,
een update gooide het bestand weg, en de brain las weer "mag praten". De console
loog niet — die corrigeert zich aan de brain — maar wie niet op de chip lette,
zag alleen een robot die begon te praten terwijl dat uit stond.

U177 heette dit op te lossen ("persist everything under userData, so an update
can never wipe it") en kwam vijf bestanden tekort: het modusbeleid met de
quiet-schakelaar, de MCP-servers van de eigenaar, de connectorvoorkeuren, de
latentiesporen en het gedownloade handmodel. Alle vijf staan nu onder
`userData`; de bestaande migratie kopieert wat nog in de installatiemap stond
mee bij de volgende start, dus er gaat niets verloren.

De test is met opzet niet "staat MODE_POLICY_PATH erin": hij scant de brain en
zijn services op élke omgevingsvariabele waarvan de standaard tegen de werkmap
aanleunt, en faalt zolang de desktop-app die niet vastpint. Rood gezien met
precies die vijf namen erin; daarna groen. Plus een tweede test die controleert
dat de scan zelf nog iets vindt — een regex die stilletjes niets meer matcht,
is erger dan geen test.

**Wat dit voor jou betekent na de volgende update**: Quiet blijft staan waar je
hem zet, ook over updates heen. Wat nog niet opgelost is: een oudere kopie van
die instelling in de installatiemap wordt genegeerd zodra de userData-versie
bestaat — voor deze installatie zeggen ze allebei "aan", dus dat valt samen.

### U328 — reageren met de antennes, niet alleen met de kop

Gevraagd: "het is niet alleen knikken of nodge of tracken, maar ook in
combinatie met de antennes kan hij reactie tonen."

Dat is niet alleen mooier, het is technisch het juiste kanaal voor een reactie
die middenin jouw zin valt. Antennes bewegen de kop niet, en dat betekent drie
dingen: geen oogcontact dat wegdraait, geen gevecht met de gezichtstracker, en
geen motorgeluid van het platform ónder de kop vlak naast de microfoon die op
dat moment jouw zin staat op te nemen — precies de reden waarom U147 de
luistercue klein hield en U157 tijdens het praten alleen antennes gebruikte.

Nieuw op de robot:

* **`acknowledge`** — het "mm-hm": kop dipt een beetje én antennes klappen naar
  voren, in **één** commando. Twee commando's zouden achter elkaar in de
  bewegingslus vallen en als twee gebeurtenissen aankomen. Bewust kleiner dan
  een echte `nod` (0,15 vs 0,35 rad): dit valt in iemands zin, en een volle
  knik daar leest als een onderbreking.
* **`perk`** — antennes naar voren en even zo houden: "ik luister".
* **`flick`** — één antenne tikt kort: "hm?".
* **`droop`** — allebei naar achteren/omlaag: medeleven, spijt.
* **`alert`** — allebei snel omhoog: verrassing, interesse.

Alle vijf staan in de lijst die het volgen intact laat.

In het gesprek gebruikt hij ze nu ook echt: de reactie terwijl jij praat rouleert
`perk` → `acknowledge` → `flick` → de leun van U147, dus antennes leiden en de
kop doet af en toe mee. En de toon van zijn eigen antwoord bereikt de antennes:
spijt laat ze zakken in plaats van de kop schuin te zetten, een groet zwaait,
en alles gewoons is de kleine kop-plus-antennes in plaats van een kale knik.

Onderweg één opruiming: de toon werd tot nu toe alleen binnen `gesture_for`
bepaald. Een tweede lezer zou zijn eigen kopie van de trefwoordenlijsten
krijgen en daarmee vroeg of laat iets anders vinden in dezelfde zin. Nu is er
`tone_for` (greeting | excited | sad | question | plain) en leest `gesture_for`
die — zelfde antwoorden als voorheen, vastgelegd in een test.

Tests eerst rood: 10 op de robot (de bewegingen bestonden niet; ook dat ze de
kop níet bewegen, dat ze het volgen niet pauzeren en dat de torso niet
stiekem wordt gecentreerd) en 3 in de brain. Daarna robot-runtime 125 groen,
aura-brain 625 groen.

**Nog niet in een echte kamer gezien.** De amplitudes zijn gekozen naar analogie
met de bestaande bewegingen, niet gemeten aan hoe ze er op tafel uitzien.

### U329 — "wanneer hij spreekt is zijn audio heel stil"

Gemeten in plaats van gedraaid aan een knop, en de meting wees drie dingen aan:

* de **hardwaremixer** van de Pi stond op 100% (0,00 dB) — daar zat het niet;
* de **digitale versterking** in de robotdienst stond op zijn standaard 0,8 —
  dat is 2 dB, geen fluisterstem;
* maar **alle** afspeelacties liepen via `POST /robot/speak/segment` (twaalf op
  rij, geen enkele via het hele-zin-pad), want de engine staat op `realtime` en
  die streamt altijd.

En daar zit het verschil: het hele-zin-pad tilt stille TTS eerst naar een piek
van 0,95 en past dán het volume toe (~0,76 uit de luidspreker). Het
segmentpad doet dat bewust niet — U153 koos dat omdat normaliseren *per segment*
het volume binnen één zin op en neer laat pompen — en vertrouwde op een
opmerking in de code dat het model toch al bijna vol bereik stuurt. Nagemeten op
een echte opname: **piek 0,35**. Keer 0,8 is 0,28. Dat is ~9 dB stiller, en met
`VOICE_ENGINE=realtime` geldt dat voor élk antwoord.

De fix houdt de reden van U153 overeind: **één versterking per uiting**, bepaald
op het eerste segment en daarna nooit meer omhoog — dus niets pompt. Een later,
luider segment trekt hem wel omláág, en dat is precies wat vervorming
voorkomt. Stilte wordt niet versterkt (dat zou de ruisvloer optillen naar een
microfoon zonder echo-onderdrukking), de versterking heeft een plafond, en het
appvolume blijft er gewoon overheen gaan. Uit te zetten met
`ROBOT_TTS_NORMALIZE=false`.

Tien tests eerst rood gezien, waaronder de twee die het echte pad doorlopen met
een nep-mediabackend: een segment van 0,35 moet de luidspreker bereiken op
0,95 × het appvolume, en het appvolume moet er nog steeds over heersen.
Robot-runtime 135 groen, ruff schoon.

**Nog te doen**: dit zit in de robot-runtime, dus het werkt pas na een flash van
de Pi. En het is in de kamer nog niet beluisterd — de meting zegt dat het gat
dicht is, jouw oren moeten zeggen of het nu góed staat.

### U330 — de schermafbeeldingen liepen achter (en waarom dat bleef gebeuren)

Gemeld als "ik merk daar nog oude layouts & visualisaties". Twee lagen gevonden:

* `docs/screenshots/*.webp` — de beelden die de README toont, voor het laatst
  vernieuwd op 4 september (U297). De Settings-opname miste daardoor twee
  units: de herschreven uitleg bij de engine én de hele rij **Calendar by
  link** (U298), die er in de oude foto simpelweg niet is.
* `design_handoff_aura_console_d2/screenshots/` — 17 beelden van 17 augustus.
  Dat is een ontwerpbriefing: referentiebeelden van de app zoals die er tóen
  uitzag, als invoer voor een herontwerp dat intussen gebouwd is. Die
  bijwerken zou het document zelf onwaar maken, dus die blijven — ze horen bij
  hun datum.

**Waarom ze stilstonden.** De release maakt dezelfde beelden, maar kan ze niet
terugzetten in de repo; de gecommitte bestanden veranderen dus alleen als
iemand met de hand een demo-stack optuigt: console bouwen tegen de juiste
poort, twee diensten starten met acht geïsoleerde paden, console serveren,
browser installeren, opnemen, omzetten. Zes stappen die niemand herhaalt.
Daarom nu één commando — `python scripts/refresh_screenshots.py` — dat dat
allemaal zelf doet, op vrije poorten, en achteraf opruimt.

De twee veiligheidsregels staan er als code in, niet als opmerking: elk
eigenaarspad wordt naar een wegwerpmap geleid, en de run **weigert te starten**
als er eentje toch binnen de repo uitkomt (`./data` is op een
ontwikkelaarsmachine een echte kennisopslag — een schermafbeelding daarvan is
een gepubliceerd gezin). Vijf tests leggen dat vast.

**Ook bijgewerkt, want tekeningen die niet meer kloppen zijn erger dan geen
tekening:**

* `media-paths.svg` wees met de pijl naar `POST /robot/speak`, terwijl vandaag
  élk antwoord via `/robot/speak/segment` gaat (U329 heeft dat gemeten). De
  segmenten stonden alleen in een voetnoot; nu andersom.
* `build-loop.svg` zei "U1 . . . U226, in order" — een getal in een tekening is
  een datumstempel die veroudert. Nu "U1 . . . today".

**Twee fouten van mezelf onderweg, allebei zichtbaar in de opnames:**

1. Ik bouwde de console eerst tegen `localhost:8020` — de **echte** brain van
   de eigenaar. Op tijd gezien, vóór er iets opgenomen of geserveerd was: er
   is niets vastgelegd. De demo hoort op vrije poorten, en dat zit nu in het
   script.
2. De eerste "robot offline"-foto toonde een robot die gewoon `connected` was.
   Oorzaak: op Windows doodt `terminate()` alleen de `uv`-starter, niet de
   server eronder — de "gestopte" nep-robot bleef antwoorden. Ik heb de brain
   even ten onrechte verdacht van een oneerlijke status; het lag aan mijn
   eigen opruimen. Nu een echte procesboom-stop, en de offline-foto krijgt een
   brain die naar een dode poort wijst (ondubbelzinnig, in plaats van een
   robot die net wegviel). Het script weigert die foto te maken zolang de
   console nog een verbonden robot tekent.

### U331 — "het is niet duidelijk wanneer hij overschakelt op GPT-Live"

Met de juiste waarneming erbij: *"lijkt dat hij bij begroeting standaard
modellen gebruikt"*. Dat klopt, en het is geen storing maar een grens die
nergens stond.

De engine-keuze stuurt **één** pad aan: een gesproken beurt die de robot zélf
hoort — na het wekwoord, of in het vervolgvenster meteen na zijn antwoord. De
spraaklus is de enige code die de instelling leest. Alles daarbuiten negeert
haar:

* getypte berichten gaan door de gewone denkketen;
* de **Talk-knop** in de app neemt op met de laptopmicrofoon en post naar
  `/voice/turn`, en dat eindpunt draait altijd de pipeline;
* de begroeting bij herkenning, proactieve zinnen en herinneringen hebben
  alleen tekst — Live is spraak-naar-spraak en heeft een audiostroom nodig.

En met *hands-free voice* uit wordt de instelling überhaupt nooit bereikt. Dat
was precies de toestand: Live gekozen, wekwoord uit, en dus een gewone
begroeting — wat redelijkerwijs leest als een kapotte instelling.

De rij zegt dat nu zelf: welk pad ze stuurt, en een waarschuwing zodra ze niets
kan doen. En zolang Live gekozen is, meldt de rij *Voice model* dat hij niet
gebruikt wordt — GPT-Live brengt zijn eigen model mee.

Vijf consoletests, twee eerst rood. Eén ervan slaagde aanvankelijk om de
verkeerde reden: hij zocht "hands-free" ergens op de pagina, en dat woord staat
ook in de stemsectie. Nu gepind op het element zelf. Console 203 groen.

### U332 — op een tweede laptop startte AURA niet op

Gemeld met het log erbij, en dat log wees precies aan waar:

```
future: asyncio.Future[bool] = field(default_factory=asyncio.get_event_loop().create_future)
RuntimeError: There is no current event loop in thread 'MainThread'.
```

Die regel staat in de **klasse-body** van een dataclass, dus hij draait bij het
importeren — in een draad zonder lus. Tot en met Python 3.13 maakte
`get_event_loop()` er dan stilletjes zelf een en waarschuwde alleen (die
DeprecationWarning stond al maanden onderaan élke testrun van dit project). Op
**3.14 is het een harde fout**. En `uv` mag elke interpreter kiezen die
`requires-python = ">=3.11"` toelaat, dus op die verse machine werd het 3.14 en
stierf de brain vóór zijn eerste regel werk — met een stacktrace over een
dataclass-veld, wat niets zegt over wat de eigenaar probeerde te doen.

Opgelost door de future te maken wanneer de goedkeuring wordt aangevraagd, in
de lus die hem ook zal afwachten. En de drie zusjes meteen mee: elke
`get_event_loop()` in eigen code is nu `get_running_loop()` — dat is de enige
die niet de verkeerde lus kán teruggeven (connector-service, identity-service,
robot-runtime).

Twee tests: een scan die élke `asyncio.get_event_loop()` in de broncode afkeurt
(rood gezien op vier bestanden), en een die de module in een verse interpreter
importeert. Daarnaast op de échte interpreter nagemeten: met de oude code geeft
Python 3.14.0 exact de fout uit het log; met de fix importeert hij schoon.

Suites: orchestrator 391, robot-runtime 135, connector-service 89,
identity-service 6, aura-brain 632.

**Nog een beslissing die van jou is.** De crash is weg, maar 3.14 wordt nergens
getest — CI draait 3.11. Zolang `requires-python` alles vanaf 3.11 toelaat,
installeert een verse machine op wat uv toevallig kiest. Twee opties: het
bereik dichtzetten (`<3.14`) zodat installaties op een geteste versie landen,
of 3.14 aan CI toevoegen en het echt ondersteunen. Niet stil beslist.

### U333 — Stop stopte niet, en quiet hield de televisie niet buiten

Twee klachten in één adem, allebei terug te zien op de schermafbeelding:
Present-modus, Quiet aan, kaartje "Speaking · live" — en een gesprek waarin hij
op filmzinnen antwoordt ("Maravó?", "there has been a new presence, Mr.
Swann").

**Quiet had geen effect, en kón dat niet.** Een Live- of realtime-sessie houdt
de microfoon open zónder wekwoord. Dat is precies wat die engines waardevol
maakt, maar het betekent ook dat wat het luidst is, de vragensteller wordt. Met
een film op tv beantwoordde hij de dialoog, regel na regel, onder een koptekst
die belooft: *he answers when asked and never speaks first*. Nu geldt: zolang
Quiet aan staat, gaat een beurt nooit naar een sessie met open microfoon — het
wekwoord bewaakt elke beurt. Antwoorden blijft onaangeroerd; dat is altijd de
betekenis van Quiet geweest.

**Stop stopte niet.** De paniekknop sneed het lopende geluid af en vroeg de
sessie te eindigen — maar daarna wachtte de sessie de *spreekstaart* uit (tot
`REALTIME_TAIL_MAX_S`, 20 seconden) én de afspeelwachtrij bleef de al
gebufferde fragmenten naar de robot posten. Hij praatte dus door na de knop.
Die staart staat er met reden (U157: de microfoon-afbouw mag het einde van een
antwoord niet afkappen), maar ná Stop is er geen antwoord meer te beschermen —
en dan is dat wachten exact het probleem dat de knop moet oplossen. Nu:
wachtrij leeg, afspeelklok op nul, geen staart. In **beide** sessie-engines,
anders betekent de knop niets in degene die je toevallig gebruikt.

Zes tests eerst rood, waaronder de tijdmeting (de sessie moet binnen enkele
seconden eindigen in plaats van de staart uit te zitten) en de wachtrij die
leeg moet zijn. Eén test van mezelf gaf eerst een niet-awaitbare lambda mee;
hersteld. Brain 632 groen.

Meegenomen: de lintfout die U332 achterliet (een aanhalingsteken in een
annotatie). Mijn `&&`-keten slikte de exitcode van ruff op via een pipe —
dezelfde val als bij het deployscript vanmorgen.

**Nog te doen, en dit is de belangrijkere:** ook zónder Quiet blijft een open
sessie met een televisie erbij een probleem. FR-007 zegt dat achtergrondmedia
geen beurt mogen opleveren; voor de pipeline doet het wekwoord dat werk, voor
een open sessie bestaat dat vangnet nog niet.

### U334 — op het podium alleen het scenario

Gemeld: *"in presentatie mode mag hij enkel iets zeggen op basis van scenario,
nu gaat hij praten los van het scenario (dit mag nooit gebeuren — eigen aan
present mode dat we deze guardrails opleggen)."*

Het bijzondere: de modus **zei dit al**. In het gedragsmodel staat bij
presentatie letterlijk `speaks_first: "never — cues only"`. Alleen dwong niets
het af. Alle andere spreekwegen bleven gewoon open vóór een publiek: een
antwoord op een getypt bericht, een begroeting zodra de camera iemand herkende,
een proactieve zin, en — het vervelendst, want daar hoeft niemand hem voor aan
te spreken — een open Live-sessie die antwoordt op wat ze hoort.

Het scenario praat langs een ándere deur: `presentation_api._speak` gaat
rechtstreeks naar de robot met zijn eigen synthese. Daardoor kon ik de
gespreksweg dichtzetten zonder de voorstelling te raken. Dat is ook precies wat
de laatste test bewaakt: met de poort dicht moet een beat nog steeds klinken —
anders heeft de beveiliging opgegeten wat ze moest beschermen.

Wat er nu gebeurt in presentatiemodus: antwoorden verschijnen nog gewoon in de
console (je ziet wat hij zou zeggen), maar er komt geen geluid uit de robot
behalve de beats, en er wordt geen sessie met open microfoon geopend.

Onderweg: ruff ving een echte fout die mijn zes tests misten. Mijn regel in de
moduswissel riep `mode_policy` aan zonder import — een `NameError` bij élke
moduswissel, en de `except ValueError` eromheen zou hem niet eens gevangen
hebben. Er is nu een test die de modus wisselt zoals de koptekst dat doet, via
de route.

Brain 637 groen, orchestrator 391 groen, ruff schoon.

### U335 — de modi beloofden vier dingen, en dwongen er twee af

Gevraagd na U334: *"kan je verifieren voor alle modi (family, work, present)
dat alles correct wordt afgedwongen"*. Nagegaan, en het antwoord was: de helft.

**Wat wél werd afgedwongen** (en al getest stond in
`services/orchestrator/tests/test_mode_policy.py`): de capaciteitengrens.
`allowed_tools()` bepaalt wat het model überhaupt aangeboden krijgt, een
geblokkeerde tool die tóch wordt aangeroepen krijgt `mode_mismatch` terug, en
elke tool van een groep op *asks* stopt bij de goedkeuringspoort. Presentatie
laat bovendien alle MCP-tools vallen.

**Wat níet werd afgedwongen:** de gedragsrij die de eigenaar in het
Modes-scherm ziet én kan bewerken:

| modus | speaks first | memory writing |
|---|---|---|
| home | yes | on |
| work | only for reminders | on |
| presentation | never — cues only | off |

Buiten `mode_policy` las niemand die waarden. `behaviour()`, `speaks_first()`
en `memory_writing` hadden precies één aanroeper: de route die ze *instelt*.
Gevolg: in werkmodus sprak de dagelijkse briefing gewoon, onder een rij die
"alleen herinneringen" zei, en tijdens een presentatie leerde hij passief bij
over wie er in de zaal stond.

Nu leest de afdwinging **de rij zelf** — dus de keuzelijsten in de
Modes-editor doen echt iets — op twee knooppunten: de proactieve stem (met een
`kind`, zodat "alleen herinneringen" een herinnering wél doorlaat) en het
passieve leren (`PersonMemory.record`). De begroeting bij herkenning stelt nu
dezelfde vraag, want een begroeting ís uit zichzelf spreken. Quiet blijft
boven alles staan: dat is de schakelaar van de eigenaar, niet van de modus.

`speaks_first()` is verwijderd: die had geen enkele aanroeper en zou met deze
wijziging twee betekenissen krijgen.

**Merkbare gedragswijziging, en het is de belofte:** standaard staat AURA in
werkmodus, dus de dagelijkse briefing spreekt niet meer uit zichzelf —
herinneringen wel. Wil je hem wél horen: zet `speaks first` voor work op *yes*
in Modes. Drie bestaande proactieve tests legden het oude gedrag vast; die
zeggen nu expliciet in welke modus ze zich afspelen.

Tien nieuwe tests eerst rood. Brain 648 groen, orchestrator 391 groen, ruff
schoon.

### U336 — hij verhuist van netwerk, en AURA zoekt hem zelf terug

Gevraagd bij het vooruitkijken naar een conferentie: *"kunnen we alles niet
comfortabeler maken vanuit aura?"*

Wat het ongemakkelijk maakte: de brain leest het robotadres **één keer**, bij
het opstarten, en kijkt daarna nooit meer. Ga je met laptop en robot naar een
ander netwerk — een telefoonhotspot, een kantoor — dan geeft DHCP hem een ander
adres terwijl de brain het oude blijft bellen. Alles meldt dan "offline":
correct, en nutteloos, tot iemand het Robot-paneel opent, *Scan my network*
indrukt en met de hand het nieuwe adres kiest. Die sweep bestaat sinds U200;
alleen riep niemand hem ooit uit zichzelf aan.

Nu wordt het adres bewaakt. Antwoordt het niet meer, dan zoekt hij in de
goedkoopste volgorde: het adres dat we hebben (één verzoek, en meestal het
antwoord), dan `reachy-mini.local`, en pas dan elke host op ons eigen /24 —
dezelfde grens die U200 trok, nooit breder dan het subnet van de eigenaar.

Alleen iets dat **als robot antwoordt** wordt overgenomen: `/health` met een
robotlichaam erin. Een open poort 8001 is geen bewijs; een printer die
verbindingen accepteert zou anders "de robot" worden en elke volgende aanroep
op een nieuwe manier laten mislukken. Overnemen gebeurt één keer per verhuizing
en langs exact dezelfde drie stappen als de handmatige knop, zodat er één weg
is waarop een adres verandert. Uit te zetten met `ROBOT_AUTOFIND=false`.

Tien tests eerst rood, waaronder: het bestaande adres kost één verzoek en geen
scan, iets anders op die poort wordt niet overgenomen, en een stukgelopen
netwerk doodt de bewaking niet.

**Wat dit uitdrukkelijk niet kan**, en geen enkele app kan: hem op een wifi
zetten waar hij nog niet op zit. Kan hij het netwerk niet bereiken, dan kan
niets hier hem bereiken. Dat blijft een eenmalige klus aan de robot zelf.

### U337 — de installer was nergens ondertekend

Gemeld: *"code signing moet toegevoegd te worden zodat ik ook kan installeren
op werk pc en niet langer exceptie krijg."* Nagekeken: er stond **geen enkele**
ondertekenconfiguratie in de bouw. Windows meldt dus bij elke installatie een
onbekende uitgever, en een beheerde werk-pc weigert het ronduit. De mac-bouw
staat expliciet op `identity: null`.

Wat er nu is: `apps/desktop/sign.cjs`, met twee routes en één regel die
belangrijker is dan beide. Azure Trusted Signing als de Azure-geheimen er zijn
(de sleutel blijft in Microsofts HSM — sinds juni 2023 mág een nieuwe
OV-sleutel sowieso niet meer als los bestand bestaan), een PFX als díe er is,
en anders een bewuste no-op die `UNSIGNED` logt. Die laatste is de belangrijke:
een fork, een pull request en een lokale `npm run dist` hebben geen geheimen en
moeten gewoon een werkende installer opleveren. Een ontbrekend geheim mag nooit
een release breken — maar het mag evenmin stilzwijgend gebeuren.

Daarom controleert de release achteraf de handtekening van het bestand en zet
het antwoord in de samenvatting van de run. "Onbekende uitgever" hoor je anders
pas op de machine van iemand anders, op het slechtste moment.

Een privésleutel die naar een runner geschreven wordt, verdwijnt in een
`finally` — buildmappen worden gecached en teruggezet, dus een achtergebleven
PFX ís een gelekte sleutel.

**Wat jij nog moet doen, en het kost geld:** een certificaat. Twee routes:

* **Azure Trusted Signing** — ongeveer $10 per maand, draait in CI, geen
  hardware nodig. Vereist wel een geverifieerde organisatie-identiteit.
* **OV- of EV-certificaat op een hardwaretoken** — duurder, en een token in een
  CI-runner krijgen is bewerkelijk. EV geeft wel meteen SmartScreen-reputatie;
  OV en Trusted Signing bouwen die op met het aantal downloads.

En eerlijk over de grens: ondertekenen haalt "onbekende uitgever" weg, maar een
beheerde werk-pc kan installaties nog steeds per beleid blokkeren
(AppLocker/Intune). Het verschil is dat IT een ondertekende build **kan**
toelaten op uitgever; een ongetekende niet.

Onderweg ontdekt: CI draaide de controles in `scripts/` als een **met de hand
bijgehouden lijst** van bestanden, en twee stonden er niet in — waaronder de
schermafbeeldingstest van U330. Dat is nu `pytest scripts/`. Een test die CI
niet draait, is een opmerking met een docstring.

### U338 — SignPath: gratis ondertekenen, omdat dit project open source is

Gevraagd: *"er is geen gratis alternatief?"* Voor een publiek vertrouwd
certificaat: niet te koop voor nul. Maar deze repo is **publiek en
Apache-2.0**, en dat opent de route van SignPath Foundation — die geeft
certificaten weg aan opensourceprojecten en ondertekent via hun dienst.

De koppeling zit nu in de release. SignPath ondertekent een *artefact*, dus de
volgorde is: ongetekende installer uploaden, laten ondertekenen, en het
ondertekende bestand landt terug bovenop het ongetekende. Daardoor publiceert
de bestaande uploadstap vanzelf de ondertekende versie, zonder iets van
ondertekenen te weten.

Twee eigenschappen zijn belangrijker dan de koppeling zelf:

* **Zonder token gebeurt er niets.** Een fork of een pull request heeft geen
  geheimen en moet gewoon een werkende installer opleveren.
* **Een verkeerde instelling kost nooit de release.** De stap staat op
  `continue-on-error`, en de controle uit U337 zegt daarna eerlijk of er een
  handtekening op zit.

Een test legt de vólgorde vast (uploaden → ondertekenen → controleren →
publiceren). Draai je twee van die stappen om, dan publiceer je een ongetekende
build onder een samenvatting die zegt dat hij ondertekend is — precies het
soort stille leugen dat dit project nergens wil.

De projectgegevens staan als repository-variabelen, niet als geheimen: een
organisatie-id en een paar slugs zijn configuratie, en zo is een verkeerde
waarde leesbaar in de repo in plaats van onzichtbaar in een geheim. Alleen het
API-token is een geheim.

**Eerlijk over wat ik niet kon verifiëren:** de exacte invoernamen van de
GitHub-actie van SignPath heb ik uit het hoofd opgeschreven, zonder toegang tot
hun documentatie. Ze zijn daarom bewust niet-fataal bedraad. Klopt er iets
niet, dan zegt de release het en is het één regel werk.


### U339 — de tweede laptop kon nergens zeggen dat hij bij deze robot hoort

Gemeld: *"bij gebruik aura op andere laptop klaagt hij over
`ROBOT_SHARED_SECRET`"* — elke oproep naar de robot kwam terug als **HTTP
401**.

Wat er werkelijk aan de hand was: de robot draagt sinds U220 een gedeeld
geheim. De laptop thuis heeft dat, de nieuwe niet. `ROBOT_SHARED_SECRET` werd
op **twee** plaatsen gelezen (`robot_client.py`, `robot-runtime/main.py`) en
door **niets** geschreven: geen endpoint, geen veld, geen wizardstap. De enige
manier om een tweede machine te koppelen was `%APPDATA%\aura-desktop\.env`
zoeken en het er met de hand in typen. Dat is exact het patroon dat U199 erger
noemde dan zwijgen: advies zonder plek om het uit te voeren.

Twee dingen zijn gerepareerd.

**De diagnose wees de verkeerde kant op.** `_diagnose()` kende sinds U198 drie
oorzaken — naam lost niet op, verbinding geweigerd, geen antwoord — en alles
daarbuiten werd *"is unreachable (HTTPStatusError)"*. Een robot die keurig
antwoordt en ons afwijst, is geen netwerkstoring; hij staat aan, hij is
bereikbaar, en er is precies één ding mis. Nu zegt hij: *hij antwoordde, en
wees ons af (HTTP 401) — hij heeft een koppelsleutel en deze machine niet, of
een andere; vul de zijne in onder Verbinding hieronder.* Een 403 of een 500
krijgt bewust **niet** dat verhaal: die worden niet opgelost door een sleutel
te typen, en het zou de eigenaar naar de verkeerde knop sturen.

**En daar staat nu het veld.** In de Connection-kaart, op hetzelfde scherm als
de zin die het probleem noemt. Het volgt de regel die de API-sleutels al
volgen: opslaan, nooit loggen, nooit teruggeven. De console mag één ding weten
— *is er een sleutel gezet* — en dat is genoeg om "gekoppeld" te zeggen.
Wissen kan ook, want U220 maakte het geheim opt-in: een robot zónder sleutel
moet bereikbaar blijven, dus een machine moet de waarde die hij draagt weer
kwijt kunnen.

Het werkt zonder herstart: `robot_auth_headers()` leest de omgeving bij elke
oproep, dus de eerstvolgende call draagt de sleutel al.

Tests eerst rood gezien: vier op de brain-kant (zetten en bewaren, nooit
terugkaatsen, `robot_secret_set` in de status, wissen), twee op de diagnose
(401 wél een koppelprobleem, 403/500 níet) en vijf mount-tests op de console —
deze app heeft geen `vue-tsc`, dus een mount-test is het enige dat tussen een
typfout en een grijs paneel staat.

### U339b — en de sleutel stond nergens beschreven

Vraag erachteraan: *"ik start app op vanuit repo in vscode — wat moet er nu
juist gebeuren?"* Een dev-run leest `infra/dev/.env`, niet de `.env` onder
`%APPDATA%`. En in `infra/dev/.env.example` — het bestand dat je kopieert als
je op een nieuwe machine begint — stond `ROBOT_SHARED_SECRET` niet. Niet als
waarde, niet als commentaar. Wie vanaf de bron start, kon dus alleen weten dat
hij bestaat door de 401 te krijgen en de broncode te lezen.

Staat er nu bij, uitgecommentarieerd naast `ROBOT_RUNTIME_URL`, met waar het
ding vandaan komt (de systemd drop-in op de Pi) en met de vermelding dat het in
de app ook via Robot → Connection kan (U339).

### U340 — de sleutels lagen in een bestand dat meer mensen mochten lezen

Gevraagd: *"moeten we deze file niet beveiligen ook?"* — over
`%APPDATA%\aura-desktop\.env`.

Ja. En het vervelende is dat het argument al in de repo stond. U225 verhuisde
de kennis-wachtwoordzin naar de credential store van het besturingssysteem, met
in zijn eigen docstring exact de reden: dat bestand ligt naast de ciphertext met
dezelfde rechten, dus "versleuteld op schijf" beschermde niets waar het in de
praktijk tegenop moest. Alleen: er verhuisde **één** geheim. De OpenAI-,
OpenRouter- en Gemini-sleutel, de agenda-deellink en sinds U339 ook de
koppelsleutel van de robot bleven in platte tekst staan — in precies het
bestand waar die alinea over ging.

Wat ik op de machine zelf gemeten heb (alleen rechten, niet de inhoud): het
bestand erft van `%APPDATA%\Roaming` een **leesrecht** voor de lokale groep
`CodexSandboxUsers`, met `CodexSandboxOffline` en `CodexSandboxOnline` als
leden. Twee sandbox-accounts op deze pc mochten dus de API-sleutel en de
robotsleutel lezen. En Roaming is nu net wat een beheerde werklaptop met
roaming profiles of OneDrive-mapback-up naar een bedrijfsshare synchroniseert —
precies het scenario van deze week.

Dezelfde behandeling als de wachtwoordzin, met dezelfde afwegingen:

* **De omgeving wint nog altijd.** docker-compose, CI en een shell die een
  sleutel exporteert houden de controle; een verouderde waarde in de
  credential store mag die nooit overschaduwen.
* **Geen keyring, dan het bestand.** Docker en CI hebben er geen. Die breken om
  een desktopprobleem op te lossen is een slechte ruil (U225 maakte dezelfde
  keuze).
* **Bestaande platte tekst verhuist vanzelf**, één keer, bij de volgende start.
  Een regel verdwijnt **pas** nadat de store de waarde heeft teruggegeven — een
  kluis die schrijfacties aanneemt maar niets teruggeeft zou anders de laatste
  kopie van je API-sleutel wissen.
* **Het bestand zelf gaat op slot.** Overerving eraf, rechten alleen voor de
  eigenaar, SYSTEM en Administrators (`icacls`), en op Linux/macOS `0600`. Dat
  gebeurt bij élke schrijfactie, want een herschrijving zet de overerving
  terug.
* **`GITHUB_TOKEN` blijft bewust in het bestand**: de Electron-updater leest
  hem daar rechtstreeks. Hem verplaatsen zou de updatecontrole breken terwijl
  het eruitziet als een verbetering.

**Wat dit níet doet, en wat ik er niet over ga beweren:** het houdt niets tegen
dat draait ónder jouw account. De credential store geeft een geheim aan elk
proces van die gebruiker. Wat het wegneemt is de *kopie* — een gesynchroniseerd
profiel, een tweede account, een back-up, een zip onder een bugrapport, een
screenshare.

Twee bestaande tests legden de oude waarheid vast ("de sleutel staat in de
.env") en zijn bijgewerkt naar wat ze nu bedoelen. 10 nieuwe tests, waaronder
een echte `icacls`-controle op Windows en een die de hele brain opstart om te
zien dat een sleutel die er al jaren in staat er daadwerkelijk uit verdwijnt.
674 brain-tests groen.

### U341 — slapen stond bij de instellingen, niet bij wat je hem vraagt

Gevraagd: *"for robot gestures ask -> add sleep and awake (so i can easily take
him along when going to travel)"*.

Slapen bestond al sinds U100, als schakelaar in de lichaamsstrip naast Mic,
Follow en Proactive. Dat is waar je kijkt als je hem aan het *instellen* bent.
Het is niet waar je kijkt met een tas in je hand. "Ask him to…" is de lijst van
dingen die je hem opdraagt, en gaan slapen is er daar één van.

Twee chips, in élke dichtheid — ook in `calm`, want inpakken doe je niet op een
bepaald zoomniveau. De chip die overeenkomt met de toestand waarin hij nu staat
is gemarkeerd (`aria-pressed`), zodat je niet hoeft te raden of hij al slaapt.

Bewust géén motion. Een beweging die "sleep" heet zou het hoofd laten zakken en
de motoren aan laten staan — precies verkeerd voor waar dit voor dient. De
chips gaan naar `/robot/sleep` en `/robot/wake`, dezelfde route als de
schakelaar, die nu met dezelfde functie werkt. Mislukt de oproep, dan zegt het
paneel dat (U238: een 404 die als "gelukt" leest is precies wat hier nooit mag).

4 mount-tests, 212 consoletests groen.

### U342 — hem meenemen, inclusief de gezichten

Gevraagd: *"can we add option to do export of brain, so i can import it on
other laptop? so he doesn't need to learn everything all over again"*.

Er *was* een exportknop, sinds U104. Er waren drie dingen mis mee, en pas
samen verklaren ze waarom het antwoord "die bestaat toch al" niet klopte:

1. **Er was geen import.** `GET /knowledge/export` bestond, en niets kon het
   ooit teruglezen. Een bestand dat je nergens kan laden is een souvenir.
2. **Er zaten geen gezichten in.** Mensen en feiten reisden mee, de embeddings
   niet. Op de nieuwe laptop wist hij dus alles over je en herkende hij je
   niet — precies de helft die de eigenaar bedoelt met "alles opnieuw leren".
3. **Het was platte tekst.** Elk feit over het gezin, in een bestand op een
   USB-stick. De kennisopslag is versleuteld op schijf juist omdat een kópie
   waardeloos hoort te zijn; een export die dat ongedaan maakt, maakt de
   belofte ongedaan.

Nu: één verzegeld bestand (`.aura`) met mensen, feiten, signalen, gezichten en
aangeleerde skills. De kop blijft leesbaar en zegt wát erin zit — aantallen,
nooit namen — want je moet twee exports uit elkaar kunnen houden zonder er een
te openen. De rest zit achter AES-256-GCM met een scrypt-sleutel uit een
wachtwoordzin die de eigenaar zelf kiest. De KDF-parameters reizen mee in het
bestand, zodat het verhogen van de werkfactor (wat U225 al eens deed) oude
exports niet onleesbaar maakt.

Importeren **voegt samen**, het vervangt niet:

* wat de andere machine al weet blijft staan;
* hetzelfde bestand twee keer importeren voegt niets dubbel toe — iemand gáát
  dat doen, en dan moet het saai zijn;
* een skill die daar al bestaat wordt nooit overschreven, want die kan de
  nieuwere zijn, en stilletjes andermans bewerking wissen is de vervelendste
  verrassing die een knop met "toevoegen" erop kan geven. Het paneel zegt
  hoeveel er bewaard zijn gebleven.

De import staat in **Settings**, niet bij een persoon. Dat is geen smaak: een
verse laptop kent niemand, dus er is geen persoonspaneel om het bestand in te
laten vallen. De oude platte export blijft trouwens bestaan waar hij stond —
dat is het antwoord op "wat weet je eigenlijk over mij", en dat hoort leesbaar
te zijn.

De embeddings konden niet als bytes mee: elk monster is met AES-GCM aan zijn
persoon gebonden via AAD. De matcher kreeg daarom `samples()`, zodat ze op één
plek geopend worden in plaats van de OMK op twee plekken te laten bestaan.

11 brain-tests, 4 mount-tests. 685 brain-tests, 216 consoletests, 142
shared-schemas-tests groen.

### U341b — de actieve chip was groen op groen

De markering uit U341 ("hier staat hij nu") greep naar `--accent-soft`, en die
token *is* de accentkleur. Resultaat: een massief groene pil met onleesbare
tekst. Gevonden door er in de browser naar te kijken, niet door een test — een
kleur die klopt is geen assertie die faalt, en dat blijft zo.

Nu dezelfde behandeling als elke andere "aan"-knop in de app (`App.vue`):
`--accent-wash` als achtergrond, `--accent` voor rand en tekst. Gemeten na de
fix: `rgb(228,239,231)` op `rgb(31,111,70)`.
### U343 — the launcher stood still for two months while the app moved on

Asked on a fresh clone on a second machine: *"how do I start the app locally,
is start-aura.bat up to date?"* (translated). No. One commit from 14 July, and
more than three hundred units have landed since. Every path still resolved, so
nothing looked wrong — the script started, and what it skipped only shows up
later.

Three gaps, all the same shape: the script still knew something from July that
had since been solved somewhere else.

**No `uv sync`.** The Python bootstrap in the Electron shell opens with
`if (!IS_PACKAGED) return` — it exists for an installed build, not for a
checkout. The script trusted `uv run` to do the rest. It does, but only for the
default dependencies: the extras are never asked for and are therefore
**pruned**. Exactly the trap that has sprung four times already (U179, U213,
U246, U266). Concretely: a brain without insightface (face recognition),
without pyautogui (every skill that drives a real window) and without pywin32
(slide detection) — three capabilities that are not broken but simply absent,
which under constitution XI is the worst kind of silence. The script now walks
the same ladder as the bootstrap, so a wheel that will not build on this
machine does not take the rest down with it.

**The console was never rebuilt.** The condition was `if not exist
dist\index.html`. After the first run that file exists, so every `git pull` left
an old console talking to a new brain — one half of a change, which is worse
than neither. The tree hash of `apps/operator-console` is now compared against
the hash recorded by the previous build; it changes precisely when something in
the console changed.

**Six baked-in `VITE_*` variables** pointing at `localhost:8020`. Redundant
since U234: the shell injects `window.__AURA_RUNTIME__` with the port it really
got, and runtime beats build time. And `localhost` is the very thing U229 warns
against, because on Windows it resolves to `::1` first. Gone. (They also sat
inside an `if` block without delayed expansion, so whether they did anything at
all was an open question.)

Two things you only learn in batch by hitting them. `echo %HASH%>file` writes to
**stream 9** when the hash ends in a 9; the redirect now comes first. And the
failure paths in the build blocks did `pause & exit` without `popd`, so a
failure left the shell in the wrong directory.

**No tests** — this is a `.bat` at the root and there is no harness for it.
Instead the control flow was walked through with a throwaway script first (the
ladder fails on rung 1 and succeeds on rung 2; the hash comparison picks the
right branch), and then the real script was run end to end on a fresh clone:
CPython 3.11.15, 115 packages including insightface, onnxruntime, pyautogui and
pywin32, console built, Electron started. Afterwards verified that the stamp
equals the tree hash, so a second start skips the build.

Reverted what did not belong: `npm install` under npm 11 removed 512 lines from
`package-lock.json` (the platform-specific optional esbuild entries for
netbsd/openbsd-arm64). The release build on macOS and Linux needs those; not in
this unit.

**Another decision that is yours, and it is the same one as U332.** The script
now pins `--python 3.11`, because that is the only version CI runs. That is a
plaster over the place where `requires-python = ">=3.11"` sits: a fresh machine
without this pin still lands on whatever uv happens to pick. The choice between
closing the range (`<3.14`) and adding 3.14 to CI is still open.

### U344 — it hung on the splash screen, and the log knew why

Reported with the log attached, which is the only reason this took half an hour
rather than an evening:

```
===== AURA brain start 2026-09-13T15:00:47.542Z =====
error: Failed to spawn: `aura-brain`
  Caused by: Access is denied. (os error 5)
===== brain exited (code 2) =====
```

`Access is denied` on a file that plainly exists and on which `icacls` reports a
tidy `BUILTIN\Users:(I)(RX)`. That is not a permissions problem but a policy.
Measured in the Defender log, event 1121:

```
ID: 01443614-CD74-433A-B99E-2ECDC07BFC25
Path: C:\devenv\aura\.venv\Scripts\aura-brain.exe
```

That is the ASR rule *"block executable files from running unless they meet a
prevalence, age, or trusted list criterion"*, set by IT, with Tamper Protection
on. Every console script `uv` writes into `.venv\Scripts` is by construction a
fresh, unsigned 47 kB launcher — precisely the profile that rule refuses. And it
is not one file: `uvicorn.exe` fails just as hard, while `python.exe` in the
same folder runs fine. Nothing is wrong with the app; on a corporate laptop the
shim is simply not allowed to exist as an entry point.

Fixed by starting the brain as a **module**: `uv run --package aura-brain python
-m aura_brain` instead of `... aura-brain`. There is now an
`aura_brain/__main__.py` calling the same `run()` the console script in
`pyproject.toml` declares — that declaration stays, and the test guards against
the two paths drifting apart.

**The second half is the worse one, and it is ours.** The brain was already dead
before the shell began waiting, and `waitForBrain()` kept knocking on `/health`
for **ninety seconds** at a process that no longer existed. Then a message
saying the brain "did not become healthy in time" — not a word about why, while
the reason sat in `brain.log` the whole time. From the owner's side that is a
minute and a half of frozen splash screen followed by a sentence that explains
nothing, exactly what constitution XI forbids. The exit handler now records an
exit code, the wait gives up the moment there is one, and the message quotes the
brain's own last lines of stderr.

Seen on the way: the error dialog for a dead brain hung off `mainWindow`, which
does not exist yet during the splash — so at the earliest failure nothing
appeared at all.

Test: `apps/desktop/test-brain-launch.cjs`, verified red against the old code
(`found: spawn('uv', ['run', '--package', 'aura-brain', 'aura-brain']`), then
green. Added to CI beside the four existing desktop tests. Eslint clean, all
five desktop suites green.

Then the real path on this machine: brain started, the buffalo_l model fetched
once (282 MB — that is why the first start takes a while, and it is work, not a
hang), `/health` 200, websocket open, console filling in.

### U345 — U339 taught one field the difference, and not the two beside it

Found while chasing a robot that said "offline" for the same owner — parallel to
U339, and in the places U339 did not touch.

The robot was up: `GET /health` returned 200, `connected: true`, adapter
`reachy`, commit `d2a4200`, in step with master. `GET /robot/status` returned
**401**, because the Pi carries a pairing key and this laptop does not. U339
fixed exactly that in `reason`. But two other things sit in the same response,
and they had not heard about it.

**The headline contradicted itself.** `_unavailable()` still set `error` to
`"robot unreachable: HTTPStatusError"` while `reason` underneath explained
politely that it had answered. One response, two stories — and the console leads
with the headline. "Unreachable" is a claim about the *network*, and it was
false: it sent me half an hour in the wrong direction, through ping, mDNS and
subnets, while the robot was simply saying no. `error` now names the status code
as soon as there was an answer, and keeps "unreachable" for the case where there
really was no contact.

**And the address field gave a false pass.** `POST /robot/address` probed only
`/health`, and that route is *not* gated. So it reported `reachable: true,
saved` for a robot that refuses every real call — save an address, be told it
works, and watch the header keep reading "offline". That contradiction is
exactly what this endpoint has existed to prevent since U199. The probe now also
asks a gated route, and borrows the sentence from `_diagnose()` rather than
writing a second one.

What else came out, and is not a bug: `reachy-mini.local` did not resolve here,
while `Resolve-DnsName reachy-mini.local` returned `192.168.0.178` without
complaint. Windows treats `.local` as reserved for mDNS and never sends such a
name to the ordinary DNS server through `getaddrinfo`, even when the router does
know it. `Resolve-DnsName` bypasses that rule; `ping`, Python and the app do
not. Hence a name that "works" when you test it and fails when the app uses it —
so U198's advice (use an IP) is right, but the reason is more specific than
"mDNS is not working". Worth putting in the setup guide, together with the note
that a DHCP address moves and a fixed reservation on the router is the durable
form.

Three tests, verified red first. Brain green, ruff clean.

### U346 — paired, and the video panel still stayed dark

Reported straight after pairing: *"added it, do i need to restart? still not
seeing video"* (translated). No restart needed — `robot_secret_set: true`,
`connected: true`, `face_visible: true`. And yet no picture.

Measured, and the answer was split in an odd way: `/robot/camera/stream` through
the brain returned 248 kB of real JPEG frames in three seconds, while
`/robot/camera/frame.jpg` returned **401** with `camera unavailable`. The stream
worked and the still frames did not — from the same brain, to the same robot,
one second apart.

The cause is one keyword argument in the wrong place. `_client()` caches a single
`httpx.AsyncClient` for the life of the process and built it with
`headers=robot_auth_headers()`. The brain had started before the pairing key
existed, so that client froze an **empty** header and kept sending it forever.
The MJPEG stream beside it worked precisely because it builds a client per
request. So U339's promise — pair without restarting — held everywhere except on
the path the live video panel polls.

That is the trap named in `robot_auth_headers()`'s own docstring: *"a forgotten
one would look exactly like 'the robot is down'"*. It was not forgotten; it was
bound once and never re-read.

Fixed by not baking the key into the cached client at all: both call sites pass
`headers=robot_auth_headers()` per request. Taken along in the same unit: a 401
on `frame.jpg` answered a bare `camera unavailable`, which blames the camera for
a pairing problem and sends the owner to look at the lens. It now carries the
`reason` from `_diagnose()`.

Three tests, all verified red against the pre-fix code — the first one had to be
sharpened, because the version I wrote first passed against the old code too and
so proved nothing. Then the real path on the real robot: `frame.jpg` HTTP 200,
17004 bytes of JPEG.

### U347 — the ledger was Dutch, in an English repository

Asked plainly: *"the implementation backlog has Dutch in it, always use English
in docs"* (translated).

The Dutch was not an accident — it was written into the working agreement three
times, and that agreement is copied verbatim into `AGENTS.md`, `CLAUDE.md` and
`.github/copilot-instructions.md` with CI failing when the three drift. So the
first thing this unit owes is the rule itself: changing the practice without
changing `docs/agent-working-agreement.md` would have left the rule and the
repository saying different things, which is the failure mode the agreement
exists to prevent.

**What the rule now says.** Everything under `docs/` and `.specify/` is English,
reported problems included. A quote is still a quote, but rendered in English and
marked *(translated)* on first use — because a translated quote is a paraphrase
wearing quotation marks, and a reader deciding what was actually said deserves to
know which one they are holding.

**Three things deliberately stay Dutch**, and the agreement names them so the
next reader does not "fix" them. `docs/demo/*.scenario.yaml` is not prose but
input: those are lines the robot speaks at a Dutch-language talk, and translating
them breaks the demo. Evidence where the language *is* the finding — a transcript
showing him mishandling Dutch proves nothing in English. And
`docs/gebruikershandleiding.md`, the owner-facing manual for a Dutch-speaking
household, which has had an English twin since U38; the owner confirmed it stays.

**I got the size of this wrong three times, and that is the part worth
recording.** First 366 entries, taken from a sentence in the agreement rather
than a count. Then 47, from a regex that only matched `### U` headings. The
ledger actually holds entries in **three** shapes — 224 phase bullets, 98 dated
progress-log lines and 47 `###` entries — and only counting all three gives the
real number. Each wrong estimate was reported confidently before it was measured,
which is the same defect as reporting a robot "unreachable" because one field was
never checked.

**So this unit deliberately does not claim to be finished.** It establishes the
rule, translates the agreement, and converts the Phase 3.5–6 lists and the
agentic phase (roughly thirty items). The rest is still Dutch, and the agreement
says so in as many words rather than describing an end state that does not exist
yet. Anything added from here is English; a Dutch entry someone edits gets
translated while they are in it.

One self-inflicted error found and fixed on the way: a stray Chinese character
landed in the U75 translation (`checked每 step`). That is exactly the noise a
long translation pass produces, and the reason the remainder should be measured
rather than assumed good.

`sync_agent_docs.py --check` in step across the three copies, `check_doc_links`
213 links, `privacy_scan` clean.

### U348 — the graph went stale the moment he learned something

Reported as *"when reading sources, should knowledge graph not be updated
then?"* (translated), and then precisely: *"it does do it when opening, but on
adding, the small window on the right does not update"* (translated).

Both right, and it came down to one line. The canvas cached its node set per
**person**, and the only thing that ever threw that cache away was clicking
somebody else:

```ts
if (graph && graph.pid === pid && graph.nodes.length) return graph
```

So read eight facts off a website: the store updated, the list beside it grew,
and the picture kept drawing the graph from before. No error, no hint — a
drawing that had quietly stopped being true. Reopening the view rebuilt it,
which is exactly why it looked like it worked.

That is the rule this repository already applies to its own diagrams
(constitution IX: *a diagram that used to be true is worse than no diagram,
because it is believed*), now applied to a canvas that watches live data.

The cache is keyed on **what he knows** — a short signature of fact ids, skills
and signals — instead of on who he is. Rebuilding costs nothing because the
layout is deterministically seeded, and on a rebuild existing nodes inherit
their position: the layout settles over the first few seconds, and a node the
owner dragged somewhere is a decision, not a coordinate. The camera stays put
too — yanking the view back to centre because one fact arrived would be its own
small betrayal. Only a different person gets a fresh camera.

Along the way the construction moved out of the canvas component into
`lib/personGraph.ts`, beside `lib/memoryGraph.ts` where that kind of logic
already lives. That is what made it testable for the first time: 8 tests,
including "a dragged node stays where it was put", "a fact that is gone leaves
the graph" and "links never point past the end of the node list".

**Verified by looking, not only by the tests**: an isolated brain on port 8031
(throwaway paths, never `./data`), a fact added through the button, 22 → 23
facts, and the graph on the right rebuilt immediately without reopening
anything. 224 console tests green.

### U349 — one robot, one voice, however many characters the talk needed

Reported as *"for presentator mode, in scenario add the ability to change
persona robot (also in one text so it can swtich to diffrent kind of vocals)"*.

Two asks in one sentence, and the second is the interesting one.

**What was there.** A scenario could set the mode, the trigger, the gesture and
the engine of every beat — but not who was speaking. The presentation had
exactly one voice for its whole length, resolved once, in one line:

```python
audio_b64 = await voice.synthesize_b64(text, voice.resolve_voice(mode="presentation"))
```

Meanwhile the brain has had *characters* since U84 — `dry_tech_butler` at
`ash` 0.95, `kids_companion` at `nova` 1.05, each with its own prompt and
speaking style — and the beat path was the one speaking path in the app that
never consulted them. U273 had already fixed this once for the Present panel's
Voice dropdown; the characters themselves were still invisible from a scenario.

**A beat now names one.** `persona: kids_companion` gives that beat the
character's own voice *and* speed, and when the beat improvises, the character's
note is **appended** to the system prompt so the words are in character too — a
butler's line and a kids' line differ in what they say long before they differ
in timbre. Appended, never substituted: U291 is the unit where a persona
replaced the whole instruction string and deleted the language rule with it.

**And a single line can change character halfway**, which is what the second
half of the request asked for:

```yaml
text: "Misschien. [persona:kids_companion]Of iets veel leukers![persona] De rest typ ik wel."
```

The parsing is a pure function in `shared_schemas/presentation/vocals.py`, with
one rule doing most of the work: **a marker that is nearly right is an error,
not prose.** `[persona:]` does not match the marker grammar, so without a second
deliberately sloppy pattern to catch it, it would have fallen through as text
and been read out loud — "bracket persona colon" — in front of an audience. A
malformed marker is now refused when the scenario is saved, on a screen, at a
desk.

**The part that took the thinking was what happens to the pieces afterwards.**
Two voices means two TTS calls, and the app already has machinery that looks
like the obvious answer: `stream_speech` cuts a reply into chunks and feeds them
to `/robot/speak/segment` one at a time. Reaching for it would have been wrong.
The robot decides playback gain **per utterance** (U153, U329, FR-019), and two
`speak` calls are two normalisation decisions — so the quieter of the two voices
would be pulled up to match the louder one, and the hand-over would land in the
room as a step in volume. The segments are concatenated into one PCM buffer in
the brain instead and sent as a single utterance, which gets the loudness right
*by construction* rather than by coordination. It also adds no new brain→runtime
call on a Pi that is older than the app, and keeps the behaviour engine's
playback events and gesture timeline. Written up as
[ADR-012](adr/ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md),
because the next person to read this will ask why it does not stream.

They are synthesized concurrently, not one after another: a slide-triggered beat
has 500 ms to start speaking (SC-002), and a flourish must not spend that budget.

**What it refuses to do quietly.** A persona id that matches no character is
still spoken — losing a line mid-talk over a typo would be worse — but in the
presentation voice, with `voice_note` in the status naming the id it could not
find, and a warning strip in the Present panel. That is a separate field from
`speech_error` on purpose: *he was heard in the wrong voice* and *he was not
heard* need different reactions from a presenter mid-sentence (constitution XI).
The builder warns about unknown inline ids before the talk, too, where it is
still cheap. And if any one segment fails to synthesize, the line is not played
at all: a sentence quietly missing from the middle of a talk is the harder
failure to notice than a beat that says it could not speak.

**No drawing changed.** `media-paths.svg` is keyed to formats, endpoints and
where synthesis runs; all three are exactly as they were — same PCM s16le mono
@ 24 kHz, same `POST /robot/speak`, still synthesized in the brain. Only the
number of synthesis calls behind one utterance changed, which is not a shape.

**Tests**: 15 in the brain (per-beat voice and speed, the Present Voice setting
still winning when no persona is named, three voices in one line arriving as one
utterance, a dead segment not passing a half line off as whole, the unknown-id
note appearing, clearing, and not carrying into the next talk, the improvised
line written in character), 19 in shared-schemas for the splitter and the beat
validation, 4 in the runner, 2 more in the shipped-scenario dry run, and 19 in
the console. All verified red first. The demo scenario — the repository's
worked example of every beat type — now exercises both shapes, so the dry run
pins them.

The one place this unit *should* have gone and did not is the projector
overlay's presenter strip, which already carries `speech_error` for exactly the
reason `voice_note` exists. `OverlayView.test.ts` is one of the 57 below: it
fails before it mounts, so a change there could not have been verified, and an
unverifiable line in a file about honest reporting is the wrong trade.
**Finished in U351**, once U350 made that suite run again.

**Not verified on the real robot.** Everything here is covered by fakes and by
the FakeRobot path; the one thing tests cannot show is whether 120 ms of silence
between two voices *sounds* like a hand-over in a room. That needs a run on the
actual stack, and it has not had one.

**Also found, not fixed here** (they are their own units): 57 of the 224
operator-console tests fail on `60d0b10` before any of this — all on
`localStorage.clear is not a function` (vitest warns
`--localstorage-file was provided without a valid path`), which looks like
test-environment drift since U348 recorded the same 224 tests green — and two
brain tests in `test_room_awareness.py` expect `_stt_language()` to be `nl`
and get `en`.

### U350 — the tests stopped believing in `localStorage`, and CI could not see it

Reported at the end of U349, as the thing that unit deliberately did not touch:
57 of the operator-console's tests fail on `60d0b10` before any product change,
all of them on `localStorage.clear is not a function`, with vitest printing
`--localstorage-file was provided without a valid path` alongside. It "looks
like test-environment drift".

It was drift. It was not in anything this repository installs.

**What it looked like.** Nine of 28 test files died in `beforeEach`, on their
first line, before asserting anything about the product — `themeStore`,
`characterStore`, `OverlayView`, `PickerMenu`, `SettingsView` and four more.
Every one of them persists a preference, so the obvious reading was that
something in the stores had broken. Nothing in the stores had broken.

**What was actually wrong** is three facts, each harmless on its own.

1. Vitest builds the happy-dom environment by copying the window's properties
   onto Node's `globalThis`, and `getWindowKeys` drops any name that is
   *already* on `globalThis` unless that name appears on vitest's own
   hard-coded list:

   ```js
   if (k in global) return keysArray.includes(k);
   ```

2. `localStorage` is not on that list. Not in 4.1.5, which
   `package-lock.json` pins, and not in 4.1.11, the newest 4.x — both ship the
   same content-hashed chunk, `index.DC7d2Pf8.js`, so the newer release is not
   a fix waiting to be taken.

3. **Node 25 has a `localStorage` global.** Measured here rather than assumed:
   `'localStorage' in globalThis` is `false` on Node 20.20.2, 22.23.2 and
   24.21.0, and `true` on 25.8.0. And without a `--localstorage-file` it is
   inert — an object with no `getItem`, no `setItem`, no `clear`.

Put together: on Node 25 the name collides, vitest yields to the incumbent,
happy-dom's real `Storage` never lands, and what the console talks to for the
rest of the file is a husk. On every Node before 25 there is nothing to collide
with, so the copy happens and everything works.

**Which makes the interesting number the one that stayed green.** The same
commit, the same lockfile, the same `npm ci`, measured both ways:

| | Node 20.20.2 (what CI pins) | Node 25.8.0 (this laptop) |
|---|---|---|
| Before | 243 passed, exit 0 | 57 failed / 186 passed, exit 1 |
| After | 249 passed, exit 0 | 249 passed, exit 0 |

(243, incidentally, not the 224 U349 wrote — that entry's own 19 console tests
had already landed by the time it counted.)

**What changed.** `apps/operator-console/tests/setup.ts`, wired in through
`setupFiles`, installs a `Storage` on `globalThis` for both `localStorage` and
`sessionStorage`. Two choices in it are deliberate and are argued in the file
itself, because that is where whoever later wonders why it exists will be
standing:

- **happy-dom's own `Storage` class, not a hand-written stand-in.** It is the
  exact object the environment was supposed to install, so the tests keep
  browser semantics — a miss is `null`, a value is coerced to a string — rather
  than a lookalike's approximation of them.
- **Unconditionally, not `if (… is missing)`.** A suite that runs one
  environment on the laptop and a different one in CI is how this unit happened
  in the first place. A fresh instance per test file comes free, since setup
  files re-run per file.

`sessionStorage` is included even though no test uses it yet: Node 25 exposes
that global too, on exactly the same terms, and the next test to reach for it
would have found the identical husk.

**No new dependency.** `happy-dom` is already in `package.json`. CLAUDE.md's
rule about `uv sync` pruning what was only ever installed by hand has an npm
twin, and nothing here was added to the working environment alone.

**No drawing and no ADR.** The console's shape did not change — this is the
test harness, not the product — and the decision is small enough to live in the
header of the file it governs rather than outlive it in `docs/adr/`. The spec
carries it as **FR-107**, next to FR-105's "mount tests are the only defence",
because a defence that cannot reach the mount is not one.

**The part worth remembering.** Nothing was wrong with the code. The lockfile
was honest, `npm ci` was reproducible, CI was green, and the suite still could
not run on the machine the repository is written on. A pinned CI Node is a
floor, not a ceiling: it says nothing about a newer runtime growing a global
that a test tool does not know to step around, and it cannot report a class of
failure it is not able to reach. Bumping it, or adding a second version to the
matrix, has the release workflow attached to it and is a decision with a real
blast radius — which is why it is written down here rather than taken quietly
inside a unit about test setup.

**Tests**: 6 new in `tests/environment.test.ts`, asserting the environment
itself — the full `Storage` surface on both globals, `null` for a miss and
string coercion for a value, `window.localStorage` being the same object the
app reaches, the two storages not sharing a `clear()`, and each file starting
empty. Verified red first, on the same `localStorage.clear is not a function`.
The other 57 are the rest of the evidence.

**Still open, and deliberately not bundled here:**

- The two brain tests in `test_room_awareness.py` that expect
  `_stt_language()` to be `nl` and get `en` — unrelated, still unexplained,
  still their own unit.
- U349's note that the projector overlay's presenter strip should carry
  `voice_note` beside `speech_error`. It was left out because `OverlayView`'s
  tests could not run; they can now.
- A `DOMException [AbortError]` from happy-dom's `teardownWindow`, printed
  once during a full run and absent from the next one. It does not change the
  exit code and predates this change, but it is a fetch still in flight when a
  test file ends, which is a real thing somewhere in the suite.

### U351 — the projector strip was still the one place it did not say so

Asked as *"finish this"* — the piece U349 wrote down as outstanding rather than
shipping.

U349 added `voice_note`: he was heard, but not in the voice the scenario asked
for, because a beat named a persona that is not a character here. It reached the
Present panel and stopped there. The projector overlay has carried
`speech_error` on its presenter strip since U269, for the identical reason
recorded in that unit's own comment — *"so it says it here too, where the
presenter is looking"* — and during a talk the presenter is usually looking at
the strip, not at the console.

It was left out for a reason and the reason is now gone. `OverlayView.test.ts`
was one of the 57 console tests that failed before mounting (U350), so a change
there could not have been verified — and an unverifiable line in a feature whose
entire subject is honest reporting is the wrong trade. U350 fixed the test
environment; the suite runs; this is four lines of template and four tests.

Two small decisions worth recording:

- **Stacked, not chained.** The Present panel shows one banner at a time and
  ranks it (rehearsal → not heard → wrong voice), because it is a single slot.
  The overlay strip already stacks `deck_warnings` and `speech_error` as rows,
  so the note joins them as a row. A dead speaker does not make a mis-named
  persona untrue, and a presenter fixing the audio should still learn that the
  butler was spelled wrong.
- **Presenter only.** The block sits inside the strip's existing
  `mode === 'presenter'` guard, so it can never reach the audience layer. A room
  must not read the machinery of the talk it is watching — there is a test for
  that, as there is for the rest of the strip.

**Tests**: 4, verified red first (the note renders; it stays absent when every
persona resolved; it stands beside "could not be heard" rather than instead of
it; the room never sees it). 253 console tests green.

**Not verified on a real projector.** It is the same strip, the same class and
the same guard as the row above it, but nothing here has been on a beamer.

### U352 — he could be quiet, but he could not leave the screen

Asked as *"in presentation mode, within the scenario, add option to define when
overlay is shown or not — if not mentioned (and activated) it will be shown
continuously"*.

The last clause is the whole compatibility contract, and it shaped every
default below: `overlay` absent means "leave it as it is", so a scenario written
before this field behaves exactly as it did.

**What was missing.** A scenario could decide what he says, when he says it, in
whose voice (U349) and whether he moves. It could not decide whether he was on
the projector. `the-question` in the demo has been a `silent` beat since U205 —
the robot shuts up so the owner can own an uncomfortable question — and it was
only ever half of handing the moment over. A face on a slide is watched whether
or not it is talking.

**Hidden is rendered, not closed.** This is the decision the unit turns on.
Electron's `overlay:present:hide` **destroys the `BrowserWindow`**
(`main.cjs:619`), and `show` is always a re-show: a new window, a fresh display
pick, the page loaded again, `onMounted` refetching status and beats. That is
fine once, when the presenter puts the overlay up. Per beat it is a flicker, a
re-pick and a refetch, in front of a room. The overlay window also has **no
preload at all** (`webPreferences: { sandbox: true }`), so it cannot reach
`window.aura` to hide itself even if that were the right idea. So the window
stays exactly where it is and stops drawing — `opacity: 0` on the root with a
350 ms fade, none under `prefers-reduced-motion`. It is already
`pointer-events: none`, so a clear overlay cannot swallow a click on the deck.

**Both channels, on purpose.** The overlay is a separate window with its own
store, and the rule for that (constitution; spec 008 FR-106) is an explicit
channel. This uses both the app has:

- `PresentationOverlayChanged` on the bus — for a window already open, because
  1.5 s of a robot sitting on a slide he was supposed to clear is visible from
  the back of a room. Published **only on a real change**: a beamer redrawing
  itself because a beat restated the obvious is a flicker too.
- `overlay_visible` in `/presentation/status` — for a window opened halfway
  through a talk. *An event only reaches a subscriber that exists when it is
  published*, and this is exactly the state that must survive a late one.

Both write the same field in the store, so there is one answer to "should it be
on screen" rather than two that can disagree; the push just arrives sooner. An
**absent** `overlay_visible` reads as visible, so a console newer than its brain
never blanks the projector.

**Three smaller decisions worth recording:**

- **The projector moves before the line.** The change is emitted at the top of
  `_fire`, ahead of `beat_started`, so a beat that brings him back and then
  speaks does not talk into a blank screen and appear afterwards.
- **A rehearsal still moves it.** U267 holds back the two outputs that reach the
  room — voice and motion. The overlay is the one output a rehearsal exists to
  let you *watch*: checking that he clears the screen at the live demo is a
  reason to walk the show beforehand, and a rehearsal that skipped it could not
  rehearse this at all.
- **The control sits outside the row that vanishes for a silent beat.** In the
  builder the gesture/voice row is hidden for `silent`, and a silent beat is the
  likeliest of all to want this — a beat whose entire job is to clear the screen
  says nothing and gestures nothing.

`hide`/`hidden` and `show`/`shown` are both accepted in both places. A scenario
default reads naturally as a state and a beat as an action, people reach for
either, and refusing one of them teaches nothing. A word that is neither is
refused when the scenario is saved, in a sentence naming the beat — an overlay
that silently ignored a typo would leave the robot on the projector through the
one moment the scenario was written to clear it.

**What it deliberately does not do**: open the overlay. The scenario decides
*when*, never *whether* — the presenter still switches it on in the Present
panel, which is where it has belonged since U266 ("the beamer, not this view, is
the truth"). `overlay: show` on a beat does nothing if no overlay is up, and
that is correct: a YAML file should not be able to put a window on somebody's
beamer.

**Tests**: 9 in shared-schemas for the two fields and their vocabulary, 6 in the
runner (default silence, a beat moving it, a talk starting hidden, no event for
a no-op, the ordering against `beat_started`, and rehearsal), 7 in the brain
(both channels, a fresh talk starting from its own scenario, and the readable
refusal), and 12 in the console across the overlay view, the store and the
builder. All verified red first. The demo scenario now clears the projector for
the hard question and brings him back for the last word, so the dry run pins it.

**Not verified on a real projector.** The fade, and whether 350 ms reads as him
stepping aside rather than as a glitch, needs a beamer and a room.

### U353 — the work laptop would not run the installer at all

Reported with the screenshot Windows actually shows:

> Windows cannot access the specified device, path, or file. You may not have
> the appropriate permissions to access the item.

And beside it the observation that settles the diagnosis: *"for reachy mini
control the SmartScreen prompt ... for aura i get the permissions one"*. The
Reachy Mini Control MSI reaches its **wizard** on that laptop. AURA's installer
never starts.

**Measured before changing anything**, because the obvious answer was wrong.
`Get-AuthenticodeSignature` on both files: **NotSigned**, both. Neither carries
a Mark of the Web. So the unsigned warning really is identical, and signing is
not what separates them — which matters, because U337 and U338 had already
gone at this from the signing side and the honest note in U337 said so: signing
removes "unknown publisher", but *"a managed work PC can still block installs
by policy"*.

The difference is what each installer **is**. An MSI is not a program; it is
data handed to `msiexec.exe`, which is Microsoft-signed and already allowed,
and it lands in `Program Files`. AURA shipped only an NSIS `.exe`, which has to
be executed itself — and electron-builder defaults NSIS to a **per-user**
install in `%LOCALAPPDATA%`, the user-writable location the default AppLocker
rule set exists to deny. The error is Windows refusing to *execute*, before any
wizard could exist.

This is the same argument FR-014 already makes for starting the brain as
`python -m aura_brain` instead of a generated `.venv\Scripts` launcher:
*"unsigned and brand new by construction, which is exactly what a managed
machine's ASR policy refuses; the interpreter is signed and allowed."* The
installer had the identical problem and nobody had connected the two.

**So Windows gets both.** The `.exe` stays untouched — it is the auto-update
path and every install that already exists. The MSI is added with
`perMachine: true`, because electron-builder defaults *that* to per-user too,
and an MSI into `%LOCALAPPDATA%` would have changed nothing at all.

**The part that would have been a defect if left out.** The updater is custom
(U173) and hard-coded `windows-setup.exe`. Shipping an MSI without touching it
means an MSI install auto-downloads the `.exe` and installs a **second** copy
per-user, in a different directory, with the shortcut pointing at whichever won
— a bug introduced by the fix. So an update now follows the way this copy was
installed: the running executable's path decides, the MSI is preferred for a
per-machine install, and it falls back to whatever the release actually carries
because an older release has no MSI and answering "no update available" would
be a lie. The apply script runs the staged file the way that file can be run —
`msiexec /i` rather than `call … /S`, which does nothing useful to an MSI.

That branch is deliberately **not** silent. A per-machine install needs
elevation, and a UAC prompt appearing with no window to explain it is worse
than a wizard the owner can see.

**Tests**: 9 in `scripts/test_windows_installers.py` (both targets built, the
MSI per-machine and assisted, distinct artifact names, the release actually
building and publishing and signing both, the NSIS config pinned so it cannot
drift) and 11 more in `test-updater-verify.cjs` (asset choice each way, the
fallback for a release with no MSI, where-am-I-installed including case and
trailing slashes, and that an MSI is never installed silently). All verified
red first.

**Not verified** *(at the time of writing — see U354, which ran it)*: nothing
here has been run on the work laptop, and I could not read its policy — this
machine is `WORKGROUP` and AppLocker on it is `AuditOnly`. The reasoning is measured (both files unsigned; the MSI installed
machine-wide into `Program Files` with an HKLM uninstall entry; the `.exe`
refused before its wizard), but "the MSI will install there" is a prediction
until it does. Nor has an MSI been built yet: the target is wired, and the
first release to run it is the first proof that WiX packages this app cleanly.

### U354 — the MSI installed, and then Defender would not let it start

Reported with the toast: *"with the msi it installed, but then when launching it
stopped and gave risk warning"*.

**Half of U353 is now measured, and it was right.** The MSI installed on the
managed laptop, into `C:\Program Files\AURA\AURA.exe` — per-machine, in
Program Files, which is exactly what `msi.perMachine: true` was for and exactly
what the `.exe` could never reach. The install path is no longer a prediction.

**The other half found a second gate, and it is one this repository has already
met.** Launching is refused by Defender:

```
Blocked by : Attack surface reduction
Rule       : Block executable files from running unless they meet a
             prevalence, age, or trusted list criteria
Affected   : C:\Program Files\AURA\AURA.exe
```

That is ASR rule `01443614-CD74-433A-B99E-2ECDC07BFC25` — **the same rule, by
id, that U344 hit** on `.venv\Scriptsura-brain.exe`, set by the same IT
department with Tamper Protection on.

U344 got around it because the thing being refused was a *shim*: `uv` writes a
fresh 47 kB unsigned launcher, and there was a signed, prevalent `python.exe`
sitting next to it doing the same job. Starting the brain as a module made the
refused file stop existing.

**There is no equivalent move here.** `AURA.exe` is not a shim standing in front
of the app; it is the app. It is unsigned, it is minutes old, and almost nobody
in the world has run this build — so it fails all three limbs of the rule at
once, by construction, and will fail them again for every release. No build
flag, install location or packaging target changes that. U353 solved *where the
app installs*; this is *whether the binary may run*, and they are different
gates with different keys.

So the honest position, recorded rather than worked around:

- **What unblocks it today** is an ASR exclusion for `C:\Program Files\AURA\`,
  which only IT can add — Tamper Protection means the owner cannot, and should
  not be able to.
- **What unblocks it properly** is the signing already wired in U337 and U338.
  A trusted publisher is the "trusted list" limb of that rule, and it is the one
  limb a project can actually satisfy on purpose; prevalence and age cannot be
  engineered. The wiring waits on a SignPath Foundation project and its token —
  and U338 recorded that its action input names were written from memory, so the
  first real run is also the first test of them.
- **What does not help**, and is worth writing down so it is not tried again:
  another installer format, a different install directory, or turning off
  `runAfterFinish` so the block lands later. The rule is about the executable.

No code changed in this unit. The measurement did: U353's "not verified" is
answered, half confirmed and half replaced by a better-understood blocker.

### U355 — why the same rule lets the other unsigned app run

Asked, fairly, of U354's conclusion: *"why then does it work for reachy mini
control app"*.

It is the right question, because U354 said the ASR rule refuses `AURA.exe` for
being unsigned, minutes old and run by nobody — and Reachy Mini Control is
installed on the same laptop, from an installer already measured as
`NotSigned`, and it starts.

**Measured, and it takes the tidy version of the explanation apart.** The
executables inside that MSI:

```
C:\Program Files\Reachy Mini Control\reachy-mini-control.exe   30 MB  NotSigned
C:\Program Files\Reachy Mini Control\uv-trampoline.exe        343 KB  NotSigned
```

Also unsigned — and it ships a `uv` trampoline of its own, the same *kind* of
file U344 watched this very rule refuse. So signing is not what separates them,
in either direction. U353 established that for the installers; it holds for the
binaries too.

The rule has exactly three limbs — **prevalence, age, or trusted list** — and
one pass is enough. Signing is the trusted-list limb and neither app has it. By
elimination the answer is the other two, and that is where the two projects stop
being comparable:

| | Reachy Mini Control | AURA |
|---|---|---|
| Signed | no | no |
| Binary age | built 2026-08-25, ~3 weeks old | minutes |
| Copies of *this exact binary* in the world | one build, every user who installs it | one build, one user |

**The second row is the one that matters, and it is structural.** FR-002: every
push to `master` produces a versioned release, and there are **162** `v2.0.*`
tags. AURA has never shipped the same binary twice and by design never will, so
every release starts at zero prevalence and zero age and stays there —
Microsoft's cloud has seen that file exactly once, on the machine asking about
it. Reachy ships one build for weeks to everybody, so their file is common and
old by the time a corporate laptop meets it.

So U354's *"prevalence and age cannot be engineered"* was true but too gentle.
For this project they cannot be **reached at all**, at any point in the future,
under the release model the product is built on. That is not a gap waiting to
close with time or downloads: signing is not the best of three doors, it is the
only door there is — which makes the SignPath work in U337/U338 not a polish
item but the entire path to AURA running on a managed machine.

Worth stating plainly beside it, because it is the part I cannot promise: a
fresh certificate proves *who* built the file, and how quickly this particular
rule honours a publisher it has not seen before is not measurable from here. The
exclusion IT can add is the certain route; signing is the durable one.

No code changed. What changed is that one of the three doors is now known to be
permanently shut — worth finding out before spending money on a certificate in
the hope that downloads would eventually do the job instead.

### U356 — the button was disabled, and nothing anywhere said so

Reported as *"brain import -> clicking button does not work"*, with a
screenshot of **Move him to another laptop** and its empty passphrase field.

It works exactly as written. Both buttons are gated:

```
:disabled="transferPass.length < 8 || transferring"
```

and the field was empty, so `Import…` was dead. The defect is not the gate —
Import genuinely needs the passphrase the file was sealed with, so it belongs
there. The defect is that **nothing said so**, and one line of CSS made it
worse than silent:

```css
.d2-ghost-btn { … cursor: pointer; }
.d2-ghost-btn:hover { border-color: var(--accent); color: var(--accent); }
```

No `:disabled` rule at all. So a disabled ghost button kept full contrast, kept
`cursor: pointer`, and **lit up accent on hover** — it advertised itself as
clickable and then ate the click. `.d2-primary-btn` had `opacity: 0.5;
cursor: not-allowed` from the start, so this was a gap in one class, not a
decision.

It is not one button. `.d2-ghost-btn` is the app's workhorse: **17** of them
across ten views are `:disabled` under some condition — *Save key*, *Refresh*,
*Connect*, the realtime test, and the two here. Every one of them has been
lying by omission. (`.d2-danger-btn` has the same missing rule; checked, and no
danger button is ever disabled, so it is left alone rather than changed on
spec.)

Two fixes, because dimming alone would only have said *no*:

- `:hover` is now `:hover:not(:disabled)` and there is a real `:disabled` rule.
  The hover rule is the one that actively misled, so guarding it matters more
  than the dimming.
- The transfer row says **why**. The passphrase gates *both* buttons, which is
  not guessable from a field that sits beside them looking like an export-only
  setting.

**Tests**: 3 on the transfer row (both buttons disabled while the passphrase is
short, a hint that explains it, and both released the moment it is long enough)
and 3 on the stylesheet itself. The style tests are a poor substitute for
looking at it — there is no `vue-tsc` here and jsdom applies none of this CSS —
but they are a great deal better than the nothing that let a whole class of
buttons ship without a disabled state. 271 console tests green.

**Not verified by eye**: the dimmed button has not been looked at on screen,
only asserted in the stylesheet.

### U357 — he lay down, and then put his head back up

Reported as *"when i tell it to go to sleep, it should remain in the sleep
position (now it executes it and then jumps back)"*, and then precisely, which
is what made it findable: *"went down in the shell/torso, but once this was
finished, the head jumped back up"*.

**Not the loops.** That was the obvious suspect, because U237 and U238 exist for
exactly this shape of bug — the on-device loops that keep the robot from looking
frozen used to stand it straight back up. Measured before touching anything:
`POST /robot/sleep` answered `{"asleep": true, "stays_down": true}`, so the
runtime *had* been told and its loops were suppressed. U237 is working. The
torso staying down proved it too.

**It was the head, and it was asked for.** The brain's sleep sequence is: tell
the runtime, turn follow-me off, then strike the pose. The middle step is the
problem. Turning follow-me off recentres the head (U165), for a good reason — an
awake robot that stops following should not sit staring at the last place it saw
a face. But it means going to sleep issues this, one step before `goto_sleep()`:

```python
self._mini.goto_target(head=_NEUTRAL, duration=1.0, body_yaw=None)
```

A one-second interpolation to *upright*, commanded as part of lying down. In the
stubbed adapter the calls are synchronous and it merely looks redundant; on the
real robot the move is still in flight when the emote runs, so it completes
after `goto_sleep()` has finished and the head comes back up. Exactly what was
described, and the reason the torso was unaffected: only the head was ever
commanded.

Fixed where the knowledge lives rather than at the call site: the adapter skips
the recentre while `sleep_state.is_asleep()`. U237 already decided this — *sleep
means take no action of your own* — and lifting the head is precisely such an
action. Doing it in the runtime means it holds however the sequence is ordered,
and for any future caller that turns follow-me off near a sleeping robot. The
tracker is still paused; this is about the **pose**, not the tracking.

**Tests**: three, against the stubbed SDK that records every call — the head is
not commanded anywhere while asleep, an *awake* robot still recentres (U165 must
not regress, and it is the kind of thing a fix like this quietly takes away),
and the full brain sequence leaves `goto_sleep` as the last thing that moves
him. The first was verified red and failed with the identity matrix in the
message, which is the bug written out as an assertion. 138 robot-runtime tests
green.

**Not verified on the robot.** The stub cannot reproduce the overlap that makes
this visible — in it the recentre simply happened before the emote — so the
tests pin the command that must not be sent, not the jump itself. Whether the
head now stays down needs a press of the button on the real robot.

### U357b — follow-me, checked before the fix went to the robot

Asked before deploying U357: *"ensure follow me will still keep working when
starting aura, or when doing wake up; if so you can deploy"*.

The right question. U357 stops the head being recentred while asleep, and the
failure mode of a fix like that is a suppression that outlives the sleep it was
for — a robot that wakes up and never looks at anyone again. Reading the code
says it cannot happen; the code said the loops could not stand him up either,
and they were not the problem.

Three tests, one per way it could go wrong:

- **Boot.** A fresh runtime is never asleep — `sleep_state` starts `False` — so
  connect starts the tracker. Pinned, including the assumption about the
  starting state, since the whole guard rests on it.
- **Wake.** The full sequence the brain sends, in its real order: clear the
  sleep state, play the wake emote, turn follow-me back on. Tracking comes back
  and `_tracking_on` is `True`.
- **Scope.** Once awake, turning follow-me off recentres again. This is the one
  that would catch a leak, and it is the reason U165 is still whole.

**One thing the check found, which is why it was worth writing.** The boot test
first asserted he also settles upright on connect, and it failed — not a
product bug but a hole in the stub: `FakeMini` has no `enable_motors`, so
connect's wake-and-settle block raises and is logged before the emote is
reached. Every test in this file has been connecting to a robot that throws
half-way through `connect()`. The tracker start sits after that block, which is
why the half this unit cares about is genuinely observable — and the assertion
that is not observable was removed and written down rather than quietly
softened into something that passes.

Worth fixing on its own: a stub that cannot complete `connect()` leaves the boot
pose path untested for everyone.

141 robot-runtime tests green, 403 orchestrator, ruff clean. Deployed to the Pi
after this.

### U358 — teaching a face with your eyes shut

Asked for as *"for the teach your face, show camera view while it's detecting,
so i know it's teaching the right face"*.

**Taken literally it would not have worked**, and finding that out first changed
the shape of the fix. Enrollment grabs four frames in about **1.5 seconds**
(`for i in range(4)` over ~1.5 s, U18), and the frame loop needs roughly 250 ms
to put its first picture on screen. A camera that appears *while it detects*
would show you the tail of something already decided — and, for a one-shot
button, arrive as the result did.

So the picture comes **first**. *Teach face* now opens the robot's live view
with the person's name beside it — *"Check it is Jan in the picture before you
take them"* — and a second, deliberate press takes the photos. The result lands
with the camera still up, because the message is about the face that was just
in shot and closing the picture as the answer arrives takes away the only thing
that can confirm it.

**The setup wizard has done exactly this since it existed** — a `face-cam` next
to *Teach him your face*. The Robot panel, which is where the Memory tab sends
you when it says *"teach him this face"*, fired blind. Two flows for one job,
and only one of them let you look.

**Where the camera lives is the design decision.** `useCameraFeed` starts its
frame loop on mount and stops it on unmount, so the call site decides how long
the robot is polled. Called in `PeopleView` it would fetch frames over WiFi for
as long as anybody had a person open — against the grain of U219, which exists
to halve exactly this traffic. It is a component now (`CameraPreview.vue`), so
a `v-if` is the on/off switch, and there is a test that unmounting really does
stop the polling rather than merely hiding the picture.

**Tests**: 6 on the view (camera off until asked; it appears on the first press;
the person is named in it; the photos are only taken on the second press; the
picture survives the result; Close puts it away) and 4 on the component. Five of
the six were verified red against the old view — the sixth, "the camera stays
off until it is asked for", passes on the old code too, which is right: it is a
guard against a future regression, not a description of the bug.

**Found while writing them**: the component tests leaked. Every mounted preview
polls until unmounted, and `@vue/test-utils` does not unmount between cases, so
a leaked instance counted its frames into the next test and the stop-polling
assertion failed for the wrong reason. `enableAutoUnmount(afterEach)` fixes it —
worth writing down because the symptom looked exactly like the bug under test.

**Not verified by eye**: the layout has not been looked at on screen, only
asserted. 281 console tests green.

### U359 — one failed line, and he never spoke again

Found mid-rehearsal, one slide into the Devoxx talk. The first line played. The
next one, and every one after it, came back:

> He was not heard — Server error '500 Internal Server Error' for url
> 'http://172.20.10.8:8001/robot/speak' For more information check:
> https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500

Two failures in one sentence, and the second is the one that hid the first.

**Why he went mute.** `BehaviorEngine.speak()` read:

```python
await self.transition(BehaviorState.SPEAKING)
...
await asyncio.gather(*tasks)          # the audio
await self._bus.publish(SpeechPlaybackCompleted(...))
await self.transition(BehaviorState.IDLE)
```

Nothing guarded. A playback that raises skips the last line and leaves the
engine in SPEAKING — and `SPEAKING → SPEAKING` is **not** in the transition
table (`behavior/states.py`: SPEAKING may go to RESPONDING or IDLE, nothing
else). So the next line raised `TransitionBlockedError` before it reached the
speaker, and so did every line after it. One transient audio failure, and the
robot cannot speak again for the rest of the session — on stage, permanently,
with the talk still running.

The state now comes back in a `finally`. The failure still propagates, because
the caller must hear that the line was not said (U269); it is only the state
that may not survive it. `SpeechPlaybackCompleted` moved into the `finally`
too — it means *no longer playing*, not *played well*, and the console derives
its speaking indicator from the pair, so a start with no completion is a
subtitle that never clears and an avatar that mouths for ever.

**Why nobody could tell.** The route had no error handling at all, so any
exception became a bare 500 — and a bare 500 sends the owner to a page about
HTTP status codes in the middle of a talk. The robot knew exactly what had
failed and said none of it. It now answers **503** with the cause attached
(503 because this is "he could not, right now", not "that request was wrong"),
and `RobotClient` puts that reason into the error it raises rather than
httpx's status-and-a-link. Type and response are preserved — `set_asleep()`
and friends branch on `exc.response.status_code == 404`, and a message change
must not quietly break the skew handling U238 exists for.

**Tests**: three on the engine (the state returns after a failure; he really
does speak again afterwards; the room is never left thinking he is still
talking), one on the route (a failure answers with the reason, not a 500), and
two on the client (the reason reaches the message; a body-less error still
raises normally, because an older robot or a proxy answers with HTML). All
verified red — the client test failed with the MDN link in the assertion
message, which is the bug quoted back.

145 robot-runtime tests green, 716 brain.

**Not verified on the robot**: what actually raised during that first line is
still unknown — it happened on a phone hotspot, and the robot's own log needs
SSH this laptop does not have. This unit makes the failure survivable and
legible; it does not explain it. If it recurs, the 503 will now name it.

### U360 — the scenario said `voice: onyx`, and nothing was listening

Found mid-rehearsal, alongside U359. A generated conference scenario had a gag
built on a second voice:

```yaml
  - id: the-fanfare
    mode: speak
    text: "Ta. Ta. Ta. Taa-ta-taaa. Taa-ta-taa."
    voice: onyx
    speed: 0.85
```

The file's own comment explains why: *"A DIFFERENT VOICE (onyx, at 0.85×) —
this is not the robot, it is the robot doing an orchestra, and the switch is
what separates the two jokes."* The switch never happened. `voice`, `speed` and
`pause` are not fields on `Beat`, **pydantic ignores unknown keys by default**,
so the scenario validated cleanly and all three evaporated. The gag came out in
the ordinary voice, the 7-second wait that lines the setup line up with a video
crawl did not happen, and no screen anywhere said a word.

Measured before changing anything, because "it must be the voice resolution"
was the tempting answer:

```
voice -> <DROPPED>   speed -> <DROPPED>   pause -> <DROPPED>
no error was raised: the beat validated fine
```

**So: the fields exist now, and unknown fields are refused.** The second half
matters more than the first. `extra="forbid"` on `Beat` and `Scenario` turns a
misspelt key into a load failure that names itself, at the one moment it is
still cheap — at a desk, with the file open. Everything this repository keeps
learning about honest state says the same thing: a setting that is quietly
ignored is worse than one that is rejected.

`voice` and `speed` are the narrow form of U349's `persona` — a line that wants
a different sound without a whole character behind it — so they win where both
are given, **including over inline `[persona:x]` segments**. A line cannot be
both "all in onyx" and "this bit in somebody else's voice"; the beat said onyx.

`pause` waits before speaking, for lining a line up with something on *screen*
rather than with the slide change that fired the beat. A rehearsal skips it:
U267's rehearsal is for reading the lines, not for waiting out a video.

**The list of voices moved down.** Validating `voice: onix` needs the voice
names where the schema can see them, and they lived only in `aura_brain.voice`.
They are in `shared_schemas.voice.voices` now and the brain re-exports the same
name, because a second copy of a list like that drifts the first time one of
them is edited.

**One knock-on worth the extra ten minutes.** The scenario builder has no
control for these three fields, and it rebuilds every beat from its form on
save — so loading a generated scenario and pressing Save would have stripped
exactly what the file was written for. It carries them through untouched now,
with a test. Silently undoing a file's whole reason for existing is the same
defect wearing a different hat.

The runner also stopped passing fields one at a time: it hands the speaker the
**whole beat**. That is what made this possible to fix at all — `voice` could
not have reached TTS through a `speak(text, persona)` signature however well
the model carried it.

**Tests**: 8 in shared-schemas (the three fields, their defaults, a voice
refused by name, a speed outside what the provider takes, a negative pause, and
unknown keys on both models), 3 in the runner (the beat reaches the speaker; a
pause is waited; a rehearsal is not), 4 in the brain (voice and speed reach
TTS; a named voice beats the persona; a persona still decides when no voice is
named; a speed alone works), and 1 in the console round-trip. All verified red.

178 shared-schemas, 406 orchestrator, 720 brain, 282 console.

### U361 — the format, written down, and a way to check a file before the room

Asked for alongside U359 and U360: *"also provide me fixed scenario with
instructions i can give to claude cowork to fix it in the future"*.

**The scenario did not need fixing.** After U360 the file validated exactly as
generated, with both of the fields that had been evaporating:

```
OK - I Hired a Real Robot as My Junior Dev
  beats           23
  he speaks       5 time(s)
  you press       3 time(s): sound-check, the-disclaimer, last-word
  armed keywords  Java
  slide cues      8, 9, 29, 41, 48, 57, 58, 59, 62, 67, 68, 79, 84, 86, 91, 104, 107
  overlay starts  shown
  ! the-setup: waits 7.0s before speaking
  ! the-fanfare: voice onyx at 0.85x
```

The app was the thing that was wrong. What was actually missing is the other
half of the request: somewhere to point a generator at, and a way to find out a
file is wrong at a desk rather than on a stage.

**`docs/demo/scenario-format.md`** is the whole format — every field with its
type and default, the trigger forms, what each mode requires, inline persona
markers, and a section of the things that bite. It says outright that the model
is the authority and the document is a bug if they disagree, and it ends with
five rules for an assistant regenerating a scenario. The first is *never invent
a field*: since U360 that is a refused load, and before U360 it was worse —
silence.

**`scripts/check_scenario.py`** runs the same validation the Present panel runs
and then says what the talk will *do*: how many times he speaks, which presses
are the presenter's, which keywords are armed, which slides carry cues, where
the overlay starts, and every beat that changes voice or waits before speaking.
A checker that only answers "valid" leaves you no wiser than before opening it.
Exit 0 or 1, so it fits a pre-flight script.

Refusals quote the beat: a misspelt `voise: onyx` comes back as
`0.voise: Extra inputs are not permitted`, which is the U360 failure caught
where it is still free.

**Found while testing it**: the script crashed under `subprocess` with output
that was fine in a terminal. An em dash in a `print`, a captured stdout on
Windows, cp1252 — and a passing check became a `UnicodeEncodeError`. The output
is ASCII now, and the reason is written at the top of the file so nobody
prettifies it back. It is the same family as the heredoc trap CLAUDE.md already
records: this repository runs on Windows, and anything that writes bytes has to
mean it.

**Tests**: 7 — the shipped scenario passes, the report actually contains the
five things it promises, a misspelt field is refused by name, a broken beat
names the beat, YAML that is not YAML says so, a missing file is a sentence and
not a traceback, and the flags for voice and pause appear. 91 tests in
`scripts/`, which CI runs wholesale.

### U362 — the same file, picked twice, did nothing

Reported during Devoxx prep: *"when i import a yaml, second time i import it
does not seem to load? (first time after startup app it worked)"*.

A file input fires `change` only when its **value** changes. Pick the same file
again and that is not a change, so nothing fires: no request, no error, no
scenario, and a panel still saying *No scenario yet*. "First time after startup
it worked" is the exact signature — the first pick always changes the value,
because it starts empty.

`SettingsView` already cleared its input in a `finally`. `PresentView` never
did, and neither did `PeopleView`'s chat import — **three file inputs, one of
them right**, and the one that was right got there by being written last.

Both are fixed the same way, and the `finally` matters as much as the clearing:
the one time you are certain to pick the same file name again is straight after
a rejected file, having just fixed it.

**The test was wrong before the code was right.** The first version asserted
`el.value === ''` after the import — and passed, with and without the fix,
because jsdom reports a file input's value as `''` and refuses to be set. A
test that passes against the bug is worse than no test: it is a claim of
coverage. The tests now install a property setter and assert on the **write**,
which is the thing the fix actually does. That mistake is why the second
instance in `PeopleView` got found at all — going back to check the first test
meant reading the others.

**Also found**: the People test tripped an unhandled rejection that vitest flags
as "might cause false positive tests". Not a product bug — the fetch stub
answered `{}` to the view's own re-fetch of the person, which replaced `detail`
mid-render and threw inside the template. Having just been caught by one false
pass, taking the warning at face value was not optional. The stub answers that
call properly now.

**Tests**: 3 on Present (the input is cleared; the scenario is posted; it is
cleared after a failure too) and 2 on People. All verified red — genuinely, the
second time. 287 console tests green.

### U363 — twenty megabytes of log, and not one beat in it

Found while diagnosing U362's neighbour: a beat that fired but did not speak.
The question was the simplest one there is — *did that beat fire?* — and the
runner answers it, at INFO, on purpose:

```python
logger.info("beat %r fired (mode=%s trigger=%s)", beat.id, beat.mode, beat.trigger)
```

`brain.log` was 20 MB. It contained `grep -c beat` → **0**.

**Nothing configured logging.** `uvicorn.run()` installs its own loggers and
leaves the root at WARNING, so every `logger.info` in `aura_brain`, the
orchestrator and the runner was discarded on the way out. Every careful log line
this repository has written over 360 units — the beats, "robot is now asleep",
the degradation notices — went nowhere. What survived was uvicorn's access log,
which is why the file is enormous and says nothing.

On a stage that file is the only record there is.

`configure_logging()` runs before uvicorn: INFO by default, `LOG_LEVEL` to
override, and a nonsense value is never fatal — this is the process the whole
app waits on, and a typo in an env var must not stop it starting. The noisy HTTP
libraries are pinned at WARNING, because the camera is polled several times a
second and `httpx` at INFO would bury the very thing this unit is for.

**The first version broke six unrelated tests, and the fix is the interesting
part.** `basicConfig(force=True)` is the obvious way to be idempotent. It also
**closes every existing root handler** — in a test run, pytest's own capture.
The handler is now added once, identified by an attribute, and nothing else is
ever removed or closed. uvicorn adds handlers too; closing those would have been
worse than the bug.

A second thing the same mistake caused: the test asserting the beat line comes
out could not see it through `caplog`, because `force=True` had removed
caplog's handler while the line printed perfectly. It reads the stream now,
which is also what `brain.log` actually is — so the assertion is on the real
artefact rather than on a test fixture.

**Tests**: 6 — the app's loggers are heard, the beat line genuinely comes out,
the noisy libraries stay quiet, the level can be turned down, a nonsense level
is not fatal, and configuring twice does not double every line.

**Reported and not fixed here**: six brain tests fail in this working copy —
`test_proactive.py` (5) and `test_speech_dispatch.py` (1). They are **not** from
this unit: with every line of it removed the suite still reports 714 passed and
those same 6 failed, and with it, 720 passed and the same 6. They passed a few
hours earlier, so something in the environment moved rather than the code —
these tests read the real `./personas` and the real environment rather than a
throwaway one, which is the shape of the problem even if the trigger is not yet
named. Left for its own unit rather than folded into this one.

### U364 — a child's memory, handed to the model as a fact

Found while checking the published blog series against the code: two posts and
both Devoxx talks say a minor's assistant knows what it was *told* and nothing
it *inferred*. The spec says the same (018, US4.1), and so does ADR-008 §10.
The code did not.

**What was actually wrong.** The rule was enforced in two places, and both of
them only guarded observed *signals*: `record_signal` refuses a minor without
consent, and the judgment layer drops a minor's signals. But since U109 the
learning that actually runs is not a signal. It is `PersonMemory`: a model's
summary of the conversation, stored as a `ProfileFact` with key `memory`.
`PersonMemory.record` never looked at the person's role, so a child's
conversations were distilled like anybody else's, and the judgment layer, which
passes a minor "explicit facts only", passed that memory along with them,
because a memory is a fact by type. Inference, labelled as explicit.
`look_up_person` (U294) goes through the same layer, so it leaked the same way.

**What changed.**

- `PersonMemory` asks, before buffering a turn and again before distilling,
  whether this person may be learned about: anyone who is not a minor, or a
  minor the owner opted in with the existing `observed_learning` consent. It
  checks twice so that a role changed between the two cannot slip through. It
  fails closed: if the store cannot say who this is, nothing is learned. A
  child's words are not even held in the buffer.
- The judgment layer leaves a minor's `memory` fact out of the prompt unless
  that consent exists. This is what covers a memory distilled **before** this
  unit, which is still on the profile, visible and deletable in the console,
  and now no longer sent anywhere. It is filtered before the fact cap, so it
  cannot crowd out a real fact either.
- The owner writing a minor's memory by hand is not gated, because that is
  explicit. With no consent it is still not injected, and the owner can add the
  same thing as an ordinary fact instead.

The demo profile is deliberately left alone: `ensure_minor_learning_consent`
also refuses the demo persona, and reusing it would have changed what a talk's
demo profile learns in the same commit as a privacy fix. That is a separate
question.

**Tests**: 6 new. Three describe the bug and were verified red against the old
code: a minor is not remembered and the model is never called; a role changed
to minor before the flush is not distilled; the judgment layer drops a minor's
memory without consent. Three are guards that pass either way and must keep
passing: a minor with consent is remembered, the judgment layer keeps that
memory, and the owner's own edit still works. `test_passive_learning_stops_on_stage` built
`PersonMemory(store=None)`, which only worked while `record()` never looked at
the store; it now gets an empty store, with the reason written beside it.
shared-schemas 180, orchestrator 406, brain 729 (1 skipped), all run with the
keys unset. In a fresh clone the six failures U363 reported do not reproduce,
which supports its reading that they came from that working copy's environment.

### U365 — the video was moving and the header said he was offline

Reported as (translated): *"why is it taking so long for Richie to come online?
Also at some point we see video moving (together with Richie moving) but AURA
still says robot offline — in the title bar, the video, …"*.

Both halves are one defect, and the evidence was already on the screen: a
moving picture is proof the robot is answering. Asked directly while the
console said offline, the brain answered:

```
/robot/status → {"connected": true, "mode": "online", "adapter_name": "reachy"}
```

So the console was not showing the brain's truth. It was showing something else
that had gone stale, beside a camera feed that had not.

**Fault one — the bridge could not follow him.** `RobotEventBridge` derived its
WebSocket URL once, in `__init__`, from whatever `ROBOT_RUNTIME_URL` said at
startup. U336 taught the brain to follow the robot to a new address by
rewriting that variable and `RobotClient._base_url` — which every HTTP call
reads *per request*. The bridge read neither. After the move onto the phone
hotspot earlier that day, the camera proxy, the status poll and speech all went
to the new address while the event stream hammered the old one, forever. It now
takes a getter instead of a string. No watcher is needed while it is connected:
the address only changes *because* the old one stopped answering, so the socket
is already down by the time it does.

**Fault two — a retry announced a fresh disconnect every five seconds.** That
flood is what made a wrong answer permanent rather than brief: anything the
console learned by asking was overwritten a moment later. A disconnect is a
transition, not a heartbeat, and is now published once on the way down.

**Fault three — the console asked twice in its life.** U297 made it ask instead
of only listening: once on mount, and again whenever the event socket reopens.
Everything after that arrived as events, so a single wrong or missed
`RobotDisconnected` stayed on screen until the app was restarted. It asks on a
timer now. Events stay the fast path; the poll is what makes being wrong
temporary — the rule this repository already states, that state which must
survive a late subscriber is polled, not awaited.

**Asked for explicitly**: *"make sure this is tested so it does not happen
again"* (translated). The bridge had **no tests at all**, which is how it
survived. It has five now, including the address change and the "one disconnect
per transition" rule.

And the shell had never been mounted by anything — which bit immediately:
writing the watch into `App.vue` used `onUnmounted` without importing it, and
the store test beside it passed cheerfully while the window was broken. There
is no `vue-tsc` here, so that is not a build error, it is a blank screen in
front of the owner. `AppShell.test.ts` was **verified against the break**:
restoring the missing import turned three red tests green, and removing it
again reproduces `ReferenceError: onUnmounted is not defined`.

One thing fixed in passing, and it was mine: `test_brain_bundle` asserted that
the sealed export does not contain `b"Jan"`. Three letters turn up in random
base64 often enough to fail a run for no reason, and it did. The property being
tested is "the plaintext is not readable in the file", so it now asserts that
with a string long enough to mean it. Re-run three times to confirm.

### U366 — Quiet changed the header and nothing else

Reported again, after U333 (translated): *"quiet mode and stop still seem not
to work (although activated he keeps going)"*, with the instruction: *"make
sure we don't have this regression any more"*.

It was not a regression of U333. It was the same rule, written in one place and
needed in three — which is the more durable kind of bug, because every
individual fix looks complete.

**Where the gates were.** U256 gave the owner the Quiet switch. U332 made it
real at the *start* of a turn: while Quiet is on, a turn is never handed to a
session that listens without a wake word. U334 did the same for Present mode.
Both gates sit where a turn is decided — and an open Live session is not a
turn. It holds the microphone for up to `LIVE_SESSION_MAX_S`, **ten minutes**
by default, and answers whatever is loudest in the room. The supervising loop
ticks about once a second and asked, every single tick, whether the owner had
pressed Stop. It never asked whether he was still allowed to speak.

So switching Quiet on mid-conversation changed the chip in the header and
nothing else, for up to ten minutes. Exactly what was reported, twice.

**The nastier half, which explains "Stop does not work" as well.** A Live
session that produced no reply is treated as a failure, and the pipeline
answers instead — correct when the model falls over, and precisely wrong when
the session ended *because* silence was asked for. The test for "was this
deliberate?" was a string comparison against `"stopped by owner"`, true only as
long as Stop was the only deliberate way to end a session. So a session ended
by Quiet looked like a failure, and the pipeline then said out loud the answer
to the question the owner had just silenced. It now asks the session
(`sess.stopped`) instead of matching a sentence.

**What changed.** The question has one home, `aura_brain/hush.py`, and both
session loops ask it on the tick they already use for Stop. Stop, Quiet and
Present now mean the same thing — *now*, not when this conversation happens to
end — and each says which of the three it was instead of borrowing the owner's
name for it. The entry gate asks the same module, so there is one rule rather
than two that drift.

It keeps the older rule pointing the other way on purpose: **an unreadable
policy never silences him.** A robot that goes mute because a JSON file would
not parse is a fault nobody can diagnose from the outside; a robot that keeps
talking is the state everyone already understands.

**Made hard to lose again**, which is what was actually asked for. Seven tests,
each verified against the old code:

* Quiet switched on mid-conversation ends it, and within about a second rather
  than eventually — driving the **real** policy module the console's switch
  writes through, so a future change that keeps the gate but breaks the chain
  still fails.
* Present mode ends an open conversation.
* The realtime engine falls silent too: a switch that works on one engine and
  not the other is worse than neither, because it teaches the owner to trust it.
* A session ended by Quiet is not handed to the pipeline to be answered aloud.
* An unreadable policy never ends a conversation.
* And a structural one: anything that holds a microphone open must consult
  `hush`. A new session type added next year fails in the suite rather than in
  the owner's living room.

### U367 — CI had been red for six units, and the installers kept shipping

Asked, in two words: *"build failed?"* It had — on every push since U361, six
units earlier. Nothing said so, because the Release workflow is green and
independent: builds kept appearing in the usual place while the checks beside
them failed.

The cause is a leftover of my own U337. That unit replaced a hand-kept list of
*tests* in the "Repository checks" step with `pytest scripts/ -q`, on the
grounds that a test CI does not run is a comment with a docstring — and left a
hand-kept list of *dependencies* on the line directly above it:

```yaml
pip install pillow pyyaml
pytest scripts/ -q
```

The same mistake, one level down. U361 added `scripts/check_scenario.py`, which
imports `shared_schemas` and therefore pydantic. The list could not know, and
the failure did not read like a missing package: seven tests failed on
assertions like `assert 'voice onyx' in ''`, with the real
`ModuleNotFoundError` buried inside a subprocess's captured stdout. It looks
like the script is broken rather than the job that runs it.

The step installs the workspace now (`uv sync --all-packages`), which is what
the scripts actually import and what every other job in this repository already
does — and runs it as `python -m pytest`, not `pytest`.

**That second half cost a second red build**, and the lesson is the older one
in this repository's own trap list. The first attempt ran `uv run
--all-packages pytest`, which looked right and stayed red: an earlier step in
the *same job* does `pip install pytest`, so `uv run` found that binary on
PATH and ran it on the runner's interpreter — with none of the workspace it had
just installed. The giveaway was in the traceback all along
(`/opt/hostedtoolcache/...` instead of `.venv/...`).

It was verified locally before pushing, and the verification was worthless:
this machine's `.venv` already had everything, so the command could not fail
here for the reason it failed there. The honest check is a clean room, and it
is cheap — `uv run --isolated --no-project --with pytest python -m pytest
scripts/test_scripts_are_runnable.py` reproduces a bare environment, where the
guard correctly reports `{'check_scenario.py': {'yaml'}, 'readme_shots.py':
{'PIL'}}`.

The run also passes `--continue-on-collection-errors`, because without it two
modules failing to import abort collection and the guard never gets to speak —
the readable explanation was there and pytest stopped before printing it. And `scripts/test_scripts_are_runnable.py` stays behind it: it reads the
top-level imports of every script and reports, by name, any module this
environment cannot provide, with the file to fix. Deliberately `ast`-based
rather than importing each script — importing runs module-level code, and the
point is to say what is missing *without* depending on being able to run it.

**Worth a decision, not taken here:** Release does not depend on CI. That is
defensible — a red documentation check should probably not stop a build — but
it is also why nobody noticed for six units. Coupling them, or having the
release summary say what CI thought of the same commit, is the owner's call.

### U368 — one gate, and a release that cannot skip it

The first fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T1), which was
asked for as (translated): *"all specs should be tested and validated at all
times on any release, automated — there is too much regression"*.

The most direct cause of the seven red builds that shipped anyway (U361–U367)
was not a missing test. It was that **CI and Release each kept their own list
of what must pass**, and the lists had drifted: Release lacked
`identity-service` and `test-brain-launch.cjs`, and ran none of the repository
checks — no privacy scan before publishing, no spec drift, no doc links, none
of `scripts/`. So CI went red and Release, consulting its own shorter list,
stayed green and published. U337 removed one hand-kept list, U367 a second;
this was the third, and the only one that decides whether a build reaches the
owner.

Now there is **one file**: `.github/workflows/checks.yml`, a reusable workflow
holding every job CI had, verbatim. `ci.yml` calls it and nothing else.
`release.yml`'s gate job calls it too, and `build` and `release` depend on
that job. A suite is listed once, or not at all.

`scripts/test_release_gate.py` keeps it that way, and does the thing a list
cannot: it **walks the tree** for every package with a test file and every
`apps/desktop/test-*.cjs`, and fails if the gate does not run one. On its very
first run it found a third omission — `packages/shared-prompts/tests/`, which
has existed since April with only an `__init__.py` in it (audit T11). The walk
now requires a real test file, because pytest on an empty directory exits 5
and would have failed the gate for a suite that does not exist.

Verified the way the audit says to: both suites Release had been skipping pass
(`identity-service`: 6, `test-brain-launch.cjs`: ok), all three workflows
parse, the signing-order tests (U337/U338) still hold on the restructured
`release.yml`, and the first push through the new gate is watched to
completion rather than assumed.

### U369 — a spec was claimed, not validated

Second fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T2).

`spec_drift.py` (U299) closed sixty-nine units of drift by checking one
direction: every shipped unit is claimed by a spec. It never checked the other.
A spec could claim a unit whose behaviour no test protected, and the
constitution's "no code merged without traceability to a spec acceptance
criterion" was checkable exactly as far as the claim and no further.

The audit measured what that left open: **122 of 394 claimed units are named
by no test file at all.** Spec 020 (desktop) 40 of 61; spec 015 13 of 19; spec
008 (console) 19 of 40. Recent ones include U333, U343, U344, U354 and U355.
The twelve repeat-reports since U300 are what that looks like from the owner's
chair — a fix with nothing standing behind it is a fix the next refactor
removes without noticing, which is exactly how U366 happened to U332.

`scripts/spec_tests.py` is the sibling: a unit is *named by a test* when its
id appears in any `test_*.py` or `*.test.ts` — the convention every test here
already follows — and a claimed unit no test names is reported by spec. Same
shape as `spec_drift.py` on purpose: a second baseline, `tests_baseline`, in
`.specify/coverage.json` marks the 122 as historical debt, reported on every
run so the number stays in view; every unit after it must be named by a test
or the gate fails. `scripts/test_spec_tests.py` refuses a baseline that moves
forward, and `--list` prints the debt one unit per line so paying it is a
checklist rather than an archaeology.

It runs inside `checks.yml` (U368), so it gates both CI and Release. First
real run: *no new untested units — but 122 claimed unit(s) up to the U367b
baseline are named by no test.* That sentence is the audit's headline number,
now printed on every push until it is zero.

### U369b — the check's own tests vouched for units they knew nothing about

Caught within the hour, by the check itself. The first version of
`scripts/test_spec_tests.py` used real-looking ids as fixture data — a spec
claiming `U299, U300, U301`, a test naming `U339` — and the moment that file
was tracked, the debt reported by `spec_tests.py` fell from 122 to 117 with no
test written. The tokenizer does exactly what it says: a unit id anywhere in a
test file names that unit. Fixture data is anywhere.

Fixtures now use the `U8xx` range, three digits (four are invisible to the
`U\d{1,3}` token both checks share) and far above any real unit for years.
One more slipped through the first pass: a *comment* naming the baseline unit
as the ceiling the baseline may not exceed. Spelled in two parts now.

Two things worth keeping from this:

* **A pipe swallowed a red guard.** The pre-commit chain ran
  `python scripts/spec_tests.py | head -1`, which printed *1 claimed unit(s)
  that no test names* and then let the commit through, because `head` owns the
  exit code. The same trap as the deploy script in U333 and the ruff slip in
  U332 — noted then, repeated now. The one unnamed unit was U369 itself: the
  new test file was not yet `git add`ed, and only **tracked** files vouch.
  That behaviour is right (a stray local file must not certify anything); the
  order of operations was not.
* **The debt number is the product.** 122 is what the audit measured, 122 is
  what the check reports again after this fix, and any drop from here on has a
  test behind it or is a bug in the check.

### U370 — half the console had never been mounted

Third fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T4).

Five of the ten views had never been imported by any test — `TalkView`, the
screen the owner looks at most, among them — along with seven stores
(`modeStore`, which owns the Quiet switch that U256, U332 and U366 were all
about) and nine components (the setup wizard, the approval panel, both
canvases). This project has no `vue-tsc`; esbuild strips types unchecked. So
"never mounted" means "never compiled", and the compile error is delivered to
whoever opens that panel next. U365 had just shown the shape of it: a missing
import in `App.vue`, green everywhere, blank in front of the owner.

Three sweeps, and none of them keeps a list:

* **Every view.** The ids are read from `navStore.ts`'s `View` union — the
  same union `App.vue` switches on — and each is shown inside the mounted
  shell with a route-aware fetch stub and no `[Vue warn]` allowed. Add
  `'diary'` to the type without mounting it and this fails, by name.
* **Every component.** The directory under `src/components` is the list; each
  file is mounted with its required props from a small table. Two entries were
  missing on the first run (`PhotoLightbox` needs `src`, `PickerMenu` needs
  `open` and `items`) and the message said so.
* **Every store.** Every `use*Store` under `src/stores` is constructed —
  the cheapest compile step there is — and `modeStore`'s Quiet switch is
  exercised both ways: it writes through `/orchestrator/policy/quiet`, and
  when the brain refuses it snaps back rather than leaving the chip on HUSHED
  over a robot that is not.

All ten views mounted clean on the first run. That is worth saying plainly:
this unit found no broken screen. What it removes is the way the *next* broken
screen would have shipped. Console suite: 341 green, 47 of them new.

One thing observed while this landed, and not explained: the first Release
run through the new gate (U368) reached *Publish release* with the same token
permissions as every green run before it and was refused with HTTP 403; the
very next run (U369) published v2.0.177 through the identical workflow. Noted
here so a second occurrence is a pattern and not a surprise.

### U372 — nothing ran the gate locally

Fourth fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T5).

There was no `Makefile`, no root script, no single command that did what CI
does. So "verified locally" meant "ran the suite I remembered", and U367b is
what that costs: a fix verified in a primed venv, wrong on the runner, and a
second red build to find out.

`scripts/gate.py` reads `.github/workflows/checks.yml` — the one list, since
U368 — and runs its `run:` steps through bash in the runner's order, with each
step's `working-directory` and `env`, stopping at the first failure as the
runner does. `--job test` runs one job, `--list` prints what would run,
`--keep-going` reports every failure at once. It is the file, not a copy of
it: a step added to the gate runs here on the next invocation, and there is no
second list to forget. Environment steps (`pip install`, `uv sync`, `npm ci`)
run too, so a fresh clone is treated like the runner.

Verified by running it: `--list` prints the thirty-one steps CI runs, and
`--job lint` executed end to end on this machine — *gate green -- 2 step(s) in
13s, the same steps CI runs*. One Windows lesson on the way: the first version
printed a check mark and the console's cp1252 encoding took the whole gate
down with a `UnicodeEncodeError`. The output is plain ASCII now and the
streams are reconfigured to replace rather than raise, so a step that prints a
glyph cannot fail the gate by printing it.

The working agreement names it: "verified locally" means the gate ran here.
That line is synced into `CLAUDE.md`, `AGENTS.md` and the Copilot
instructions by `sync_agent_docs.py`, which the gate itself checks.

### U371 — the robot being behind the laptop was invisible in the app

Fifth fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T6).

The Pi is deployed separately from the laptop. It has been 74 commits behind
once (the U240 report) and was one behind on the day of the audit, and nothing
in the brain or the console said so. `deploy_robot.py --check` did — if you
remembered it existed. Every "the fix did not work" that was really "the fix
is not on the Pi yet" was diagnosed by hand; the Quiet/Stop report that became
U366 started with exactly that check, done by hand, before the real cause was
found.

The comparison the script makes is made in the brain now and travels with
`/robot/status` as `build: {robot, laptop, behind}`. The robot's commit comes
from `/health.build` (U240), asked **once** per runtime rather than on every
status poll — a commit does not change while the runtime runs, and the console
polls every ten seconds since U365. The laptop's commit is the honest part:

* a checkout asks `git rev-parse HEAD`;
* a packaged app has no `.git`, so the release now writes `BUILD_COMMIT` into
  the packaged tree and the desktop shell hands it to the brain as
  `AURA_BUILD_COMMIT`;
* neither present — an installer older than this — and `laptop` is `null`,
  `behind` is `null`, and the card says *cannot compare*. Two unknowns that
  happen to be equal must never read as "same build" (constitution XI).

The Connection card renders three sentences: *f145485 — behind this laptop
(8f179ce) · run `python scripts/deploy_robot.py`*, *same build as this
laptop*, and *cannot compare — this build carries no stamp*; a runtime older
than U240 gets *does not report its build*.

**Verified as far as it could be.** Seven brain tests (including the
once-per-runtime rule and the checkout-beats-stale-stamp rule), four console
mount tests, the packaging and brain-launch checks on the stamped
`package.json`, and `laptop_commit()` returning this checkout's HEAD. The
robot itself was off while this landed — `/health` answered nothing by name
or by address — so the live line was not seen; `/health.build` has answered
to `deploy_robot.py --check` all day, and that is what the comparison reads.
The first deploy after this is where it will show, and should.

Also noted, because it looked like a failure and was not: U370's Release run
was **cancelled** with no job started. The release workflow's concurrency
group keeps at most one *pending* run; U372 arrived while U370 was still
queued behind U369b, and the queue kept the newer one. Not every commit gets
its own installer under load — true before this audit, and unchanged by it.

### U373 — a test directory that had held only `__init__.py` since April

Sixth fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T11), found by
U368's tree walk on its first run.

`packages/shared-prompts` renders the system prompt every persona speaks from
(`orchestrator/persona_manager.py` calls it), the approval request the owner
reads before a tool runs, and the daily context block. It had a `tests/`
directory, a `dev` extra with pytest in it, and no test — since the scaffold
in April. The gate could not even run it: pytest exits 5 on an empty
directory, so the walk that finds unlisted suites had to be taught to skip it.

Six tests now, on rendered text rather than on the template engine: the
persona and context arrive in the system prompt; the two guardrail lines are
in every one of them (a persona without "never reveal bearer tokens" is a
persona that may read one back to the room); an owner-typed `<` or `&` reaches
the model as typed rather than as `&lt;`, because prompts are not web pages;
the approval request names the tool, the requester and the reply it asks for;
the context summary carries its count as a number; and blank lines stay
trimmed so the model is not reading past doubled newlines.

The suite is listed in `checks.yml`, and `scripts/test_release_gate.py`'s
walk — which requires a real test file before it insists on a suite — now
insists on this one.

### U374 — the settings every connector reads, tested for the first time

Seventh fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T8).

`packages/shared-config` is 233 lines that every connector and the identity
service read at start-up — which connectors are on, which keyring backend
holds the tokens, where the calendar link is — and it had no tests and no
`tests/` directory. What goes wrong in a settings module is quiet: a secret
that prints in a traceback, a connector list that keeps an empty entry, a
developer's `.env.local` deciding what a test measures. Quiet is the kind this
audit is about.

Twelve tests. The ones worth naming: the keyring passphrase and the Azure
client secret are `SecretStr` and do not appear in `repr`, `str` or
`model_dump` — a settings object ends up in logs, and the secret in it must
not; an unknown keyring backend is refused rather than guessed; `"m365,,"`
from a hand-edited env enables one connector, not three; and every settings
object in the suite is built with `_env_file=None`, because the `.env.local`
on the machine running the tests must not be what they measure.

Listed in `checks.yml`; the gate's tree walk now insists on it.

### U375 — the settings an update could reset, pinned by test

Eighth fix from the testing audit
([`docs/audit-testing-2026-09.md`](audit-testing-2026-09.md), T7), and the
last of this pass.

U177 moved the knowledge store, the faces, the memory DB and the skills out
of the install directory, because an NSIS update replaces that directory
wholesale. U327 found the settings U177 had left behind — the mode policy,
the MCP servers, the connector preferences, the turn traces — still
defaulting to `./data`, which for a packaged app *is* the install directory.
Reported as "quiet mode is on and he still talks": an update had reset the
file the brain reads. Both fixes live in `brainEnv()` in `main.cjs`, and
nothing checked that the list was complete or that a later edit had not
quietly dropped a line from it.

`apps/desktop/test-brain-env.cjs` does. Eleven owner-state paths must default
under the owner's data directory and never to a relative path; an explicit
`.env` value must win over each default (the `||` is the contract — the
wizard's choice beats the shell's); voice providers must be forced off in the
shell; and the U371 build stamp must reach the brain. It is source-level, like
the four checks beside it, because `main.cjs` requires `electron` at load and
cannot be imported by plain node — weaker than executing `brainEnv()`, and
exactly strong enough for the U327 class. **Proven red** against it: with
`MODE_POLICY_PATH` reverted to `'./data/mode-policy.json'` the check fails by
name, and passes again on restore. In the gate.

**A pattern, now with two data points.** U371's release was refused at
*Publish release* with HTTP 403 — the same refusal U368 met, on the same
printed token permissions, with a fresh tag number each time. The two are the
only commits in this pass that edited `release.yml`; the three that did not
(U369, U369b, U372) published v2.0.177–179 through the identical workflow.
Recorded as audit T12 with the rule of thumb it implies — a commit that edits
the release workflow does not ship its own installer; the next one does — and
the two ways to settle it: reproduce on purpose with a comment-only edit, or
move publishing to a `workflow_run` on CI success so the file that publishes
is never the file that changed. Not decided here.

Where the audit's numbers stand at the end of the pass: suites in the gate 10
→ 12, tests 1,828 → 1,931, and `spec_tests.py` prints **117** (see U375b for
why 122 was an undercount) — the debt is the debt, and the gate now refuses to
let it grow.

### U375b — the check did not count the desktop's own tests

U375 added `apps/desktop/test-brain-env.cjs`, named itself in it, and the
pre-commit run of `spec_tests.py` printed *1 claimed unit(s) that no test
names* — U375. The commit went through because the exit code was printed and
not acted on, which is the third time this session that pattern has cost a
red build, and it is now the reason `gate.py` exists.

The check's globs were `test_*.py` and `*.test.ts`: what pytest and vitest
collect. The desktop shell's checks are plain-node `test-*.cjs` scripts, run
by the gate like any other suite, and the check did not know them. A test
file is whatever the gate runs. `*test-*.cjs` is in the globs now, with a test
that a `.cjs` file names a unit, and U375 is named by the check it added.

**The number moved, and it should have.** The real run reports **117**, not
122: five units — U224 (`test-updater-verify.cjs`), U229 and U234
(`test-console-origin.cjs`), U239 (`test-bootstrap-extras.cjs`), U344
(`test-brain-launch.cjs`) — had been guarded by desktop checks all along, and
the check was not looking at the suite that guards them. The audit's 122
undercounted the *coverage*, not the debt; this is the check catching its own
blind spot, which is the correct direction for the number to move.

(Two things went wrong landing this and are on record because the pattern is
the point of the whole audit: the ledger text of U375b was written *before*
the run and said "the same 122"; and a `\n` inside a heredoc became a real
newline inside a string literal, so the test file shipped with a
`SyntaxError` — the trap CLAUDE.md names, met again. Both fixed in U375c, with
the guards run *and acted on* before the push.)
