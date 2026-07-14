"""U50: gated Computer Use agent — loop logic with fake client + backend."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest

from aura_brain.computer_use import ComputerUseAgent


# -- fakes ------------------------------------------------------------------

class FakeBackend:
    """Records I/O calls; screenshot returns fixed bytes."""

    PNG = b"\x89PNG\r\n\x1a\n-fake-screenshot"

    def __init__(self, size: tuple[int, int] = (1280, 800)) -> None:
        self._size = size
        self.calls: list[tuple] = []

    def size(self) -> tuple[int, int]:
        return self._size

    def screenshot(self) -> bytes:
        self.calls.append(("screenshot",))
        return self.PNG

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def click(self, x, y, button="left", count=1):
        self.calls.append(("click", x, y, button, count))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def key(self, keys):
        self.calls.append(("key", keys))

    def scroll(self, x, y, direction, amount):
        self.calls.append(("scroll", x, y, direction, amount))

    def drag(self, x1, y1, x2, y2):
        self.calls.append(("drag", x1, y1, x2, y2))


@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _ToolUse:
    input: dict
    id: str = "tu_1"
    name: str = "computer"
    type: str = "tool_use"


@dataclass
class _Msg:
    content: list
    stop_reason: str


@dataclass
class FakeClient:
    """Returns scripted messages; records the kwargs of each create() call."""

    scripted: list[_Msg]
    calls: list[dict] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _Msg:
        self.calls.append(kwargs)
        return self.scripted[min(len(self.calls) - 1, len(self.scripted) - 1)]


# -- tests ------------------------------------------------------------------

async def test_screenshot_then_finish_returns_summary() -> None:
    backend = FakeBackend()
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "screenshot"})], stop_reason="tool_use"),
        _Msg([_Text("Done — Spotify is now playing.")], stop_reason="end_turn"),
    ])
    agent = ComputerUseAgent(backend, client=client, max_steps=5)

    summary = await agent.run("play music in spotify")

    assert summary == "Done — Spotify is now playing."
    assert ("screenshot",) in backend.calls
    assert len(client.calls) == 2  # tool step + final step


async def test_tool_definition_advertises_computer_and_display_size() -> None:
    backend = FakeBackend(size=(1024, 768))
    client = FakeClient(scripted=[_Msg([_Text("ok")], stop_reason="end_turn")])
    agent = ComputerUseAgent(backend, client=client)

    await agent.run("noop")

    tools = client.calls[0]["tools"]
    assert tools[0]["type"] == "computer_20251124"
    assert tools[0]["display_width_px"] == 1024
    assert tools[0]["display_height_px"] == 768


async def test_click_action_drives_backend_and_feeds_back_screenshot() -> None:
    backend = FakeBackend()
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "left_click", "coordinate": [100, 250]})],
             stop_reason="tool_use"),
        _Msg([_Text("clicked")], stop_reason="end_turn"),
    ])
    agent = ComputerUseAgent(backend, client=client)

    await agent.run("click the play button")

    assert ("click", 100, 250, "left", 1) in backend.calls
    # The tool_result fed back on the 2nd call must be a base64 screenshot image.
    followup = client.calls[1]["messages"][-1]
    result = followup["content"][0]
    assert result["type"] == "tool_result"
    img = result["content"][0]
    assert img["type"] == "image"
    assert base64.b64decode(img["source"]["data"]) == FakeBackend.PNG


async def test_double_click_uses_count_two() -> None:
    backend = FakeBackend()
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "double_click", "coordinate": [10, 20]})],
             stop_reason="tool_use"),
        _Msg([_Text("ok")], stop_reason="end_turn"),
    ])
    await ComputerUseAgent(backend, client=client).run("double click")
    assert ("click", 10, 20, "left", 2) in backend.calls


async def test_type_and_key_actions() -> None:
    backend = FakeBackend()
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "type", "text": "hello"})], stop_reason="tool_use"),
        _Msg([_ToolUse({"action": "key", "text": "ctrl+s"})], stop_reason="tool_use"),
        _Msg([_Text("typed and saved")], stop_reason="end_turn"),
    ])
    await ComputerUseAgent(backend, client=client).run("type hello and save")
    assert ("type_text", "hello") in backend.calls
    assert ("key", "ctrl+s") in backend.calls


async def test_bad_action_becomes_error_result_without_crashing() -> None:
    backend = FakeBackend()
    client = FakeClient(scripted=[
        # missing 'coordinate' → KeyError inside the handler → error tool_result
        _Msg([_ToolUse({"action": "left_click"})], stop_reason="tool_use"),
        _Msg([_Text("recovered")], stop_reason="end_turn"),
    ])
    summary = await ComputerUseAgent(backend, client=client).run("oops")
    assert summary == "recovered"
    err = client.calls[1]["messages"][-1]["content"][0]
    assert err["is_error"] is True


async def test_step_cap_stops_loop() -> None:
    backend = FakeBackend()
    # Always asks for another screenshot → would loop forever without the cap.
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "screenshot"})], stop_reason="tool_use"),
    ])
    summary = await ComputerUseAgent(backend, client=client, max_steps=3).run("loop")
    assert len(client.calls) == 3
    assert "stopped after 3 steps" in summary


async def test_max_steps_env_override(monkeypatch) -> None:
    monkeypatch.setenv("COMPUTER_USE_MAX_STEPS", "2")
    backend = FakeBackend()
    client = FakeClient(scripted=[
        _Msg([_ToolUse({"action": "screenshot"})], stop_reason="tool_use"),
    ])
    await ComputerUseAgent(backend, client=client, max_steps=99).run("loop")
    assert len(client.calls) == 2


# ── U64: OpenAI-driven fallback (no Anthropic key needed) ───────────────

from types import SimpleNamespace

from aura_brain.computer_use import OpenAIComputerAgent


def _oa_tc(tc_id: str, name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=tc_id,
        function=SimpleNamespace(name=name, arguments=__import__("json").dumps(arguments)),
        model_dump=lambda: {"id": tc_id, "type": "function",
                            "function": {"name": name,
                                         "arguments": __import__("json").dumps(arguments)}},
    )


class FakeOpenAI:
    def __init__(self, scripted: list) -> None:
        self._scripted = scripted
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        msg = self._scripted[min(len(self.calls) - 1, len(self._scripted) - 1)]
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


async def test_openai_agent_clicks_then_finishes() -> None:
    backend = FakeBackend()
    client = FakeOpenAI([
        SimpleNamespace(content=None, tool_calls=[
            _oa_tc("t1", "click", {"x": 40, "y": 60}),
        ]),
        SimpleNamespace(content=None, tool_calls=[
            _oa_tc("t2", "done", {"summary": "Spotify is playing."}),
        ]),
    ])
    agent = OpenAIComputerAgent(backend, client=client, max_steps=5)
    summary = await agent.run("start music")
    assert summary == "Spotify is playing."
    assert ("click", 40, 60, "left", 1) in backend.calls
    # Each round feeds a fresh screenshot to the model (vision loop).
    imgs = [m for call in client.calls for m in call["messages"]
            if isinstance(m.get("content"), list)
            and any(c.get("type") == "image_url" for c in m["content"])]
    assert imgs


async def test_openai_agent_step_cap(monkeypatch) -> None:
    monkeypatch.setenv("COMPUTER_USE_MAX_STEPS", "2")
    backend = FakeBackend()
    client = FakeOpenAI([
        SimpleNamespace(content=None, tool_calls=[_oa_tc("t", "wait", {"seconds": 0})]),
    ])
    out = await OpenAIComputerAgent(backend, client=client).run("loop forever")
    assert "stopped after 2 steps" in out


async def test_provider_ladder_prefers_anthropic_then_openai(monkeypatch) -> None:
    from aura_brain import computer_use as cu

    monkeypatch.setenv("COMPUTER_USE_ENABLED", "true")
    monkeypatch.setattr(cu, "PyAutoGuiBackend", lambda: FakeBackend())

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    agent = cu.create_default_agent()
    assert isinstance(agent, cu.OpenAIComputerAgent)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cu.create_default_agent() is None
