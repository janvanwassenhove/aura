"""U255: adding MCP tools, looking at them, and only then switching them on.

Asked for after U254: "voeg mogelijkheid toe om tools toe te voegen (mcp) die
daarna dan kunnen geactiveerd worden."

There was already a `GenericMCPConnector`, but it posted a shape no MCP server
answers (`{"tool":…}` to `/tools/call`), had no way to ask what a server
offers, and nothing ever called it. These tests pin the parts that make the
feature real: a client that speaks JSON-RPC, a registry where added is not the
same as activated, and a gate that treats a stranger's tool as a stranger's.
"""

from __future__ import annotations

import json

import pytest
from orchestrator import mcp_client, mcp_servers, mode_policy


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_SERVERS_PATH", str(tmp_path / "mcp.json"))
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    # Never touch the real OS keyring from a test.
    monkeypatch.setattr(mcp_servers, "_keyring", lambda: None)
    mcp_servers.reset_cache_for_tests()
    mode_policy.reset_cache_for_tests()
    yield
    mcp_servers.reset_cache_for_tests()
    mode_policy.reset_cache_for_tests()


# ---------------------------------------------------------------------------
# The client: does it speak MCP?
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: dict, ctype: str = "application/json") -> None:
        self.text = json.dumps(payload)
        self.status_code = 200
        self.headers = {"content-type": ctype}


def _fake_transport(monkeypatch, handler) -> list[dict]:
    """Capture the JSON-RPC bodies AURA sends, and reply with `handler`."""
    seen: list[dict] = []

    class _Client:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):  # noqa: A002
            seen.append({"url": url, "body": json, "headers": headers or {}})
            return handler(json)

    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", _Client)
    return seen


async def test_discovery_speaks_json_rpc_and_handshakes_first(monkeypatch) -> None:
    """A spec-compliant server may refuse everything before `initialize`, and
    the old connector never sent one — it posted an invented REST shape."""
    def handler(body):
        if body["method"] == "initialize":
            return _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}})
        return _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {"tools": [
            {"name": "search", "description": "Search the wiki",
             "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}},
        ]}})

    seen = _fake_transport(monkeypatch, handler)
    tools = await mcp_client.list_tools("https://example.test/mcp")

    assert [c["body"]["method"] for c in seen] == ["initialize", "tools/list"]
    assert all(c["body"]["jsonrpc"] == "2.0" for c in seen)
    assert [t.name for t in tools] == ["search"]


async def test_an_event_stream_reply_is_understood(monkeypatch) -> None:
    """Streamable HTTP servers may answer with SSE; refusing that would rule
    out a large share of real servers for no reason."""
    def handler(body):
        payload = ({} if body["method"] == "initialize"
                   else {"tools": [{"name": "ping", "description": "", "inputSchema": {}}]})
        r = _FakeResponse({}, ctype="text/event-stream")
        r.text = f'event: message\ndata: {json.dumps({"jsonrpc": "2.0", "id": 1, "result": payload})}\n\n'
        return r

    _fake_transport(monkeypatch, handler)
    tools = await mcp_client.list_tools("https://example.test/mcp")
    assert [t.name for t in tools] == ["ping"]


async def test_a_tool_result_is_flattened_to_text(monkeypatch) -> None:
    def handler(body):
        return _FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "42 results"}]}})

    _fake_transport(monkeypatch, handler)
    out = await mcp_client.call_tool("https://example.test/mcp", "search", {"q": "x"})
    assert out == "42 results"


async def test_a_server_error_is_a_sentence_not_a_stack_trace(monkeypatch) -> None:
    def handler(body):
        return _FakeResponse({"jsonrpc": "2.0", "id": 1,
                              "error": {"code": -32601, "message": "no such tool"}})

    _fake_transport(monkeypatch, handler)
    with pytest.raises(mcp_client.McpError, match="no such tool"):
        await mcp_client.list_tools("https://example.test/mcp")


# ---------------------------------------------------------------------------
# The registry: added is not activated
# ---------------------------------------------------------------------------


def _added_with_tools(name: str = "wiki") -> None:
    mcp_servers.add(name, "https://example.test/mcp")
    mcp_servers.record_tools(name, [
        mcp_servers.McpToolSpec("search", "Search the wiki", {"type": "object", "properties": {}}),
    ])


