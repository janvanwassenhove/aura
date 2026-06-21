"""Approval and access control policies for AURA."""

from __future__ import annotations

# Tools that require explicit user approval before execution.
# The orchestrator's ApprovalManager checks this set before calling any tool.
APPROVAL_REQUIRED: frozenset[str] = frozenset(
    {
        "send_mail",
        "post_teams_message",
        "create_calendar_event",
        "delete_calendar_event",
        "create_task",
        "delete_task",
    }
)

# Personas / modes and the tool names available within each.
# The orchestrator's ContextBuilder filters tool schemas to this list.
MODE_TOOL_MAP: dict[str, frozenset[str]] = {
    "work": frozenset(
        {
            "list_calendar_events_today",
            "create_calendar_event",
            "delete_calendar_event",
            "get_unread_mail",
            "send_mail",
            "post_teams_message",
            "list_tasks",
            "create_task",
            "delete_task",
            "list_todos",
            "create_todo",
            "complete_todo",
            "list_reminders",
            "create_reminder",
        }
    ),
    "home": frozenset(
        {
            "list_todos",
            "create_todo",
            "complete_todo",
            "list_reminders",
            "create_reminder",
        }
    ),
    "presentation": frozenset(
        {
            "speak",
            "execute_motion",
            "load_presentation",
            "advance_slide",
        }
    ),
    "silent_desk": frozenset(
        {
            "list_todos",
            "create_todo",
            "complete_todo",
        }
    ),
    "demo": frozenset(
        {
            "list_calendar_events_today",
            "get_unread_mail",
            "send_mail",
            "post_teams_message",
            "list_tasks",
            "create_task",
            "list_todos",
            "create_todo",
            "complete_todo",
            "list_reminders",
            "create_reminder",
            "speak",
            "execute_motion",
        }
    ),
}
