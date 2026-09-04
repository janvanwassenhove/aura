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
        "open_browser_url",  # navigating the owner's browser always asks
        "run_powershell",  # arbitrary shell — always asks, per command
        "write_file",  # writing to disk always asks
        "save_skill",  # self-training: every skill write is owner-approved
        # U249: asking to be UNBLOCKED is the one request that can change the
        # assistant's own boundaries, so it is gated hardest of all. The value
        # is never model-supplied (see orchestrator/unblocks.py) — the owner is
        # approving a named entry from a fixed catalogue.
        "request_capability",
    }
)

# Personas / modes and the tool names available within each.
# The orchestrator's ContextBuilder filters tool schemas to this list.
# U249: `request_capability` is added to EVERY mode below. Asking to be
# unblocked is not itself a capability — it opens an approval card the owner
# reads. A mode that cannot ask is a mode that goes quiet when it hits a wall,
# which is the behaviour this was built to end.
MODE_TOOL_MAP: dict[str, frozenset[str]] = {
    "work": frozenset(
        {
            "run_dev_task",
            "use_computer",
            "open_in_vscode",
            "run_powershell",
            "read_file",
            "write_file",
            "git_prepare",
            "save_skill",
            "delegate_subtask",
            "list_browser_tabs",
            "open_browser_url",
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
            "list_browser_tabs",
            "open_browser_url",
            "save_skill",
            "delegate_subtask",
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

# Every mode may ask to be unblocked — see the note above MODE_TOOL_MAP. Done
# here rather than by repeating the name five times, so a mode added later
# cannot forget it.
#
# U259: looking things up belongs in the same category. The owner asked for
# search to work "zoals claude chat" — always, not as a capability you first
# have to remember to switch on. Presentation included: a talk is exactly where
# being unable to check a fact is most embarrassing. WHETHER it stops to ask is
# a separate question, answered per mode in mode_policy (work asks).
# U294: and so does knowing WHO is being talked about. Looking a
# housemate up in his own notes is not a capability anyone should have
# to switch on first — it reads the owner's own data, through the
# judgment layer, which is what decides per person what may be said at
# all. Presentation included: being introduced to someone you already
# know is exactly the moment not to draw a blank.
_ALWAYS = {"request_capability", "web_search", "read_url", "look_up_person"}

MODE_TOOL_MAP = {
    mode: tools | _ALWAYS for mode, tools in MODE_TOOL_MAP.items()
}
