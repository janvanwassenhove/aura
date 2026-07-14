"""Capabilities / permissions center (U40).

The secure place where the OWNER decides what AURA may do on this laptop — the
UI counterpart of the approval gate. Each capability is a boolean grant stored
in the env (and persisted to the env file so it survives restarts). Some grants
apply live via injected hooks; the rest take effect on the next start.

Security model:
  - Nothing here bypasses the approval gate. Turning a capability ON only lets
    AURA *attempt* it; sensitive actions still prompt for approval.
  - The app launcher can only start apps the owner has pre-registered
    (ALLOWED_APPS) — never an arbitrary executable.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from aura_brain.setup_api import _write_env  # reuse the .env writer

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

# key -> (env var, default, label, description, applies_live)
_CAPS: dict[str, tuple[str, str, str, str, bool]] = {
    "dev_agent": ("DEV_AGENT_ENABLED", "true", "Developer tasks",
                  "Read code, run tests and shell tasks. Writes/commits/pushes still ask for approval.", True),
    "app_launch": ("APP_LAUNCH_ENABLED", "true", "Launch apps",
                   "Open apps you've allow-listed (e.g. VS Code). Each launch asks for approval.", True),
    "follow_me": ("HEAD_TRACKING", "true", "Follow me",
                  "The robot keeps looking at your face.", True),
    "body_follow": ("BODY_FOLLOW", "false", "Turn body too",
                    "The torso rotates along with the face, not just the head.", True),
    "speak_replies": ("SPEAK_REPLIES", "true", "Speak replies aloud",
                      "Say answers out loud on the robot with a gesture.", True),
    "gestures": ("GESTURES_ENABLED", "true", "React to gestures",
                 "Wave back to an open palm, celebrate a thumbs-up.", True),
    "recognition": ("RECOGNITION_ENABLED", "true", "Face recognition",
                    "Recognize and greet known people. Needs the knowledge passphrase.", False),
    "maintenance": ("MAINTENANCE_ENABLED", "true", "Self-maintenance",
                    "Periodic self-checks and auto-recovery of the robot link.", True),
    "computer_use": ("COMPUTER_USE_ENABLED", "false", "Control the screen",
                     "Let AURA see the screen and drive the mouse/keyboard to "
                     "operate any app. Off by default; needs an Anthropic API key; "
                     "every use still asks for approval.", True),
}

_live_hooks: dict[str, Callable[[bool], None]] = {}


def set_live_hook(key: str, hook: Callable[[bool], None]) -> None:
    """Register a callback applied immediately when a capability toggles."""
    _live_hooks[key] = hook


def _is_on(env_var: str, default: str) -> bool:
    return os.environ.get(env_var, default).lower() == "true"


@router.get("")
async def list_capabilities() -> JSONResponse:
    caps = [
        {
            "key": key,
            "label": label,
            "description": desc,
            "enabled": _is_on(env_var, default),
            "applies_live": live,
        }
        for key, (env_var, default, label, desc, live) in _CAPS.items()
    ]
    # Registered app launchers (name only — never expose the command path list
    # beyond what the owner set).
    apps = [p.split("=", 1)[0] for p in os.environ.get("ALLOWED_APPS", "").split(";") if "=" in p]
    return JSONResponse({"capabilities": caps, "allowed_apps": apps})


@router.post("/{key}")
async def set_capability(key: str, body: dict) -> JSONResponse:
    if key not in _CAPS:
        return JSONResponse({"error": f"unknown capability {key!r}"}, status_code=404)
    enabled = bool((body or {}).get("enabled", True))
    env_var, _default, _label, _desc, live = _CAPS[key]
    value = "true" if enabled else "false"
    os.environ[env_var] = value
    _write_env({env_var: value})
    applied_live = False
    if live and key in _live_hooks:
        try:
            _live_hooks[key](enabled)
            applied_live = True
        except Exception:  # noqa: BLE001 — a hook failure must not 500 the toggle
            applied_live = False
    return JSONResponse({
        "key": key, "enabled": enabled,
        "applied_live": applied_live,
        "restart_required": bool(not live),
    })
