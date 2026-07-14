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
    "list_onedrive_files": _fn(
        "list_onedrive_files",
        "List the user's recent OneDrive files (name, folder, size, modified).",
        _NO_ARGS,
    ),
    "play_music": _fn(
        "play_music",
        "Play music on Spotify, optionally on a specific speaker (e.g. the "
        "Sonos). Give a song/artist as 'query', a 'playlist' name, or set "
        "'favorites' to play liked songs. Omit all to resume playback.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Song or artist to play."},
            "playlist": {"type": "string", "description": "Playlist name to play."},
            "favorites": {"type": "boolean", "description": "Play the user's liked songs."},
            "device": {"type": "string", "description": "Speaker name, e.g. 'Sonos'. Defaults to the Sonos."},
        }, "additionalProperties": False},
    ),
    "media_control": _fn(
        "media_control",
        "Control the media player running on the owner's laptop (the real "
        "Spotify/browser app) via the keyboard media keys. Use this to "
        "play/pause/skip whatever app is playing — no account needed. "
        "Pair with launch_app('spotify') to open Spotify first.",
        {"type": "object", "properties": {
            "action": {"type": "string",
                       "enum": ["play_pause", "next", "previous", "stop",
                                "volume_up", "volume_down", "mute"]},
        }, "required": ["action"], "additionalProperties": False},
    ),
    "pause_music": _fn("pause_music", "Pause music playback.", _NO_ARGS),
    "next_track": _fn("next_track", "Skip to the next track.", _NO_ARGS),
    "list_music_playlists": _fn("list_music_playlists", "List the user's Spotify playlists.", _NO_ARGS),
    "list_speakers": _fn("list_speakers", "List available Spotify/Sonos speakers.", _NO_ARGS),
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
    "launch_app": _fn(
        "launch_app",
        "Launch an allow-listed desktop app on the owner's laptop by its "
        "registered name (e.g. 'vscode', 'spotify'). Only pre-approved apps "
        "can be started, and each launch asks the owner for approval.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Registered app name."},
        }, "required": ["name"], "additionalProperties": False},
    ),
    "open_in_vscode": _fn(
        "open_in_vscode",
        "Open a file (optionally at a line) or a folder in VS Code on the "
        "owner's laptop. Use to SHOW code you are discussing.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File or folder path."},
            "line": {"type": "integer", "description": "1-based line number (optional)."},
        }, "required": ["path"], "additionalProperties": False},
    ),
    "delegate_subtask": _fn(
        "delegate_subtask",
        "Delegate a focused, self-contained subtask to a SUBAGENT with a "
        "restricted read-only toolset and its own small round budget. Use for "
        "gathering/verifying information (read files, git status, tab lists, "
        "calendar/mail/task lookups) while you keep the main thread. The "
        "subagent cannot write, launch apps, or delegate further.",
        {"type": "object", "properties": {
            "goal": {"type": "string", "description": "Concrete, self-contained subtask."},
            "max_rounds": {"type": "integer", "description": "Subagent round budget (default 4, max 6)."},
        }, "required": ["goal"], "additionalProperties": False},
    ),
    "save_skill": _fn(
        "save_skill",
        "SELF-TRAINING: save or update a skill — a procedure the owner taught "
        "you (from feedback, corrections, or a demonstrated way of working). "
        "Sensitive — the owner approves every skill write and sees exactly "
        "what you want to store. Scope to a person when it's THEIR way of "
        "working (digital twin); add triggers so it activates at the right time.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "kebab-case id, e.g. 'deploy-flow'."},
            "description": {"type": "string", "description": "One line: what this skill covers."},
            "body": {"type": "string", "description": "The procedure, step by step."},
            "triggers": {"type": "array", "items": {"type": "string"},
                         "description": "Substrings of requests where this applies."},
            "personas": {"type": "array", "items": {"type": "string"},
                         "description": "Limit to modes (work/home/presentation)."},
            "person": {"type": "string", "description": "Person id when it's one person's way of working."},
        }, "required": ["name", "description", "body"], "additionalProperties": False},
    ),
    "run_powershell": _fn(
        "run_powershell",
        "Run one PowerShell command on the owner's laptop (CLI layer). "
        "Sensitive — requires owner approval per command. Prefer a dedicated "
        "tool/API when one exists; prefer this over file writes or GUI control.",
        {"type": "object", "properties": {
            "command": {"type": "string", "description": "The PowerShell command."},
            "working_dir": {"type": "string", "description": "Directory to run in (optional)."},
        }, "required": ["command"], "additionalProperties": False},
    ),
    "read_file": _fn(
        "read_file",
        "Read a text file on the owner's laptop (file-system layer, read-only, "
        "restricted to allowed roots). Free to use for analysis.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to read."},
        }, "required": ["path"], "additionalProperties": False},
    ),
    "write_file": _fn(
        "write_file",
        "Write/overwrite a text file on the owner's laptop (file-system layer, "
        "restricted to allowed roots). Sensitive — requires owner approval.",
        {"type": "object", "properties": {
            "path": {"type": "string", "description": "File path to write."},
            "content": {"type": "string", "description": "Full new file content."},
        }, "required": ["path", "content"], "additionalProperties": False},
    ),
    "git_prepare": _fn(
        "git_prepare",
        "Read-only git inspection to PREPARE actions: status, diff, diff_staged, "
        "log. Committing/pushing goes through run_dev_task (approval-tiered).",
        {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["status", "diff", "diff_staged", "log"]},
            "working_dir": {"type": "string", "description": "Repo directory (optional)."},
        }, "required": ["action"], "additionalProperties": False},
    ),
    "list_browser_tabs": _fn(
        "list_browser_tabs",
        "List the open tabs (title + url) in the owner's Chrome browser. "
        "Read-only. Chrome must run with --remote-debugging-port=9222.",
        _NO_ARGS,
    ),
    "open_browser_url": _fn(
        "open_browser_url",
        "Open a URL in a new Chrome tab on the owner's laptop. Sensitive — "
        "navigating the owner's browser requires approval.",
        {"type": "object", "properties": {
            "url": {"type": "string", "description": "http(s) URL to open."},
        }, "required": ["url"], "additionalProperties": False},
    ),
    "use_computer": _fn(
        "use_computer",
        (
            "Take screenshot + mouse/keyboard control of the owner's laptop to "
            "operate ANY desktop app when launch_app/media_control aren't enough "
            "(e.g. clicking around inside an app's UI). Sensitive and slow — "
            "requires owner approval and must be OFF by default. Describe the "
            "concrete goal to accomplish on screen as 'goal'. Never used to enter "
            "passwords, payment details, or accept terms."
        ),
        {"type": "object", "properties": {
            "goal": {"type": "string",
                     "description": "Concrete on-screen goal, e.g. 'in Spotify, "
                                    "click Play on the Discover Weekly playlist'."},
        }, "required": ["goal"], "additionalProperties": False},
    ),
    "run_dev_task": _fn(
        "run_dev_task",
        (
            "Run a development task: execute a shell command (read/grep/test) or "
            "invoke Claude Code CLI for complex coding work. "
            "Write/edit/commit/push operations require owner approval. "
            "Provide 'task' as a concrete shell command (e.g. 'uv run pytest tests/') "
            "for shell operations, or a natural-language description when using Claude Code."
        ),
        {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Shell command or natural-language task description. "
                        "For shell backend: must be a valid shell command. "
                        "For claude backend: natural language is fine."
                    ),
                },
                "working_dir": {
                    "type": "string",
                    "description": "Directory to run in. Defaults to the brain's cwd.",
                },
                "operation_type": {
                    "type": "string",
                    "enum": ["read", "write", "commit", "push", "complex"],
                    "description": (
                        "Hint for the approval tier. Auto-classified from 'task' if omitted. "
                        "Use 'read' for safe reads/tests, 'write' for file edits, "
                        "'commit'/'push' for git operations, 'complex' for multi-step coding."
                    ),
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    ),
}


