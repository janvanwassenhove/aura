"""U254: which connectors the owner switched on, remembered across restarts.

`ENABLED_CONNECTORS` is an environment variable, which meant enabling Google
required editing a file the desktop app generates and then restarting the
brain. In practice that is not a setting at all — it is a deployment detail,
and the four Connect buttons in the console pointed at connectors the owner
had no way to switch on from the console.

Stored as JSON next to the other owner-owned state (same shape as the mode
policy from U252): the environment stays the DEFAULT, and an explicit choice
overrides it. Nothing is written until the owner actually chooses, so an
untouched install keeps behaving exactly as its configuration says.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from shared_config import ConnectorServiceSettings

from connector_service import connector_state

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "./data/connector-prefs.json"
_cache: dict[str, bool] | None = None


def _path() -> Path:
    return Path(os.environ.get("CONNECTOR_PREFS_PATH", _DEFAULT_PATH))


def _load() -> dict[str, bool]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        overrides = raw.get("enabled")
        _cache = ({str(k): bool(v) for k, v in overrides.items()}
                  if isinstance(overrides, dict) else {})
    except (OSError, ValueError):
        _cache = {}
    return _cache


def _save() -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"enabled": _load()}, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("could not persist connector prefs: %s", exc)


def enabled_keys(settings: ConnectorServiceSettings | None = None) -> set[str]:
    """The connectors that should be live: configuration, then the owner."""
    s = settings or ConnectorServiceSettings()
    keys = set(s.enabled_connector_list)
    for key, on in _load().items():
        if key not in connector_state.known_keys():
            continue          # a key we no longer ship — ignore, never crash
        if on:
            keys.add(key)
        else:
            keys.discard(key)
    return keys


def set_enabled(key: str, enabled: bool) -> None:
    """Record the owner's choice for one connector.

    Always stores an explicit value, even when it equals the configured
    default: "I chose this" and "it happens to match today's config" are
    different facts, and only the first should survive a config change.
    """
    if key not in connector_state.known_keys():
        raise ValueError(f"unknown connector: {key!r}")
    _load()[key] = bool(enabled)
    _save()


def clear(key: str) -> None:
    """Forget the owner's choice; the configured default applies again."""
    _load().pop(key, None)
    _save()


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None
