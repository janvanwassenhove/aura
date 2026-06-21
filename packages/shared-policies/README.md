# shared-policies

## Purpose

Defines the approval and access control rules that the orchestrator enforces.

- `APPROVAL_REQUIRED` — set of tool names requiring explicit user approval before execution
- `MODE_TOOL_MAP` — which tools are available in each persona/mode
- `Policy` — Pydantic model combining approval rules and mode access control

## Contents

```python
from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP, Policy

# Check if a tool needs approval
if tool_name in APPROVAL_REQUIRED:
    # emit ApprovalRequested event

# Check if a tool is available in current mode
if tool_name in MODE_TOOL_MAP[current_persona]:
    # allow the call
```

## Approval-Required Tools (initial set)

- `send_mail`
- `post_teams_message`
- `create_calendar_event`
- `delete_calendar_event`
- `create_task`
- `delete_task`

## Mode Tool Map

| Mode | Available Tool Categories |
|------|--------------------------|
| `work` | M365 Calendar, M365 Mail, M365 Teams, M365 Planner, memory |
| `home` | memory, reminders, todos (no M365 write) |
| `presentation` | speak, motion, presentation control only |
| `silent_desk` | text-only responses; no audio, no motion |
| `demo` | all tools (demonstration mode) |

## Tests

```bash
uv run pytest tests/
```
