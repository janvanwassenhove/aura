"""Gated Computer Use agent (U50).

Anthropic's computer-use loop gives Claude screenshot + mouse/keyboard control of
this laptop so it can operate ANY desktop app — not only the allow-listed ones —
when the allow-listed launcher and media keys aren't enough (e.g. clicking around
inside an app's UI). It is Anthropic's own technology and runs on the Anthropic
API, so it needs an ``ANTHROPIC_API_KEY`` and is **default OFF**.

Security model (unchanged, top priority):
  - The ``use_computer`` orchestrator tool is in ``APPROVAL_REQUIRED``, so any turn
    that reaches for it prompts the owner first. This module never bypasses the
    approval gate — it only ever runs after approval was granted.
  - The agent is instructed to never enter credentials/passwords or payment
    details, never accept terms, and never take irreversible destructive actions
    on its own — it asks the owner instead. These mirror the global safety rules.
  - Runs are step-capped (``COMPUTER_USE_MAX_STEPS``) and every action is logged.

The input backend is injectable (a small Protocol) so the loop is unit-tested with
fakes; ``PyAutoGuiBackend`` is the real Windows driver (lazy-imports pyautogui).
The Anthropic client is injectable too — production wraps ``AsyncAnthropic`` with
the computer-use beta header; tests pass a fake that returns scripted messages.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Opus 4.8 computer-use tool + beta header (see Anthropic docs).
_TOOL_TYPE = "computer_20251124"
_BETA_HEADER = "computer-use-2025-11-24"

_SYSTEM = (
    "You are operating the owner's Windows laptop on their behalf, with their "
    "explicit permission, to accomplish a specific goal by controlling the "
    "screen, mouse and keyboard.\n"
    "Work in small steps: take a screenshot, decide the single next action, do "
    "it, then screenshot again to verify the result before continuing. Prefer "
    "keyboard shortcuts over fiddly mouse targeting when you can.\n"
    "SAFETY — you must NOT do any of the following yourself; instead stop and "
    "report that the owner needs to do it:\n"
    "  - type passwords, API keys, card/bank/ID numbers, or any credential;\n"
    "  - sign in, create accounts, or accept terms / cookie / consent dialogs;\n"
    "  - make purchases, payments, transfers, or other financial actions;\n"
    "  - permanently delete data or take other irreversible destructive actions.\n"
    "When the goal is achieved, stop and give a one-paragraph summary of what "
    "you did and the final state. If you get stuck or hit one of the above, stop "
    "and explain what remains for the owner to do."
)


@runtime_checkable
class InputBackend(Protocol):
    """Desktop I/O surface the agent drives. All methods are synchronous; the
    agent calls them off the event loop via ``asyncio.to_thread``."""

    def size(self) -> tuple[int, int]: ...
    def screenshot(self) -> bytes: ...  # PNG bytes of the current screen
    def move(self, x: int, y: int) -> None: ...
    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None: ...
    def type_text(self, text: str) -> None: ...
    def key(self, keys: str) -> None: ...  # e.g. "ctrl+s", "Return"
    def scroll(self, x: int, y: int, direction: str, amount: int) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None: ...


class ComputerUseAgent:
    def __init__(
        self,
        backend: InputBackend,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        model: str = "claude-opus-4-8",
        max_steps: int = 25,
    ) -> None:
        self._backend = backend
        self._model = model
        self._max_steps = int(os.environ.get("COMPUTER_USE_MAX_STEPS", str(max_steps)))
        self._client = client or _AsyncAnthropicClient(
            api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        w, h = backend.size()
        self._size = (int(w), int(h))

    # -- public --------------------------------------------------------

    async def run(self, goal: str, session_id: str = "default") -> str:
        """Drive the computer-use loop toward ``goal``; return a short summary."""
        tool = {
            "type": _TOOL_TYPE,
            "name": "computer",
            "display_width_px": self._size[0],
            "display_height_px": self._size[1],
            "display_number": 1,
        }
        messages: list[dict] = [{"role": "user", "content": goal}]
        texts: list[str] = []
        logger.info("ComputerUseAgent starting goal=%r (max_steps=%d)", goal, self._max_steps)

        for step in range(self._max_steps):
            msg = await self._client.create(
                model=self._model,
                max_tokens=1024,
                system=_SYSTEM,
                tools=[tool],
                messages=messages,
            )
            step_text = [
                b.text for b in msg.content
                if getattr(b, "type", None) == "text" and getattr(b, "text", None)
            ]
            texts.extend(step_text)
            tool_uses = [b for b in msg.content if getattr(b, "type", None) == "tool_use"]

            if getattr(msg, "stop_reason", None) != "tool_use" or not tool_uses:
                logger.info("ComputerUseAgent done at step %d (stop=%s)", step,
                            getattr(msg, "stop_reason", None))
                break

            messages.append({"role": "assistant", "content": msg.content})
            results = [await self._exec(tu) for tu in tool_uses]
            messages.append({"role": "user", "content": results})
        else:
            logger.warning("ComputerUseAgent hit step cap (%d)", self._max_steps)
            texts.append(f"[stopped after {self._max_steps} steps — goal may be incomplete]")

        summary = texts[-1] if texts else "Computer-use run finished with no summary."
        return summary

    # -- internals -----------------------------------------------------

    async def _exec(self, tool_use: Any) -> dict:
        action = (tool_use.input or {}).get("action")
        try:
            content = await self._do_action(action, tool_use.input or {})
        except Exception as exc:  # noqa: BLE001 — surface as a recoverable tool error
            logger.debug("computer action %r failed: %s", action, exc)
            return {"type": "tool_result", "tool_use_id": tool_use.id,
                    "content": f"[action {action} failed: {exc}]", "is_error": True}
        return {"type": "tool_result", "tool_use_id": tool_use.id, "content": content}

    async def _do_action(self, action: str | None, inp: dict) -> Any:
        b = self._backend
        logger.info("computer action: %s %s", action,
                    {k: v for k, v in inp.items() if k != "action"})

        if action == "screenshot":
            return await self._shot()
        if action == "mouse_move":
            x, y = inp["coordinate"]
            await asyncio.to_thread(b.move, int(x), int(y))
            return await self._shot()
        if action in ("left_click", "right_click", "middle_click",
                      "double_click", "triple_click"):
            x, y = inp["coordinate"]
            button = {"right_click": "right", "middle_click": "middle"}.get(action, "left")
            count = {"double_click": 2, "triple_click": 3}.get(action, 1)
            await asyncio.to_thread(b.click, int(x), int(y), button, count)
            return await self._shot()
        if action == "left_click_drag":
            x1, y1 = inp["start_coordinate"]
            x2, y2 = inp["coordinate"]
            await asyncio.to_thread(b.drag, int(x1), int(y1), int(x2), int(y2))
            return await self._shot()
        if action == "type":
            await asyncio.to_thread(b.type_text, inp.get("text", ""))
            return await self._shot()
        if action in ("key", "hold_key"):
            await asyncio.to_thread(b.key, inp.get("text", ""))
            return await self._shot()
        if action == "scroll":
            x, y = inp.get("coordinate", (self._size[0] // 2, self._size[1] // 2))
            await asyncio.to_thread(
                b.scroll, int(x), int(y),
                inp.get("scroll_direction", "down"), int(inp.get("scroll_amount", 3)),
            )
            return await self._shot()
        if action == "wait":
            await asyncio.sleep(min(5.0, float(inp.get("duration", 1))))
            return await self._shot()
        if action == "cursor_position":
            return "cursor position tracking is not available; take a screenshot instead"
        return f"[unsupported action: {action}]"

    async def _shot(self) -> list[dict]:
        data = await asyncio.to_thread(self._backend.screenshot)
        b64 = base64.standard_b64encode(data).decode("ascii")
        return [{"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": b64,
        }}]


class _AsyncAnthropicClient:
    """Thin adapter over ``AsyncAnthropic`` that adds the computer-use beta header.
    Lazily imports the SDK so the ``[computeruse]`` extra is only needed when the
    capability is actually enabled."""

    def __init__(self, api_key: str) -> None:
        from anthropic import AsyncAnthropic  # lazy — optional dependency

        self._c = AsyncAnthropic(api_key=api_key or None)

    async def create(self, **kwargs: Any) -> Any:
        return await self._c.beta.messages.create(betas=[_BETA_HEADER], **kwargs)


class PyAutoGuiBackend:
    """Real Windows desktop backend (lazy-imports pyautogui + Pillow)."""

    def __init__(self) -> None:
        import pyautogui  # lazy — only when computer use is enabled

        self._pg = pyautogui
        pyautogui.FAILSAFE = False

    def size(self) -> tuple[int, int]:
        w, h = self._pg.size()
        return int(w), int(h)

    def screenshot(self) -> bytes:
        import io

        buf = io.BytesIO()
        self._pg.screenshot().save(buf, format="PNG")
        return buf.getvalue()

    def move(self, x: int, y: int) -> None:
        self._pg.moveTo(x, y)

    def click(self, x: int, y: int, button: str = "left", count: int = 1) -> None:
        self._pg.click(x=x, y=y, button=button, clicks=count, interval=0.05)

    def type_text(self, text: str) -> None:
        self._pg.typewrite(text, interval=0.01)

    def key(self, keys: str) -> None:
        parts = [self._map(k) for k in keys.replace("+", " ").split() if k.strip()]
        if len(parts) > 1:
            self._pg.hotkey(*parts)
        elif parts:
            self._pg.press(parts[0])

    def scroll(self, x: int, y: int, direction: str, amount: int) -> None:
        self._pg.moveTo(x, y)
        clicks = int(amount) * 100
        if direction == "up":
            self._pg.scroll(clicks)
        elif direction == "down":
            self._pg.scroll(-clicks)
        elif direction == "left":
            self._pg.hscroll(-clicks)
        elif direction == "right":
            self._pg.hscroll(clicks)

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._pg.moveTo(x1, y1)
        self._pg.dragTo(x2, y2, duration=0.3, button="left")

    @staticmethod
    def _map(key: str) -> str:
        k = key.strip().lower()
        return {"return": "enter", "super": "win", "cmd": "win", "meta": "win"}.get(k, k)


def create_default_agent() -> ComputerUseAgent | None:
    """Build the real agent if enabled + configured; else None.

    Requires COMPUTER_USE_ENABLED=true, an ANTHROPIC_API_KEY, and the
    ``[computeruse]`` extra (pyautogui). Any missing piece → disabled (None).
    """
    if os.environ.get("COMPUTER_USE_ENABLED", "false").lower() != "true":
        return None
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        logger.warning("Computer Use enabled but ANTHROPIC_API_KEY is not set — disabled.")
        return None
    try:
        backend = PyAutoGuiBackend()
    except Exception as exc:  # noqa: BLE001 — pyautogui/display missing
        logger.warning("Computer Use enabled but backend unavailable (%s) — disabled.", exc)
        return None
    return ComputerUseAgent(backend)
