# ADR-003: Robot Adapter Abstraction

**Status**: Accepted 2026-04-25 — **amended 2026-09-05**  
**Date**: 2026-04-25  
**Deciders**: AURA Platform Team

---

## Context

AURA is designed to run on Reachy Mini (a physical robot), but development cannot depend on hardware availability. We need:
- All development to proceed without physical hardware
- Hardware-specific code to be isolated from business logic
- A contract test suite that any robot adapter must pass
- A clear path to add physical hardware support later without changing core services

---

## Decision

**`RobotAdapter` ABC** defined in `packages/shared-schemas/src/shared_schemas/robot/adapter.py`  
**`FakeRobotAdapter`** in `services/robot-runtime/src/robot_runtime/adapters/fake.py` — primary dev target  
**`ReachyRobotAdapter`** (future) in `services/robot-runtime/src/robot_runtime/adapters/reachy.py`  
**Contract Tests** in `tests/contract/test_robot_adapter_contract.py` — parameterized over all adapters  
**Selection**: `ROBOT_ADAPTER=fake|reachy` environment variable  

No Reachy SDK imports are permitted outside `ReachyRobotAdapter`.

---

## RobotAdapter Interface

```python
class RobotAdapter(ABC):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def get_status(self) -> RobotState: ...
    async def speak(self, text: str) -> None: ...
    async def play_audio(self, audio_chunk: bytes) -> None: ...
    async def capture_audio(self) -> bytes: ...
    async def get_camera_frame(self) -> bytes: ...
    async def execute_motion(self, command: MotionCommand) -> None: ...
    async def execute_timeline(self, timeline: MotionTimeline) -> None: ...
    async def set_state(self, mode: RobotMode) -> None: ...
```

---

## Rationale

### ABC Pattern
- Python ABCs enforce interface compliance at class definition time
- Contract tests parameterized over all adapters catch regressions when the interface changes
- The adapter pattern is well-understood and requires no frameworks

### FakeRobot as Primary Dev Target
- FakeRobot logs speech to stdout, returns static PNG for camera, returns silence for audio
- All service tests run with FakeRobot — CI never requires hardware
- FakeRobot emits the same events as real hardware (MotionStarted, SpeechPlaybackStarted, etc.)
- Speeds up the development loop: no hardware setup, no physical teardown

### 9-Method Interface
- The 9 methods cover all robot capabilities AURA needs: speech, audio, camera, motion, state
- Keeping the interface small (9 methods) prevents the ABC from becoming a god object
- `execute_timeline()` enables synchronized speech+motion without higher-level services needing to coordinate timing

### No Reachy SDK in Orchestrator
- The orchestrator (and all services above robot-runtime) must not import Reachy SDK types
- This is enforced by the constitution and verified by `grep -r "reachy" services/orchestrator/` in CI
- Decouples AURA's business logic from any specific robot model

---

## Consequences

### Positive
- All features can be developed and tested without hardware
- Adding a new robot adapter requires only implementing the 9-method ABC
- Contract tests automatically verify any new adapter's correctness
- Clear seam for hardware integration (one file: `reachy.py`)

### Negative
- FakeRobot behavior diverges from real hardware over time (needs periodic sync)
- The 9-method interface may need extension if new Reachy Mini capabilities are added
- Fake audio/camera outputs are not suitable for testing audio processing logic

### Neutral
- Physical hardware testing must be done manually with `ROBOT_ADAPTER=reachy`
- The Reachy SDK version must be pinned in `robot-runtime/pyproject.toml` only

---

## Alternatives Considered

| Option | Reason Rejected |
|--------|----------------|
| Direct Reachy SDK calls in orchestrator | Violates hardware abstraction; cannot test without hardware |
| Mock (MagicMock) instead of FakeRobot | No event emission; no realistic behavior; not reusable |
| Protocol (structural subtyping) instead of ABC | Less explicit; no `__abstractmethods__` enforcement |
| One adapter per capability | Too many small ABCs; harder to configure and inject |

---

## Amendment — 2026-09-05

*Recorded as part of the documentation catch-up (U315).*

This is the decision that has paid off most, and it is worth saying how.

**`FakeRobot` never became a development convenience.** It is load-bearing in
production tooling: the release pipeline boots `ROBOT_ADAPTER=fake` to take
every screenshot, which is what makes those images privacy-safe **by
construction** rather than by review — no camera, no model, no keys, one
fictional persona ([spec 020](../../.specify/specs/020-desktop-app-and-releases/spec.md)).
An abstraction adopted for testability turned out to be the thing that lets the
project publish pictures of itself at all.

**The ABC does not live beside its implementations.** `RobotAdapter` is in
[`packages/shared-schemas/src/shared_schemas/robot/adapter.py`](../../packages/shared-schemas/src/shared_schemas/robot/adapter.py),
not in `robot-runtime`. That is what lets the brain depend on the contract
without depending on the runtime — and it survived the topology collapse of
[ADR-007](ADR-007-topology-and-capability-reshape.md) unchanged, which is the
test of whether a boundary was real.

*(For four months `AGENTS.md` told every agent this file was at
`services/robot-runtime/src/robot_runtime/adapters/base.py`, which has never
existed. Corrected in U315, along with four other paths in the same block, and
now checked by `scripts/check_doc_links.py`.)*

**Where the abstraction is deliberately not the boundary.** Constitution X —
tolerating a robot runtime older than the brain — lives at the **HTTP** seam
(`RobotClient`, U13), not at the adapter. The adapter's contract is what the
robot can do; the client's contract is what this particular robot, today,
happens to implement. Conflating them would push deployment skew down into
`FakeRobot`, where it has no meaning.
