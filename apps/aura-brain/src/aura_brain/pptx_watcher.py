"""U205: watch the active PowerPoint slideshow and report slide changes.

You keep PowerPoint. This polls the running slideshow for its current slide
(1-based, exactly as PowerPoint numbers it) and calls back when it changes, so
`slide:N` beats fire as you advance your deck.

Why polling and not events: PowerPoint's real event hooks need a registered
COM add-in; a poll of `SlideShowWindow.View.Slide.SlideIndex` every few hundred
ms needs nothing installed and is robust to the deck being started, stopped, or
restarted mid-talk.

Windows + pywin32 + a running PowerPoint slideshow only. Everywhere else this
degrades to "no slides" without erroring — the manual and keyword triggers
still work, you just advance slides yourself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_POLL_S = 0.3


def powerpoint_available() -> bool:
    """True only when we can actually talk to a PowerPoint slideshow."""
    try:
        import win32com.client  # noqa: F401
    except Exception:  # noqa: BLE001 — not Windows / pywin32 not installed
        return False
    return _read_slide_index() is not None


def _read_slide_index() -> int | None:
    """Current 1-based slide of the active slideshow, or None if there isn't one."""
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            shows = app.SlideShowWindows
            if shows.Count < 1:
                return None
            return int(shows.Item(1).View.Slide.SlideIndex)
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:  # noqa: BLE001 — no slideshow, COM hiccup, not Windows
        logger.debug("PowerPoint slide read failed: %s", exc)
        return None


class PowerPointWatcher:
    """Calls `on_slide(n)` whenever the active slideshow's slide changes."""

    def __init__(self, on_slide: Callable[[int], Awaitable[None]]) -> None:
        self._on_slide = on_slide
        self._task: asyncio.Task | None = None
        self._last: int | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                idx = await asyncio.to_thread(_read_slide_index)
                if idx is not None and idx != self._last:
                    self._last = idx
                    await self._on_slide(idx)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 — a watcher must not crash the talk
                logger.debug("PowerPoint watch loop error: %s", exc)
            await asyncio.sleep(_POLL_S)
