"""U396: a brain does not outlive the app that started it.

The desktop shell stops its brain when it quits. A shell that never gets to
quit — killed, crashed, replaced by its own updater — used to leave the brain
running with no window: still listening to the room, still driving the robot,
on code from whenever it was started. The next launch then gave a new brain
the next free port (U234), and two brains answered one robot.

The shell now passes its own pid as ``AURA_PARENT_PID``; the brain watches that
process and stops itself once it is gone. Nobody else passes it: a brain
started by hand, a throwaway stack or CI is watched by nobody.

On Windows the brain holds a handle to the shell from the start, so a pid
reused by some later process cannot pass for the shell — a held handle stays
signalled once its process has exited.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def _alive_check(pid: int) -> Callable[[], bool]:
    """A function that says whether `pid` still runs, bound to it now."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        synchronize, query_limited = 0x00100000, 0x1000
        wait_timeout, invalid_parameter = 0x102, 87
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        handle = k32.OpenProcess(synchronize | query_limited, False, pid)
        if not handle:
            if ctypes.get_last_error() == invalid_parameter:
                return lambda: False          # no such process: already gone
            # Anything else — access denied — cannot tell; never stop on a guess.
            logger.info("cannot watch the app (pid %s); the brain will not stop with it", pid)
            return lambda: True
        return lambda: k32.WaitForSingleObject(handle, 0) == wait_timeout

    def _posix() -> bool:
        try:
            os.kill(pid, 0)                   # signal 0: a question, not a signal
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    return _posix


def _stop_the_brain() -> None:
    """Stop the way Ctrl+C does, so the lifespan's shutdown still runs — the
    voice loop, the robot bridge and the camera stream let go properly. If that
    has not ended the process in fifteen seconds, end it."""
    logger.warning("the desktop app that started this brain is gone — stopping")

    def _last_resort() -> None:
        os._exit(0)

    timer = threading.Timer(15.0, _last_resort)
    timer.daemon = True
    timer.start()
    signal.raise_signal(signal.SIGINT)


async def watch(pid: int, *, every: float = 5.0,
                on_gone: Callable[[], None] = _stop_the_brain) -> None:
    """Return once `pid` has exited, after calling `on_gone`."""
    alive = _alive_check(pid)
    while alive():
        await asyncio.sleep(every)
    on_gone()


def start_from_env() -> asyncio.Task | None:
    """Start watching the app named in ``AURA_PARENT_PID``, if one is named."""
    global _task
    raw = os.environ.get("AURA_PARENT_PID", "").strip()
    try:
        pid = int(raw)
    except ValueError:
        return None
    if pid <= 0:
        return None
    _task = asyncio.ensure_future(watch(pid))
    logger.info("watching the desktop app (pid %s): the brain stops when it does", pid)
    return _task
