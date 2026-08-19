"""U255: a client that speaks real MCP — JSON-RPC 2.0 over Streamable HTTP.

There was already a `GenericMCPConnector`, but it posted
``{"tool": ..., "arguments": ...}`` to ``/tools/call`` — a shape no MCP server
answers. It also had no way to ask what a server offers, and nothing in the
codebase ever called it. So "AURA supports MCP" was true only in the sense that
a file with MCP in its name existed.

MCP is JSON-RPC 2.0: one endpoint, methods ``initialize``, ``tools/list`` and
``tools/call``. Streamable HTTP servers may answer either with JSON or with an
SSE stream, and both are accepted here — refusing the stream would rule out a
large share of real servers for no reason.

Everything is best-effort and bounded: a server that hangs, lies, or returns
nonsense costs one timeout and an error message, never a wedged turn. A tool
the owner added is a guest in the house, not a member of it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
_TIMEOUT_S = 20.0
#: A server may describe any number of tools; past this we stop reading. An
#: unbounded list would silently blow up every prompt (and its cost) for every
#: turn, which is a strange thing to let a third party decide.
MAX_TOOLS = 40


class McpError(RuntimeError):
    """Anything that went wrong talking to an MCP server, said plainly."""


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    input_schema: dict


def _headers(auth_type: str, auth_value: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        # Streamable HTTP servers pick their reply shape from this.
        "Accept": "application/json, text/event-stream",
    }
    if auth_type == "bearer" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"
    elif auth_type == "api_key" and auth_value:
        headers["X-API-Key"] = auth_value
    return headers


def _parse(resp: httpx.Response) -> dict:
    """Read a JSON-RPC reply from either a JSON body or an SSE stream."""
    text = resp.text
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        # Take the first `data:` line that parses as a JSON-RPC envelope.
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                obj = json.loads(line[5:].strip())
            except ValueError:
                continue
            if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                return obj
        raise McpError("the server sent an event stream with no JSON-RPC reply in it")
    try:
        return json.loads(text) if text else {}
    except ValueError as exc:
        raise McpError(f"the server did not answer with JSON ({exc})") from exc


async def _rpc(
    url: str, method: str, params: dict | None, *,
    auth_type: str = "none", auth_value: str = "",
    session_id: str | None = None,
) -> tuple[dict, str | None]:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    headers = _headers(auth_type, auth_value)
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise McpError(f"could not reach {url} ({exc})") from exc

    if resp.status_code == 401:
        raise McpError("the server rejected the credentials (401)")
    if resp.status_code == 404:
        raise McpError("no MCP endpoint at that URL (404) — check the path")
    if resp.status_code >= 400:
        raise McpError(f"the server answered {resp.status_code}")

    payload = _parse(resp)
    if "error" in payload:
        err = payload["error"] or {}
        raise McpError(str(err.get("message") or err))
    return payload.get("result") or {}, resp.headers.get("Mcp-Session-Id") or session_id


async def list_tools(url: str, auth_type: str = "none", auth_value: str = "") -> list[McpTool]:
    """Handshake, then ask the server what it can do.

    `initialize` first because a spec-compliant server is entitled to refuse
    everything else until it has happened — and because its reply is where a
    wrong URL stops being a guess and becomes a clear error.
    """
    _init, session = await _rpc(
        url, "initialize",
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "AURA", "version": "1"},
        },
        auth_type=auth_type, auth_value=auth_value,
    )
    result, _ = await _rpc(url, "tools/list", {},
                           auth_type=auth_type, auth_value=auth_value,
                           session_id=session)
    raw = result.get("tools")
    if not isinstance(raw, list):
        raise McpError("the server answered tools/list without a tool list")

    tools: list[McpTool] = []
    for item in raw[:MAX_TOOLS]:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        schema = item.get("inputSchema") or item.get("input_schema") or {}
        tools.append(McpTool(
            name=str(item["name"]),
            description=str(item.get("description") or ""),
            input_schema=schema if isinstance(schema, dict) else {},
        ))
    if len(raw) > MAX_TOOLS:
        logger.warning("MCP server at %s offers %d tools; using the first %d",
                       url, len(raw), MAX_TOOLS)
    return tools


async def call_tool(
    url: str, tool: str, arguments: dict,
    auth_type: str = "none", auth_value: str = "",
) -> str:
    """Run one tool and return its result as text for the model to read."""
    result, _ = await _rpc(url, "tools/call", {"name": tool, "arguments": arguments},
                           auth_type=auth_type, auth_value=auth_value)
    return _render(result)


def _render(result: Any) -> str:
    """MCP results are a content list; flatten to text the model can use."""
    if isinstance(result, dict):
        if result.get("isError"):
            parts = _texts(result.get("content"))
            return f"[the tool reported an error: {' '.join(parts) or 'no detail'}]"
        parts = _texts(result.get("content"))
        if parts:
            return "\n".join(parts)
    return json.dumps(result)[:4000]


def _texts(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and block.get("text"):
            out.append(str(block["text"]))
        elif block.get("type") in ("image", "audio"):
            out.append(f"[{block['type']} returned — not shown here]")
    return out