# U58: automation-ladder layer per tool. The agent must always use the most
# reliable layer available: api → cli → fs → browser → gui. GUI (Computer Use)
# is the emergency exit, not the front door. Unlisted tools default to "api".
TOOL_LAYERS: dict[str, str] = {
    "run_dev_task": "cli",
    "run_powershell": "cli",
    "open_in_vscode": "cli",
    "launch_app": "cli",
    "media_control": "cli",
    "read_file": "fs",
    "write_file": "fs",
    "git_prepare": "cli",
    "list_browser_tabs": "browser",
    "open_browser_url": "browser",
    "use_computer": "gui",
}

LADDER_NOTE = (
    "AUTOMATION LADDER — always pick the MOST RELIABLE layer that can do the "
    "job: 1) api (connectors like calendar/mail/music), 2) cli (run_dev_task, "
    "run_powershell, git_prepare, launch_app), 3) fs (read_file/write_file), "
    "4) browser (list_browser_tabs/open_browser_url), 5) gui (use_computer — "
    "the emergency exit, ONLY when no lower layer can possibly do it, and say "
    "why). Escalate one step at a time; never start at the GUI. "
    "MUSIC: you CAN open Spotify (launch_app 'spotify') and press play "
    "(media_control) — never claim you can't open apps. When asked to play "
    "music, ACT (launch + play) instead of asking which exact track; then "
    "report honestly what you could not control (a specific song/playlist/"
    "speaker needs the Spotify connection in Settings)."
)


def build_tool_specs(allowed_tools: frozenset[str]) -> list[dict]:
    """Return OpenAI function schemas for the allowed tools that have one.

    Order is stable (sorted) for deterministic prompts/tests.
    """
    return [TOOL_SCHEMAS[name] for name in sorted(allowed_tools) if name in TOOL_SCHEMAS]
