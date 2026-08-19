"""U255: MCP servers the owner adds, and the tools they bring with them.

Asked for after U254: "voeg mogelijkheid toe om tools toe te voegen (mcp) die
daarna dan kunnen geactiveerd worden." The point is that AURA stops needing a
hand-written connector per service — anything with an MCP server can be added,
inspected, and switched on.

Three rules shape this file.

**Adding is not activating.** A server is added, its tools are discovered and
shown, and only then can it be switched on. A third party's tool list should
never quietly become part of what the assistant will do; the owner has to look
at it first. Discovery therefore happens on ADD, and the tools are stored so
the list can be read without the server being up.

**Activated is not unsupervised.** MCP tools land in their own policy group
(`mcp tools`), which defaults to `asks` — every call stops for approval until
the owner says otherwise. Built-in tools were written here and reviewed here;
these were not, and the difference should cost a click, not a promise.

**Secrets go to the keyring, never to this file.** The token for a server is
stored in the OS credential store (U225's store, a different account name).
What lands on disk is the fact that a secret exists, not the secret.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "./data/mcp-servers.json"
_KEYRING_SERVICE = "AURA"
#: Namespaced so an MCP tool can never collide with (or impersonate) a built-in.
TOOL_PREFIX = "mcp__"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")

_cache: dict | None = None


@dataclass
class McpToolSpec:
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpServer:
    name: str
    url: str
    auth_type: str = "none"          # none | bearer | api_key
    enabled: bool = False            # added ≠ activated
    has_secret: bool = False
    tools: list[McpToolSpec] = field(default_factory=list)
    #: Why discovery last failed, so a dead server explains itself.
    last_error: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["tool_names"] = [qualified_name(self.name, t.name) for t in self.tools]
        return d


def qualified_name(server: str, tool: str) -> str:
    """`mcp__<server>__<tool>` — unique, and visibly not a built-in."""
    return f"{TOOL_PREFIX}{server}__{tool}"


def split_qualified(name: str) -> tuple[str, str] | None:
    if not name.startswith(TOOL_PREFIX):
        return None
    rest = name[len(TOOL_PREFIX):]
    server, sep, tool = rest.partition("__")
    return (server, tool) if sep and server and tool else None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _path() -> Path:
    return Path(os.environ.get("MCP_SERVERS_PATH", _DEFAULT_PATH))


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        servers = raw.get("servers")
        _cache = {"servers": servers if isinstance(servers, dict) else {}}
    except (OSError, ValueError):
        _cache = {"servers": {}}
    return _cache


def _save() -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_load(), indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("could not persist MCP servers: %s", exc)


def _hydrate(raw: dict) -> McpServer:
    tools = [McpToolSpec(**t) for t in raw.get("tools", []) if isinstance(t, dict)]
    return McpServer(
        name=raw["name"], url=raw.get("url", ""),
        auth_type=raw.get("auth_type", "none"),
        enabled=bool(raw.get("enabled", False)),
        has_secret=bool(raw.get("has_secret", False)),
        tools=tools, last_error=raw.get("last_error", ""),
    )


def all_servers() -> list[McpServer]:
    return [_hydrate(r) for r in _load()["servers"].values()]


def get(name: str) -> McpServer | None:
    raw = _load()["servers"].get(name)
    return _hydrate(raw) if raw else None


def _put(server: McpServer) -> None:
    _load()["servers"][server.name] = asdict(server)
    _save()


# ---------------------------------------------------------------------------
# Secrets — the keyring, never the JSON
# ---------------------------------------------------------------------------


def _keyring():
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        return None if isinstance(keyring.get_keyring(), FailKeyring) else keyring
    except Exception:  # noqa: BLE001 — an unusable keyring must never break boot
        return None


def _secret_account(name: str) -> str:
    return f"mcp-{name}"


def set_secret(name: str, value: str) -> bool:
    """Store a server's token. Returns False when there is nowhere safe to put it.

    Deliberately no plaintext fallback: writing a bearer token next to the
    config would recreate exactly the problem U225 fixed for the passphrase.
    An owner who has no keyring can still use `none` auth or an env var.
    """
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(_KEYRING_SERVICE, _secret_account(name), value)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not store MCP secret for %s: %s", name, exc)
        return False


def get_secret(name: str) -> str:
    """The stored token, or an env override, or empty."""
    env = os.environ.get(f"MCP_{name.upper().replace('-', '_')}_AUTH_VALUE", "")
    if env:
        return env
    kr = _keyring()
    if kr is None:
        return ""
    try:
        return kr.get_password(_KEYRING_SERVICE, _secret_account(name)) or ""
    except Exception:  # noqa: BLE001
        return ""


def _forget_secret(name: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(_KEYRING_SERVICE, _secret_account(name))
    except Exception:  # noqa: BLE001 — absent is the desired end state anyway
        pass


# ---------------------------------------------------------------------------
# The owner's operations
# ---------------------------------------------------------------------------


def validate_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not _NAME_RE.match(name):
        raise ValueError(
            "a server name is lowercase letters, digits, - or _ (max 31)")
    return name


def add(name: str, url: str, auth_type: str = "none", secret: str = "") -> McpServer:
    """Register a server. It is NOT enabled — discovery has to happen first."""
    name = validate_name(name)
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("the URL must start with http:// or https://")
    if auth_type not in ("none", "bearer", "api_key"):
        raise ValueError("auth must be none, bearer or api_key")

    stored = False
    if secret:
        stored = set_secret(name, secret)
        if not stored:
            raise ValueError(
                "there is no OS keyring on this machine, so the token cannot be "
                "stored safely. Use auth 'none', or set "
                f"MCP_{name.upper().replace('-', '_')}_AUTH_VALUE in the environment.")

    server = McpServer(name=name, url=url, auth_type=auth_type,
                       enabled=False, has_secret=stored or bool(get_secret(name)))
    _put(server)
    return server


def remove(name: str) -> bool:
    if name not in _load()["servers"]:
        return False
    del _load()["servers"][name]
    _save()
    _forget_secret(name)
    return True


def set_enabled(name: str, enabled: bool) -> McpServer | None:
    server = get(name)
    if server is None:
        return None
    # Enabling a server with no known tools would put an empty promise in the
    # policy — the owner sees "on" and nothing can happen.
    if enabled and not server.tools:
        raise ValueError(
            "no tools have been discovered yet — press Refresh first, so you "
            "can see what you are switching on")
    server.enabled = enabled
    _put(server)
    return server


def record_tools(name: str, tools: list[McpToolSpec], error: str = "") -> McpServer | None:
    server = get(name)
    if server is None:
        return None
    if error:
        server.last_error = error
        # Keep the previously known tools: a server that is down for a minute
        # should not silently strip capabilities the owner already approved.
    else:
        server.tools = tools
        server.last_error = ""
    _put(server)
    return server


# ---------------------------------------------------------------------------
# What the tool layer consumes
# ---------------------------------------------------------------------------


def enabled_tool_specs() -> list[dict]:
    """OpenAI function schemas for every tool of every ENABLED server."""
    specs: list[dict] = []
    for server in all_servers():
        if not server.enabled:
            continue
        for tool in server.tools:
            schema = tool.input_schema or {"type": "object", "properties": {}}
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            specs.append({
                "type": "function",
                "function": {
                    "name": qualified_name(server.name, tool.name),
                    # Say where it came from: the model should know this is a
                    # guest tool, and so should anyone reading a transcript.
                    "description": (
                        f"[{server.name} · added by the owner] "
                        f"{tool.description or tool.name}"
                    )[:1024],
                    "parameters": schema,
                },
            })
    return specs


def enabled_tool_names() -> frozenset[str]:
    return frozenset(s["function"]["name"] for s in enabled_tool_specs())


def route(tool_name: str) -> tuple[McpServer, str] | None:
    """Which server serves this qualified tool name, and under what tool name."""
    parts = split_qualified(tool_name)
    if parts is None:
        return None
    server_name, tool = parts
    server = get(server_name)
    if server is None or not server.enabled:
        return None
    return server, tool


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None
