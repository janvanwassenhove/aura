# shared-events

## Purpose

Provides the asyncio in-process event bus and WebSocket broadcaster used by all AURA services.

- `AsyncEventBus` — pub/sub bus using `asyncio.create_task` for non-blocking dispatch
- `WebSocketBroadcaster` — accepts FastAPI WebSocket connections; fan-out of all published events as JSON

## Usage

```python
from shared_events import AsyncEventBus
from shared_schemas.events.robot import RobotConnected

bus = AsyncEventBus()

# Subscribe
async def on_connected(event: RobotConnected):
    print(f"Robot connected: {event.session_id}")

bus.subscribe(RobotConnected, on_connected)

# Publish
await bus.publish(RobotConnected(session_id="session-1"))

# Unsubscribe
bus.unsubscribe(RobotConnected, on_connected)
```

## WebSocket Broadcaster

```python
from shared_events import WebSocketBroadcaster

broadcaster = WebSocketBroadcaster(bus)

# In FastAPI route
@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await broadcaster.connect(websocket)
    try:
        await websocket.receive_text()  # keep alive
    finally:
        broadcaster.disconnect(websocket)
```

## Behavior

- Slow subscribers do NOT block publishers — each handler is dispatched via `asyncio.create_task`
- Subscriber exceptions are logged but do not crash the bus or affect other subscribers
- Publishing before `bus.start()` raises `EventBusNotStartedError`

## Future

Redis Streams upgrade path is documented in [ADR-002](../../docs/adr/ADR-002-event-model.md). The `AsyncEventBus` interface can be swapped for a Redis implementation without changing service code.

## Tests

```bash
uv run pytest tests/
```
