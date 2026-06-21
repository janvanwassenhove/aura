# operator-console

**Port**: 5173 (Vite dev server)  
**Spec**: [008-operator-console](../../.specify/specs/008-operator-console/spec.md)

## Purpose

Vue 3 monitoring and control console for AURA. Provides real-time visibility into robot state, conversation transcripts, system events, and approval requests.

## Features

- **Robot State Panel** — current mode (ONLINE/DEGRADED/OFFLINE), behavior state, motion log
- **Conversation Panel** — full transcript with user/AURA turns, streaming response display
- **Event Log** — all bus events with type, timestamp, and filterable by event type
- **Approval Panel** — modal for approving/denying sensitive tool calls (send mail, post Teams message)
- **Text Input** — submit text turns directly without voice

## Tech Stack

- Vue 3 + Composition API
- Vite + TypeScript
- Pinia (state management)
- TailwindCSS
- WebSocket composable for real-time event streaming

## Running Locally

```bash
cd apps/operator-console
npm install
npm run dev
```

Open `http://localhost:5173`.

The console connects to:
- `http://localhost:8003` (orchestrator REST)
- `ws://localhost:8001/ws/events` (robot-runtime events)
- `ws://localhost:8003/ws/events` (orchestrator events)

## Building for Production

```bash
npm run build
# Output in dist/ — serve as static files
```

## Pinia Stores

| Store | State |
|-------|-------|
| `robotStore` | mode, behavior_state, motion_log, speak_active |
| `conversationStore` | session_id, turns, streaming_text |
| `eventStore` | events[], filter |
| `approvalStore` | pending_approvals[] |

## Environment Variables

```
VITE_ORCHESTRATOR_URL=http://localhost:8003
VITE_ROBOT_RUNTIME_WS=ws://localhost:8001/ws/events
VITE_ORCHESTRATOR_WS=ws://localhost:8003/ws/events
```

## Tests

```bash
npm run test:unit
```
