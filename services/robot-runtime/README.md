# robot-runtime

**Port**: 8001  
**Spec**: [002-fakerobot-simulation](.../../.specify/specs/002-fakerobot-simulation/spec.md), [004-behavior-engine](../../.specify/specs/004-behavior-engine/spec.md)

## Responsibilities

- Owns the `RobotAdapter` ABC and all concrete adapter implementations
- Hosts `FakeRobotAdapter` (primary development target)
- Hosts `ReachyRobotAdapter` (future — physical hardware)
- Runs the `BehaviorEngine` — coordinates idle, listening, thinking, and speaking behaviors
- Executes `MotionTimeline` objects (synchronized speech + motion)
- Emits robot and behavior events to the shared event bus

## Key Interfaces

- `RobotAdapter` — 9-method ABC in `shared-schemas`
- `FakeRobotAdapter` — logs speech, returns static PNG for camera, returns silence for audio
- `BehaviorEngine` — `plan_behavior()`, `create_speaking_timeline(text)`, `interrupt()`
- REST: `POST /robot/speak`, `POST /robot/motion`, `GET /robot/status`
- WebSocket: `/ws/events` — streams all robot and behavior events

## Running Locally

```bash
cd services/robot-runtime
cp ../../infra/dev/.env.example .env
uv run uvicorn robot_runtime.main:app --reload --port 8001
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROBOT_ADAPTER` | `fake` | `fake` or `reachy` |
| `IDLE_INTERVAL_SECONDS` | `4` | Idle motion interval |

## Tests

```bash
uv run pytest tests/unit/
uv run pytest ../../tests/contract/test_robot_adapter_contract.py --adapter=fake
```

## Architecture Notes

- `BehaviorEngine` subscribes to `AudioInputStarted`, `IntentRecognized`, `ResponseDrafted`, `RobotModeChanged`
- No Reachy SDK imports are permitted outside `adapters/reachy.py`
- All motion keyframes for FakeRobot are simulated (logged, not physically executed)
