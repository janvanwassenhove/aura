"""U263: watch the slideshow that is actually running — PowerPoint or Keynote.

Replaces `pptx_watcher` (U205), which had three faults the owner ran into in
one sitting:

  1. **It looked once.** `start_presentation` asked `powerpoint_available()` at
     the moment the scenario started; if the slideshow was not up YET, no
     watcher was created and there was no retry. Start the scenario before the
     show — the natural order, since the scenario is what you set up first —
     and every `slide:N` beat stayed silent for the whole talk, while the UI
     calmly said "manual". Now it keeps looking, and says which state it is in.

  2. **It never checked WHICH deck.** The scenario's `pptx:` field was
     documentation; nothing compared it to what was on screen. Open last
     month's deck and the beats fire on the wrong slides, in front of an
     audience, with no warning anywhere.

  3. **It never knew how many slides there were.** Insert one slide in the
     middle and every `slide:N` after it points one place too early — silently.

Keynote was simply absent, so half of the possible presenters could not use
any of this. It speaks a different dialect (AppleScript, not COM) but answers
the same three questions, so both live behind one `read_state()`.

Everywhere else — Linux, no presentation extra, no slideshow — this degrades to
"nothing is running", which is a state, not an error: manual and keyword beats
work regardless.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

_POLL_S = float(os.environ.get("SLIDES_POLL_S", "0.3"))
_OSASCRIPT_TIMEOUT_S = 3.0


@dataclass(frozen=True)
class SlideState:
    """What is on the projector right now."""

    app: str        # "powerpoint" | "keynote"
    deck: str       # file or document name, as the app reports it
    slide: int      # 1-based, exactly as the app numbers it
    total: int      # 0 when the app will not say


# ---------------------------------------------------------------------------
# PowerPoint (Windows, COM)
# ---------------------------------------------------------------------------


def _read_powerpoint() -> SlideState | None:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            shows = app.SlideShowWindows
            if shows.Count < 1:
                return None
            view = shows.Item(1).View
            pres = shows.Item(1).Presentation
            return SlideState(
                app="powerpoint",
                deck=str(getattr(pres, "Name", "") or ""),
                slide=int(view.Slide.SlideIndex),
                total=int(getattr(pres.Slides, "Count", 0) or 0),
            )
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:  # noqa: BLE001 — no show, COM hiccup, not Windows
        logger.debug("PowerPoint read failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Keynote (macOS, AppleScript)
# ---------------------------------------------------------------------------

# One script, one round trip: asking three times would let the answers come
# from three different moments, and a slide number that belongs to a different
# deck than the name beside it is worse than no answer.
_KEYNOTE_SCRIPT = """
tell application "Keynote"
    if not running then return ""
    if (count of documents) is 0 then return ""
    set d to front document
    if not playing then return ""
    return (name of d) & "\\t" & (slide number of current slide of d) & "\\t" & (count of slides of d)
end tell
"""


def _read_keynote() -> SlideState | None:
    if platform.system() != "Darwin" or not shutil.which("osascript"):
        return None
    try:
        out = subprocess.run(                                  # noqa: S603
            ["osascript", "-e", _KEYNOTE_SCRIPT],              # noqa: S607
            capture_output=True, text=True, timeout=_OSASCRIPT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Keynote read failed: %s", exc)
        return None
    line = (out.stdout or "").strip()
    if not line:
        return None                       # Keynote closed, or not playing
    parts = line.split("\t")
    if len(parts) < 2:
        return None
    try:
        return SlideState(
            app="keynote",
            deck=parts[0].strip(),
            slide=int(parts[1]),
            total=int(parts[2]) if len(parts) > 2 else 0,
        )
    except ValueError:
        return None


def read_state() -> SlideState | None:
    """The running slideshow, whichever app it is in, or None."""
    forced = os.environ.get("SLIDES_APP", "").strip().lower()
    readers = {"powerpoint": _read_powerpoint, "keynote": _read_keynote}
    if forced in readers:
        return readers[forced]()
    for read in (_read_powerpoint, _read_keynote):
        state = read()
        if state is not None:
            return state
    return None


def available() -> bool:
    """Is a slideshow running right now?"""
    return read_state() is not None


@lru_cache(maxsize=1)
def read_blocker() -> str:
    """Why he CANNOT look — as opposed to finding nothing to look at.

    U266: `_read_powerpoint` returns None for "no slideshow up" and for "the
    library that reads PowerPoint is not installed", and the UI rendered both
    as "waiting for your slideshow (F5 / Play)". The second one is not a wait,
    it is a dead end: the packaged app's bootstrap never asked for the
    `presentation` extra, so pywin32 was pruned out of every install and slide
    cues could never fire — while the dev tree, where this was tested, had it.
    Reported with the slideshow visibly running behind the message.

    Empty string means nothing is blocking; he simply has not found a show.
    """
    system = platform.system()
    if system == "Windows":
        try:
            import win32com.client  # noqa: F401, PLC0415 — probe, not a use
        except Exception:  # noqa: BLE001 — any import failure is the same wall
            return (
                "He cannot read PowerPoint on this install (pywin32 is "
                "missing). Restart AURA so it can finish setting itself up. "
                "Manual and keyword beats work regardless."
            )
    elif system == "Darwin" and not shutil.which("osascript"):
        return (
            "He cannot read Keynote on this Mac (osascript is unavailable). "
            "Manual and keyword beats work regardless."
        )
    return ""


# ---------------------------------------------------------------------------
# The watcher
# ---------------------------------------------------------------------------


class SlidesWatcher:
    """Follows the running slideshow and reports slide changes.

    Unlike its predecessor it runs from the moment the talk starts and keeps
    running: waiting for a slideshow is a normal state, not a failure, and
    "you started the scenario first" must not cost you the whole talk.
    """

    def __init__(self, on_slide: Callable[[int], Awaitable[None]]) -> None:
        self._on_slide = on_slide
        self._task: asyncio.Task | None = None
        self._last_slide: int | None = None
        self._state: SlideState | None = None

    @property
    def state(self) -> SlideState | None:
        return self._state

    @property
    def watching(self) -> bool:
        """True once a slideshow has actually been found."""
        return self._state is not None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                state = await asyncio.to_thread(read_state)
                if state is None:
                    # The show ended or has not started. Forget the last slide
                    # so restarting the deck re-fires its first beat rather
                    # than being swallowed as "no change".
                    if self._state is not None:
                        logger.info("slideshow ended; still watching")
                    self._state = None
                    self._last_slide = None
                else:
                    if self._state is None:
                        logger.info("following %s: %s (%d slides)",
                                    state.app, state.deck or "untitled", state.total)
                    self._state = state
                    if state.slide != self._last_slide:
                        self._last_slide = state.slide
                        await self._on_slide(state.slide)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 — a watcher must not end a talk
                logger.debug("slide watch loop error: %s", exc)
            await asyncio.sleep(_POLL_S)
