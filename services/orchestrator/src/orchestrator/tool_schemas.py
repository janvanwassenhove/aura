"""OpenAI function-calling schemas for orchestrator tools.

The orchestrator advertises these to the LLM via the ``tools=`` parameter so the
model can emit real ``tool_calls``. Without this, the LLM is never told the tools
exist and the connector execution path is unreachable.

Each schema maps 1:1 to an entry in ``pipeline._TOOL_ROUTES``. Keep them in sync.
Tools without a schema here (e.g. presentation ``speak``/``execute_motion``) are
handled elsewhere and are simply not advertised to the connector LLM.
"""

from __future__ import annotations

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}


def _fn(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description, "parameters": parameters,
    }}


# Tool name → OpenAI function schema.
TOOL_SCHEMAS: dict[str, dict] = {
    "list_calendar_events_today": _fn(
        "list_calendar_events_today", "List the user's calendar events for today.", _NO_ARGS,
    ),
    "create_calendar_event": _fn(
        "create_calendar_event", "Create a calendar event.",
        {"type": "object", "properties": {
            "subject": {"type": "string", "description": "Event title."},
            "start": {"type": "string", "description": "ISO-8601 start datetime."},
            "end": {"type": "string", "description": "ISO-8601 end datetime."},
            "attendees": {"type": "array", "items": {"type": "string"},
                          "description": "Attendee email addresses."},
        }, "required": ["subject", "start", "end"]},
    ),
    "delete_calendar_event": _fn(
        "delete_calendar_event", "Delete a calendar event by id.",
        {"type": "object", "properties": {
            "id": {"type": "string", "description": "Event id to delete."},
        }, "required": ["id"]},
    ),
    "get_unread_mail": _fn(
        "get_unread_mail", "Get the user's unread mail.", _NO_ARGS,
    ),
    "send_mail": _fn(
        "send_mail", "Send an email. Sensitive — requires user approval.",
        {"type": "object", "properties": {
            "to": {"type": "string", "description": "Recipient email."},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        }, "required": ["to", "subject", "body"]},
    ),
    "post_teams_message": _fn(
        "post_teams_message", "Post a Teams message. Sensitive — requires approval.",
        {"type": "object", "properties": {
            "channel": {"type": "string"},
            "message": {"type": "string"},
        }, "required": ["channel", "message"]},
    ),
    "list_tasks": _fn("list_tasks", "List the user's Planner tasks.", _NO_ARGS),
    "create_task": _fn(
        "create_task", "Create a Planner task. Sensitive — requires approval.",
        {"type": "object", "properties": {
            "title": {"type": "string"},
            "due": {"type": "string", "description": "ISO-8601 due date (optional)."},
        }, "required": ["title"]},
    ),
    "delete_task": _fn(
        "delete_task", "Delete a Planner task by id. Sensitive — requires approval.",
        {"type": "object", "properties": {
            "id": {"type": "string"},
        }, "required": ["id"]},
    ),
    "list_todos": _fn("list_todos", "List the user's personal todos.", _NO_ARGS),
    "create_todo": _fn(
        "create_todo", "Create a personal todo.",
        {"type": "object", "properties": {
            "text": {"type": "string"},
        }, "required": ["text"]},
    ),
    "complete_todo": _fn(
        "complete_todo", "Mark a todo complete by id.",
        {"type": "object", "properties": {
            "id": {"type": "string"},
        }, "required": ["id"]},
    ),
    "list_reminders": _fn("list_reminders", "List the user's reminders.", _NO_ARGS),
    "create_reminder": _fn(
        "create_reminder", "Create a reminder.",
        {"type": "object", "properties": {
            "text": {"type": "string"},
            "due_at": {"type": "string", "description": "ISO-8601 due datetime."},
        }, "required": ["text", "due_at"]},
    ),
}


def build_tool_specs(allowed_tools: frozenset[str]) -> list[dict]:
    """Return OpenAI function schemas for the allowed tools that have one.

    Order is stable (sorted) for deterministic prompts/tests.
    """
    return [TOOL_SCHEMAS[name] for name in sorted(allowed_tools) if name in TOOL_SCHEMAS]
