"""U61: declarative tool hooks — deterministic guardrails inside the loop.

Hooks are JSON, from the ``AGENT_HOOKS`` env var or ``AGENT_HOOKS_FILE``
(default ``./hooks.json``), one object per hook:

    [
      {"when": "pre",  "tool": "run_dev_task", "arg_match": "git push",
       "action": "block", "message": "Run the test suite first."},
      {"when": "post", "tool": "write_file",
       "action": "note",  "message": "Run the linter on the changed file."}
    ]

Semantics:
  - ``pre`` + ``block``: the call is NOT executed; the message is returned as
    the tool result, so the model reads why and adapts in the next round.
  - ``post`` + ``note``: the message is appended to the tool result.
  - ``arg_match``: substring of the serialized arguments (omit → every call).

Hooks are deterministic policy, not model behavior — a hook fires every time,
regardless of what the model 'wants'. They complement (never replace) the
approval gate.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Hook:
    when: str            # "pre" | "post"
    tool: str            # tool name it applies to
    action: str          # pre: "block" · post: "note"
    message: str
    arg_match: str = ""  # substring of serialized args; "" → always

    def applies(self, tool_name: str, args_serialized: str) -> bool:
        if self.tool != tool_name:
            return False
        return self.arg_match.lower() in args_serialized.lower() if self.arg_match else True


def load_hooks() -> list[Hook]:
    """Read hooks from env/file each call — tiny files, live-editable."""
    raw = os.environ.get("AGENT_HOOKS", "").strip()
    if not raw:
        path = Path(os.environ.get("AGENT_HOOKS_FILE", "./hooks.json"))
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AGENT_HOOKS is not valid JSON: %s", exc)
        return []
    hooks = []
    for item in items if isinstance(items, list) else []:
        try:
            hooks.append(Hook(
                when=str(item["when"]), tool=str(item["tool"]),
                action=str(item["action"]), message=str(item["message"]),
                arg_match=str(item.get("arg_match", "")),
            ))
        except (KeyError, TypeError):
            logger.warning("skipping malformed hook: %r", item)
    return hooks


def pre_hook_block(tool_name: str, args_serialized: str) -> str | None:
    """Message when a pre-hook blocks this call; None to proceed."""
    for hook in load_hooks():
        if hook.when == "pre" and hook.action == "block" and hook.applies(tool_name, args_serialized):
            return f"[blocked by hook] {hook.message}"
    return None


def post_hook_notes(tool_name: str, args_serialized: str) -> list[str]:
    """Notes appended to the tool result by post-hooks."""
    return [
        h.message for h in load_hooks()
        if h.when == "post" and h.action == "note" and h.applies(tool_name, args_serialized)
    ]
