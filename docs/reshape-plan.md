# AURA Reshape Plan

A phased migration from the current 6-service scaffold to a two-deployable,
capability-complete personal Reachy assistant. Companion to
[ADR-007](adr/ADR-007-topology-and-capability-reshape.md).

**Guiding rule:** every phase ends with the system still runnable
(`FakeRobot` + echo/mock). No big-bang rewrite. Keep the safety gate intact at
all times.

**Hardware:** target is the **Reachy Mini Wireless (Raspberry Pi 5)**. The Pi runs
only motion + audio I/O; the brain (STT, LLM, knowledge base) lives on the
laptop. This is assumed throughout.

---

## Phase 0 (spike, do this FIRST) — streaming voice latency de-risk (2–4 days)

Rationale: "does it feel instant?" is the single biggest unknown and the thing
most likely to invalidate the whole approach. Prove it on the real hardware +
real provider **before** investing in the restructure. This is a throwaway
vertical spike — correctness/cleanliness not required, *measured latency* is.

- [ ] Minimal path: Pi mic → laptop → **streaming STT** (OpenAI Realtime API, or
      streaming local Whisper) → LLM with **token streaming** → **streaming TTS**
      → Pi speaker. Skip orchestration, tools, approval, memory entirely.
- [ ] Instrument and record **first-word-out** and **full-turn** latency over the
      real LAN link, on the actual Pi 5, with your actual provider/subscription.
- [ ] Prove **barge-in**: speaking over AURA cancels in-flight TTS within ~200ms.
- [ ] Compare cloud Realtime vs streaming-local on the Pi-class path; decide the
      default and the offline fallback tier from measured numbers, not the ADR.
- [ ] **Go/no-go:** if streaming hits a usable target (e.g. < ~700ms first word),
      proceed with confidence. If not, the voice transport — not the architecture
      — is the thing to solve first, and we know it now instead of after Phase 3.

**Exit:** a real, measured, interruptible spoken round-trip on the Wireless, with
numbers that justify (or redirect) the rest of the plan. Findings feed Phase 3.5.

---

## Phase 0b — De-risk what exists (1–2 days)

Prove the current online path actually works before restructuring around it.

- [ ] **Fix tool-calling.** In `services/orchestrator/src/orchestrator/pipeline.py`,
      pass real function schemas to the LLM (`openai_chat(messages, tools=...)`)
      and build those schemas from `MODE_TOOL_MAP` / the `_TOOL_ROUTES` table.
      Confirm a real `tool_calls` round-trips: "what meetings do I have today?"
      → `list_calendar_events_today` → mock connector → spoken answer.
- [ ] **End-to-end smoke test** (FakeRobot + mock M365 + echo→real LLM) covering
      one read tool and one write tool (to exercise the approval gate).
- [ ] **Delete dead ceremony from the working tree.** Move `.github/apm/` and
      `knowledge/` to `docs/method/` (or a separate archive repo). Add a
      `.gitignore` entry for the stray `node_modules/`, `dist/`, `.pytest_cache/`
      currently untracked.
- [ ] Decide LLM-provider story for "brain": confirm provider switch covers your
      ChatGPT/Claude/Copilot subscriptions via API keys, and note which need a
      local proxy.

**Exit:** a real conversation triggers a real (mock) tool call and an approval.

---

## Phase 1 — Collapse to `aura-brain` (3–5 days)

Merge orchestrator + conversation-runtime + connector-service + memory-service +
identity-service into **one process**, keeping module boundaries as packages.

- [ ] New `services/aura-brain/` (or `apps/aura-brain/`) with a single FastAPI
      app that mounts the existing routers as sub-apps / routers.
- [ ] Replace cross-service `httpx` calls (`pipeline._call_connector`,
      `fallback_agent._create_reminder`, identity-token fetches) with in-process
      calls. Keep the function signatures; swap the transport.
- [ ] One `AsyncEventBus` instance shared by all brain modules → the WebSocket
      broadcaster now has the full event stream in one place.
- [ ] Collapse Compose from 7 containers to **2**: `aura-brain`, `robot-runtime`
      (+ `operator-console` dev server = 3 for dev).
- [ ] Keep all existing unit tests green; convert the cross-service integration
      tests to in-process.

**Exit:** `docker compose up` runs brain + robot; the README text-turn still works.

---

## Phase 2 — Real laptop↔Reachy split & resilience (3–4 days)

- [ ] Define the **one** network boundary: brain (laptop) ↔ robot-runtime
      (Reachy) over WebSocket/REST on the LAN.
- [ ] Rework `HeartbeatMonitor` to watch **(a)** the brain↔robot link and
      **(b)** the brain's upstream internet — not sibling containers. Mode
      transitions (`ONLINE/DEGRADED/OFFLINE`) key off these two signals.
- [ ] Ship an **on-device offline behavior loop** in `robot-runtime`: idle
      motion, a spoken "I've lost connection to my brain," local wake-word ack —
      so the robot is never dead when the laptop is unreachable.

### Reachy Mini packaging — this is *how the logic gets onto the robot*

