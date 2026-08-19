"""Mode policy — what each mode allows, asks about, and blocks. (D2 redesign)

`MODE_TOOL_MAP` has governed which tools a mode exposes since U58, and
`APPROVAL_REQUIRED` has named the tools that stop for the owner — but neither
was ever *visible*: the console showed mode as a 9px tinted dot, and nothing in
it could change a boundary. This module is the missing middle layer:

  * it groups the ~40 raw tool names into the eight capability groups a human
    thinks in (mail, music, screen control, …),
  * it derives each group's state per mode — ``allows`` / ``asks`` /
    ``blocked``, the exact three words the UI and the docs use — from the real
    policy, never from a hand-written table,
  * and it holds the owner's overrides, persisted to a small JSON file, so the
    Modes editor can change a row and have it take effect immediately.

Vocabulary is deliberate and fixed: **allows** runs without asking, **asks**
stops for approval every time, **blocked** is refused even if asked. One word
per concept, identical in the UI, these config keys, and the docs.

Overrides change real enforcement:
  * a group set to ``blocked`` removes its tools from the mode's allowed set,
  * a group set to ``allows``/``asks`` adds them,
  * ``asks`` routes every tool in the group through the approval gate;
    ``allows`` lets the group run without it. Setting a group that contains
    baseline-gated tools (send_mail, run_powershell) to ``allows`` is
    therefore an explicit owner decision to drop that gate for that mode —
    which is the point of the editor, and why only the owner sees it.

Tools that belong to no group (save_skill, request_capability, …) keep their
baseline behaviour and can never be loosened from here.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP

logger = logging.getLogger(__name__)

ALLOWS = "allows"
ASKS = "asks"
BLOCKED = "blocked"
STATES = (ALLOWS, ASKS, BLOCKED)

# The modes the console shows. silent_desk and demo stay reachable through the
# API but are not part of the three-way header switch.
UI_MODES = ("home", "work", "presentation")

# ── The eight capability groups ────────────────────────────────────────────
# (id, label, detail, tools). Conversation has no tools: talking is the turn
# itself, not a tool call — it exists so the chip row can say so.
TOOL_GROUPS: list[tuple[str, str, str, frozenset[str]]] = [
    ("conversation", "Conversation", "talking, answering, remembering", frozenset()),
    ("calendar", "Calendar", "read your agenda, add and move events", frozenset({
        "list_calendar_events_today", "create_calendar_event", "delete_calendar_event",
    })),
    ("mail", "Mail", "read, draft and send on your behalf", frozenset({
        "get_unread_mail", "send_mail", "post_teams_message",
    })),
    ("music", "Music", "play and control speakers by room", frozenset({
        "play_music", "pause_music", "next_track", "list_music_playlists",
        "list_speakers", "media_control",
    })),
    ("reminders", "Reminders", "todos, tasks and spoken reminders", frozenset({
        "list_reminders", "create_reminder", "list_todos", "create_todo",
        "complete_todo", "list_tasks", "create_task", "delete_task",
    })),
    # delegate_subtask is deliberately NOT here: it is a read-only research
    # subagent that home mode also carries, and grouping it under dev tools
    # made the home chip read "dev tools · allows" for a mode with no dev
    # tools at all. Ungrouped, it keeps its baseline behaviour.
    ("dev tools", "Dev tools", "repos, CI, releases, the shell", frozenset({
        "run_dev_task", "run_powershell", "read_file", "write_file",
        "git_prepare", "open_in_vscode",
    })),
    ("screen control", "Screen control", "drive the desktop like a user", frozenset({
        "use_computer", "launch_app", "open_browser_url", "list_browser_tabs",
    })),
    ("slides", "Slides", "advance and react to a presentation", frozenset({
        "speak", "execute_motion", "load_presentation", "advance_slide",
    })),
]

_GROUP_BY_ID = {gid: (label, detail, tools) for gid, label, detail, tools in TOOL_GROUPS}
_GROUP_OF_TOOL: dict[str, str] = {
    tool: gid for gid, _l, _d, tools in TOOL_GROUPS for tool in tools
}


def _store_path() -> Path:
    return Path(os.environ.get("MODE_POLICY_PATH", "./data/mode-policy.json"))


# ── Persistence ────────────────────────────────────────────────────────────

_cache: dict | None = None
_cache_path: Path | None = None


def _load() -> dict:
    """The stored policy file: {"overrides": {mode: {group: state}},
    "behaviour": {mode: {...}}}. Missing or unreadable → empty."""
    global _cache, _cache_path
    path = _store_path()
    if _cache is not None and _cache_path == path:
        return _cache
    data: dict = {"overrides": {}, "behaviour": {}}
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data["overrides"] = raw.get("overrides") or {}
                data["behaviour"] = raw.get("behaviour") or {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("mode policy file unreadable (%s) — using defaults", exc)
    _cache, _cache_path = data, path
    return data


def _save(data: dict) -> None:
    global _cache
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:  # policy still applies for this session
        logger.warning("mode policy not persisted: %s", exc)
    _cache = data


def reset_cache_for_tests() -> None:
    global _cache, _cache_path, _live_domains
    _cache, _cache_path = None, None
    # U254: connector availability is process-wide too, so a test that made a
    # domain dead would otherwise leak into every test after it.
    _live_domains = None


# ── Derivation ─────────────────────────────────────────────────────────────

def default_state(mode: str, group_id: str) -> str:
    """The state the real policy implies, before any override.

    No tool of the group in the mode's set → blocked. Any in-mode tool that
    stops at the approval gate → the group asks. Otherwise it allows.
    """
    _label, _detail, tools = _GROUP_BY_ID[group_id]
    if not tools:  # conversation — the turn itself
        return ALLOWS
    in_mode = tools & MODE_TOOL_MAP.get(mode, frozenset())
    if not in_mode:
        return BLOCKED
    if in_mode & APPROVAL_REQUIRED:
        return ASKS
    return ALLOWS


def group_state(mode: str, group_id: str) -> tuple[str, str]:
    """(state, source) — source is 'override' when the owner changed it."""
    override = (_load()["overrides"].get(mode) or {}).get(group_id)
    if override in STATES:
        return override, "override"
    return default_state(mode, group_id), "default"


def set_group_state(mode: str, group_id: str, state: str) -> tuple[str, str]:
    """Owner edit from the Modes view.

    An explicit choice always sticks, even when it matches the derived
    summary: a derived ``asks`` means "part of this group asks" (the baseline
    gate), while an owner-set ``asks`` gates the whole group. ``default``
    clears the override and returns the row to the derived policy.
    """
    if mode not in MODE_TOOL_MAP:
        raise ValueError(f"Unknown mode: {mode!r}")
    if group_id not in _GROUP_BY_ID:
        raise ValueError(f"Unknown tool group: {group_id!r}")
    if state not in (*STATES, "default"):
        raise ValueError(f"State must be one of {(*STATES, 'default')}, not {state!r}")
    if group_id == "conversation":
        raise ValueError("Conversation is not a tool — it cannot be bounded here")
    data = _load()
    per_mode = dict(data["overrides"].get(mode) or {})
    if state == "default":
        per_mode.pop(group_id, None)
    else:
        per_mode[group_id] = state
    overrides = dict(data["overrides"])
    if per_mode:
        overrides[mode] = per_mode
    else:
        overrides.pop(mode, None)
    _save({**data, "overrides": overrides})
    return group_state(mode, group_id)


# ── Enforcement ────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# U254: what a LIVE CONNECTION changes about what he can do
# ---------------------------------------------------------------------------
#
# Tools that cannot work without a connector behind them, by the domain that
# connector serves. Todos and reminders are deliberately absent: those are
# memory-service, local to this laptop, and gating them on a Microsoft account
# would break the one part that works with no account at all.
#
# The point is honesty in both directions. With no mail connector, offering
# get_unread_mail means the assistant promises to read mail and then explains
# a 503 — U248's lesson, one layer down. And switching Google ON has to change
# what he can do in the same breath, or "connected" is just a green badge.
_CONNECTOR_TOOLS: dict[str, frozenset[str]] = {
    "mail": frozenset({"get_unread_mail", "send_mail"}),
    "calendar": frozenset({
        "list_calendar_events_today", "create_calendar_event", "delete_calendar_event",
    }),
    "chat": frozenset({"post_teams_message"}),
    "tasks": frozenset({"list_tasks", "create_task", "delete_task"}),
    "files": frozenset({"list_onedrive_files"}),
}

# None means NOT KNOWN — and then nothing is filtered. Only the brain, which
# owns both halves, can say; every other caller (tests, a bare orchestrator,
# an older deployment) keeps the previous behaviour exactly. Same rule as the
# derived mode states: a layer that is unsure must not take capabilities away.
_live_domains: set[str] | None = None


def set_live_domains(domains: set[str] | None) -> None:
    """Tell the policy which connector domains can actually answer right now."""
    global _live_domains
    _live_domains = None if domains is None else set(domains)


def live_domains() -> set[str] | None:
    return None if _live_domains is None else set(_live_domains)


def _tools_without_a_connector() -> frozenset[str]:
    """Connector-backed tools whose domain has nothing live behind it."""
    if _live_domains is None:
        return frozenset()
    dead: set[str] = set()
    for domain, tools in _CONNECTOR_TOOLS.items():
        if domain not in _live_domains:
            dead |= tools
    return frozenset(dead)


def allowed_tools(mode: str) -> frozenset[str]:
    """The mode's tool set with the owner's overrides applied."""
    base = set(MODE_TOOL_MAP.get(mode, frozenset()))
    overrides = _load()["overrides"].get(mode) or {}
    for group_id, state in overrides.items():
        entry = _GROUP_BY_ID.get(group_id)
        if entry is None or state not in STATES:
            continue
        tools = entry[2]
        if state == BLOCKED:
            base -= tools
        else:  # allows / asks — the group is available either way
            base |= tools
    # U254: last word — a mode may allow mail, but with no mail account there
    # is nothing to allow. Subtracted AFTER the overrides so an owner cannot
    # accidentally re-enable a tool that has nothing behind it.
    return frozenset(base - _tools_without_a_connector())


def requires_approval(tool_name: str, mode: str) -> bool:
    """Mode-aware approval.

    A DERIVED state is a summary of the baseline policy, so it must not change
    behaviour: a group that reads as ``asks`` because send_mail asks does not
    suddenly gate get_unread_mail. Only an explicit owner OVERRIDE has teeth —
    ``asks`` routes every tool in the group through the gate, ``allows`` runs
    the group without it. Ungrouped tools keep the APPROVAL_REQUIRED baseline
    and can never be loosened from here.
    """
    group_id = _GROUP_OF_TOOL.get(tool_name)
    if group_id is None:
        return tool_name in APPROVAL_REQUIRED
    state, source = group_state(mode, group_id)
    if source == "override":
        if state == ASKS:
            return True
        if state == ALLOWS:
            return False
    return tool_name in APPROVAL_REQUIRED  # default, or blocked (never reached)


def rule_for(tool_name: str, mode: str) -> str:
    """The sentence an approval card shows: which rule caused this ask.
    Never render a rule with no route to its source."""
    group_id = _GROUP_OF_TOOL.get(tool_name)
    mode_label = "Present" if mode == "presentation" else mode.replace("_", " ").capitalize()
    if group_id is None:
        return f"{tool_name} always asks first, in every mode."
    state, source = group_state(mode, group_id)
    label = _GROUP_BY_ID[group_id][0]
    if state == ASKS:
        who = "You set" if source == "override" else f"{mode_label} mode sets"
        return f"{who} {label.lower()} to asks — every use needs your approval."
    if state == BLOCKED:
        return f"{mode_label} mode blocks {label.lower()} entirely."
    return f"{mode_label} mode allows {label.lower()} without asking."


# ── Per-mode behaviour (persona, voice, memory writing) ────────────────────

_BEHAVIOUR_DEFAULTS = {
    "home": {"persona": "home", "voice": "",
             "speaks_first": "yes", "memory_writing": "on"},
    "work": {"persona": "work", "voice": "",
             "speaks_first": "only for reminders", "memory_writing": "on"},
    "presentation": {"persona": "presentation", "voice": "",
                     "speaks_first": "never — cues only", "memory_writing": "off"},
}

_BEHAVIOUR_KEYS = frozenset({"persona", "voice", "speaks_first", "memory_writing"})


def behaviour(mode: str) -> dict:
    stored = _load()["behaviour"].get(mode) or {}
    fallback = {"persona": mode, "voice": "", "speaks_first": "yes", "memory_writing": "on"}
    base = dict(_BEHAVIOUR_DEFAULTS.get(mode, fallback))
    base.update({k: v for k, v in stored.items() if k in _BEHAVIOUR_KEYS})
    if not base.get("voice"):
        # The pre-D2 home of this setting; still honoured so nothing regresses.
        base["voice"] = os.environ.get(f"TTS_VOICE_{mode.upper()}", "") or os.environ.get("TTS_VOICE", "alloy")
    return base


def set_behaviour(mode: str, updates: dict) -> dict:
    if mode not in MODE_TOOL_MAP:
        raise ValueError(f"Unknown mode: {mode!r}")
    clean = {k: str(v) for k, v in (updates or {}).items() if k in _BEHAVIOUR_KEYS}
    data = _load()
    merged = {**(data["behaviour"].get(mode) or {}), **clean}
    _save({**data, "behaviour": {**data["behaviour"], mode: merged}})
    # Voice resolution (aura_brain.voice.resolve_voice) reads the env — keep it
    # true for the running process so the change is live immediately.
    if clean.get("voice"):
        os.environ[f"TTS_VOICE_{mode.upper()}"] = clean["voice"]
    return behaviour(mode)


def apply_stored_voices() -> None:
    """On boot: re-export stored per-mode voices into the env the TTS layer
    reads, so the JSON file — not the env — is the source of truth."""
    for mode in MODE_TOOL_MAP:
        voice = (_load()["behaviour"].get(mode) or {}).get("voice", "")
        if voice:
            os.environ[f"TTS_VOICE_{mode.upper()}"] = str(voice)


# ── The full picture, for the console ──────────────────────────────────────

def describe(active_mode: str) -> dict:
    """Everything the chip row and the Modes editor render, derived live."""
    modes: dict[str, dict] = {}
    for mode in UI_MODES:
        groups = []
        dead = _tools_without_a_connector()
        for gid, label, detail, tools in TOOL_GROUPS:
            state, source = group_state(mode, gid)
            # U254: a group whose tools all need an account that is not
            # connected is not "allowed" in any useful sense. The chip says so
            # rather than promising something the first question would expose.
            unreachable = bool(tools) and tools <= dead
            groups.append({
                "id": gid, "label": label, "detail": detail,
                "state": state, "source": source,
                "tools": sorted(tools),
                "unreachable": unreachable,
            })
        modes[mode] = {"groups": groups, "behaviour": behaviour(mode)}
    return {
        "active_mode": active_mode, "states": list(STATES), "modes": modes,
        # None means "not known" — the console then says nothing about
        # reachability rather than guessing (same rule as the gate itself).
        "live_domains": None if _live_domains is None else sorted(_live_domains),
    }
