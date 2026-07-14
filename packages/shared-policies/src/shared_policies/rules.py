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
        "launch_app",  # starting an app on the laptop always asks the owner
        "use_computer",  # screenshot + mouse/keyboard control always asks the owner
    }
)

# Personas / modes and the tool names available within each.
# The orchestrator's ContextBuilder filters tool schemas to this list.
MODE_TOOL_MAP: dict[str, frozenset[str]] = {
    "work": frozenset(
        {
            "run_dev_task",
            "use_computer",
            "open_in_vscode",
            "launch_app",
            "list_calendar_events_today",
            "create_calendar_event",
            "delete_calendar_event",
            "get_unread_mail",
            "list_onedrive_files",
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
            "play_music",
            "pause_music",
            "next_track",
            "list_music_playlists",
            "list_speakers",
            "media_control",
            "launch_app",
        }
    ),
    "home": frozenset(
        {
            "list_todos",
            "create_todo",
            "complete_todo",
            "list_reminders",
            "create_reminder",
            "play_music",
            "pause_music",
            "next_track",
            "list_music_playlists",
            "list_speakers",
            "media_control",
            "launch_app",
            "use_computer",
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
            "run_dev_task",
            "list_calendar_events_today",
            "get_unread_mail",
            "list_onedrive_files",
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