Target hardware is the **Reachy Mini Wireless (Pi 5)**. The current
`robot-runtime` is a generic Dockerized FastAPI service — that is **not** how
Reachy Mini apps are installed, and `adapters/reachy.py` does not yet exist.

- [ ] Implement `services/robot-runtime/src/robot_runtime/adapters/reachy.py`
      against the Reachy Mini SDK; must pass the same `RobotAdapter` contract
      tests as `FakeRobot` (this is Phase 3d — pull it forward to here).
- [ ] **Package `robot-runtime` as a Reachy Mini app**, not a Docker container:
      a `pyproject`/entry-point app the Reachy dashboard/runtime can install on
      the Pi, with an app manifest and one-command setup. ("Upload + easy setup"
      = this item; it does not exist today.)
- [ ] Run on the Pi via the Reachy app runtime (or a systemd unit) — **not**
      Docker-on-Pi for the realtime motion/audio path.
- [ ] The Pi runs **only** motion + audio I/O + the on-device offline loop. STT,
      LLM, and the knowledge base never run on the Pi — they stay on the laptop
      brain. Document the two-host bring-up (laptop brain ↔ Pi robot) in `infra/`.

**Exit:** robot speaks/moves via the real adapter; you can install/update the
on-robot logic in one step; pull the network → robot degrades gracefully
on-device; reconnect restores full function; queued sensitive actions still
require fresh approval.

---

## Phase 3 — Capability spine (parallelizable after Phase 1)

### 3a. Recognition (`robot-runtime/perception/`)
- [ ] Camera capture + face detection/embedding (e.g. `insightface` or
      `face_recognition`). Enrollment flow for you + family ("this is Jan").
- [ ] Local, **encrypted** embedding store (biometric data — extends
      Constitution VI: never logged, never leaves the device).
- [ ] Emit `PersonRecognized{identity, confidence}`; brain reacts: greet by name,
      auto-suggest mode (you→work/dev, family→family, unknown→guarded).
- [ ] New schema in `shared-schemas`; contract test like the adapter pattern.

### 3b. Outbound dev-agent tool (brain)
- [ ] A tool the LLM can call: `run_dev_task{repo, instruction}` that drives
      Claude Code / a VS Code task / shell. **Routed through `ApprovalManager`**
      — this is your highest-risk capability; reuse the gate you already built.
- [ ] Scope/sandbox: allow-list of repos/dirs, no network-write without approval,
      audit every invocation (the gateway audit pattern already exists).

### 3c. Local-LLM provider (brain)
- [ ] Add `ollama` / `llama.cpp` as a provider in `orchestrator/llm.py` behind
      the existing switch. Offline mode degrades to a *local model*, not regex.
- [ ] Optional: keep `FallbackAgent` regex as the tier-3 fallback if even the
      local model is unavailable.

### 3d. Real `ReachyRobotAdapter`
- [ ] Implement against the Reachy Mini SDK in `robot-runtime/adapters/reachy.py`;
      must pass the **same** `RobotAdapter` contract tests as `FakeRobot`.

### 3e. Personal Knowledge & Judgment Layer — "geweten en kennisbank" (brain)

A per-person, evolving model of how you and family members work and react, so
AURA anticipates and supports rather than just responds. **This is the most
privacy-sensitive thing in the system** — design security first, features second.
Warrants its own ADR-008 (data model + crypto + consent) before build.

**Two layers:**
- **Kennisbank (knowledge base)** — a per-person profile that accumulates:
  - *Explicit* facts you teach it ("remember I prefer mornings for deep work",
    "draft mail to my manager formally"). Always inspectable and editable.
  - *Observed* preferences/patterns distilled from interactions (tone, schedule
    rhythms, recurring context, what each person tends to ask for).
  - Relationships/identities (links to recognition 3a: who is who).
- **Geweten (judgment/anticipation)** — uses the profile to (a) proactively
  surface support ("your 9:00 moved; want me to tell the family?") and (b) act
  with restraint appropriate to *who is present* and *what mode* — an extension
  of the existing approval/policy gate, now personalized.

**Security — "securely saved, only reachable by me" is the hard requirement:**
- [ ] **Per-person encrypted stores.** Each person's profile is a separate store,
      **encrypted at rest** (key derived from your unlock secret / OS keyring —
      reuse the identity-service `cryptfile` keyring pattern already in the repo).
- [ ] **Owner-gated access.** Your profile decrypts only when *you* are the
      authenticated owner. Family profiles are readable/editable **only by you**,
      not by each other; a recognized family member unlocks *their own* limited
      view, a stranger unlocks nothing. Recognition (3a) gates which store opens.