def test_adding_a_server_does_not_activate_it() -> None:
    """A third party's tool list must not quietly become part of what the
    assistant will do — the owner has to look at it first."""
    server = mcp_servers.add("wiki", "https://example.test/mcp")
    assert server.enabled is False
    assert mcp_servers.enabled_tool_names() == frozenset()


def test_you_cannot_switch_on_a_server_whose_tools_are_unknown() -> None:
    """Otherwise "on" is an empty promise: nothing can happen and nothing says
    why."""
    mcp_servers.add("wiki", "https://example.test/mcp")
    with pytest.raises(ValueError, match="no tools"):
        mcp_servers.set_enabled("wiki", True)


def test_switching_on_publishes_its_tools_namespaced() -> None:
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    assert mcp_servers.enabled_tool_names() == frozenset({"mcp__wiki__search"})


def test_the_name_marks_it_as_a_guest_and_cannot_collide() -> None:
    """`mcp__` is reserved, so an added tool can never impersonate a built-in
    like send_mail — nor two servers each other."""
    _added_with_tools("wiki")
    _added_with_tools("notes")
    mcp_servers.set_enabled("wiki", True)
    mcp_servers.set_enabled("notes", True)
    names = mcp_servers.enabled_tool_names()
    assert names == frozenset({"mcp__wiki__search", "mcp__notes__search"})
    assert all(n.startswith("mcp__") for n in names)


def test_removing_a_server_takes_its_tools_with_it() -> None:
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    mcp_servers.remove("wiki")
    assert mcp_servers.enabled_tool_names() == frozenset()
    assert mcp_servers.route("mcp__wiki__search") is None


def test_a_failed_refresh_keeps_the_tools_it_already_knew() -> None:
    """A server that is down for a minute should not silently strip
    capabilities the owner already approved."""
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    mcp_servers.record_tools("wiki", [], error="could not reach it")
    server = mcp_servers.get("wiki")
    assert [t.name for t in server.tools] == ["search"]
    assert server.last_error == "could not reach it"


def test_a_secret_never_lands_in_the_json() -> None:
    """With no keyring there is deliberately no plaintext fallback: writing a
    bearer token next to the config recreates exactly what U225 fixed."""
    with pytest.raises(ValueError, match="keyring"):
        mcp_servers.add("wiki", "https://example.test/mcp",
                        auth_type="bearer", secret="s3cret")


# ---------------------------------------------------------------------------
# The gate: a stranger's tool is treated as a stranger's
# ---------------------------------------------------------------------------


def test_an_added_tool_asks_before_it_runs() -> None:
    """Built-in tools were written and reviewed in this repo; these were not.
    That difference is worth one click per call until the owner says otherwise.
    """
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    assert mode_policy.requires_approval("mcp__wiki__search", "work") is True


def test_the_owner_can_decide_to_stop_being_asked() -> None:
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    mode_policy.set_group_state("work", mode_policy.MCP_GROUP, "allows")
    assert mode_policy.requires_approval("mcp__wiki__search", "work") is False


def test_blocking_the_group_removes_the_tools_entirely() -> None:
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    assert "mcp__wiki__search" in mode_policy.allowed_tools("work")

    mode_policy.set_group_state("work", mode_policy.MCP_GROUP, "blocked")
    assert "mcp__wiki__search" not in mode_policy.allowed_tools("work")


def test_a_talk_is_no_place_for_a_third_party_tool() -> None:
    """Present mode locks down to what a stage needs; an added tool firing
    mid-presentation is the last thing anyone wants."""
    _added_with_tools()
    mcp_servers.set_enabled("wiki", True)
    assert "mcp__wiki__search" not in mode_policy.allowed_tools("presentation")


def test_a_server_that_is_off_offers_nothing_to_the_model() -> None:
    from orchestrator.tool_schemas import build_tool_specs

    _added_with_tools()
    specs = build_tool_specs(frozenset({"mcp__wiki__search"}))
    assert [s["function"]["name"] for s in specs] == []

    mcp_servers.set_enabled("wiki", True)
    specs = build_tool_specs(mode_policy.allowed_tools("work"))
    names = [s["function"]["name"] for s in specs]
    assert "mcp__wiki__search" in names
    # And it says where it came from, in the description the model reads.
    spec = next(s for s in specs if s["function"]["name"] == "mcp__wiki__search")
    assert "wiki" in spec["function"]["description"]