- [ ] **Unlock UX (ADR-008 §9) — tiered, recognition ≠ auth:**
  - *Benign tier* on face recognition only: greet by name, non-sensitive context.
  - *Sensitive tier* (owner's working default) via **OS-session binding** — brain
    runs under your Windows account; the master key in Credential Manager is
    DPAPI-gated by your Windows login / Windows Hello. No spoken passphrase
    (overheard); a spoken *"lock AURA"* to drop tiers is fine.
  - *Step-up* for the riskiest actions (destructive dev-agent ops, profile export,
    deleting a person, changing crypto/consent) via **paired-phone push approval**
    — reuse the existing `ApprovalManager` + `webhook_dispatcher`.
  - **Auto-relock** to benign on OS lock/sleep/logout, owner absent > 5 min,
    unknown face, or explicit lock. Face arriving never raises the tier.
- [ ] **Minors: explicit-only by default (ADR-008 §10)** — `role=minor` profiles
      get no passive learning and never gate/authorize anything; owner-only view;
      passive learning requires deliberate per-child opt-in.
- [ ] **Local-only, never egressed.** Profiles never leave the laptop, never go to
      a cloud LLM wholesale — only the minimal, relevant slice is injected into a
      prompt per turn, and never logged (extends Constitution VI to behavioural
      data, which for family/children is special-category personal data).
- [ ] **Transparent & revocable.** A console view to *see exactly what AURA knows*
      about each person, edit it, and delete it. Consent is explicit for family
      members; observed-learning is opt-in and clearly indicated.
- [ ] **Schema + store ABC** in `shared-schemas` (extend the `MemoryStore`
      pattern from session-scoped to person-scoped + encrypted); contract tests.

**Sequencing:** depends on 3a (recognition tells it *who*). Start with the
explicit-teaching knowledge base (low risk, high trust); add observed-pattern
learning only after the security model and the transparency UI are in place.

**Exit per sub-stream:** each lands independently behind a flag; recognition is
the priority (it's the soul of the project and currently at zero), and 3e builds
directly on it.

---

## Phase 3.5 — Performance & responsiveness (do *with* Phase 3, gate the demo on it)

Latency targets exist in the specs but the implementation does not meet them.
A desk robot that takes several silent seconds per turn fails the "feels alive"
bar regardless of features. Treat this as a hard gate, not polish.

**Current reality (measured against the code, not the specs):**
- Voice STT/TTS uses **batch** `whisper-1` / `tts-1` (buffer the whole
  utterance), *not* the OpenAI Realtime API the ADR-005 promises — seconds, not
  ~300ms. `stream_transcribe` discards the streaming contract.
- Responses are returned as **complete strings**; nothing streams to TTS.
- **No barge-in** despite the constitution requiring it on both paths.
- A tool-using turn makes **two sequential LLM calls** (`pipeline.py:94` and
  `:170`).
- Multi-hop REST per turn (removed by the Phase 1 collapse).

**Work items:**
- [ ] Set an explicit **per-turn latency budget** and *measure* it end-to-end
      (first-audio-out, full-turn) — wire timings into the existing event stream
      so the console shows real numbers.
- [ ] Real **streaming STT** (partial transcripts) — adopt the OpenAI Realtime
      API the constitution already names, or a streaming local Whisper, behind
      the existing provider ABC.
- [ ] **Token-stream the LLM response into TTS** so speech starts on the first
      clause, not after the full answer.
- [ ] **Barge-in / interruption**: cancel in-flight TTS + motion on new
      `AudioInputStarted` (the `BehaviorEngine.interrupt()` hook already exists).
- [ ] **Single-pass tool calling** where possible (stream the final answer after
      the tool result instead of a cold second call); parallelize independent
      tool calls.
- [ ] **On-Pi budget guard** (Wireless): keep STT/LLM off the Pi; only motion +
      audio I/O run on-device, driven by the laptop brain.

**Exit:** measured first-word latency and full-turn latency meet the stated
targets on your actual hardware + provider, with speech that starts streaming
and can be interrupted.

---

## Phase 4 — Presentations & polish

- [ ] Tie `presentation.py` to real slides + synchronized robot
      gestures/speech; "present with me" co-pilot mode.
- [ ] Operator-console pass for the new events (PersonRecognized, dev-agent
      approvals, link-health).

---

## Sequencing summary

```
Phase 0  (voice latency spike — FIRST, go/no-go)
   │
Phase 0b (fix tool-calling + prove)  ──►  Phase 1 (collapse brain)  ──►  Phase 2 (split + Reachy Wireless packaging + resilience)
                                      │
                                      └──►  Phase 3a recognition  (priority)
                                      │          └──►  Phase 3e knowledge & judgment ("geweten") — owner-only, encrypted
                                      └──►  Phase 3b dev-agent
                                      └──►  Phase 3c local LLM
                                      └──►  Phase 3d Reachy adapter (+ device packaging, see Phase 2)
                                                     │
                                      Phase 3.5 perf/responsiveness (hard demo gate)
                                                     │
                                                     └──►  Phase 4 presentations/polish
```

## What we explicitly keep

- `gateway.py` (auth/rate-limit/audit), `ApprovalManager`, `shared-policies`
  mode/approval model — the security core.
- `RobotAdapter` ABC + `FakeRobot` as primary dev target.
- `shared-schemas` event/model discipline.
- The multi-provider LLM switch.

## What we retire

- 4 of 6 service boundaries (merged into the brain).
- The per-service in-process "event bus as architecture" claim.
- `.github/apm/` + `knowledge/` from the product repo.
