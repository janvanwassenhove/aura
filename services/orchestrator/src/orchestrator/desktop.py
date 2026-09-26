"""The desktop rung of the automation ladder — U378.

Asked for as (translated): *"he must be able to go looking by himself (screen
recognition?) to take action, like opening a window or starting Copilot chat —
for all kinds of apps, also Claude desktop or PowerPoint."*

Before this, the ladder went cli → fs → browser → gui. `launch_app` knew seven
allow-listed names; anything else went straight to `use_computer`, which has a
vision model guess pixel coordinates on a screenshot — the slowest and least
reliable rung there is. Measured on the owner's machine: Windows knows 191
installed apps by name, every one launchable without an allow-list, and every
open window has a handle that can be asked for. None of the owner's examples
needs a pixel:

    open PowerPoint / Claude desktop   → find it by name, open it
    bring a window forward             → focus its handle
    start Copilot Chat                 → focus VS Code, press Ctrl+Alt+I

So this module is the rung between cli and gui. Six tools:

    find_app      read-only   which installed apps match a name
    list_windows  read-only   which apps have a window open
    focus_window  benign      bring an open app's window to the front
    open_app      gated       open any installed app (or focus it if open)
    send_keys     gated       press a shortcut in a named app
    type_into     gated       type text into a named app

**The one property that must never break:** `send_keys` and `type_into` press
nothing unless the intended window is verifiably in the foreground at that
moment. A shortcut sent to whatever happens to be in front is the one failure
here that does real damage — Ctrl+Enter sends a mail in Outlook.

Everything platform-specific sits behind a small backend surface (`start_apps`,
`windows`, `launch`, `focus`, `foreground`, `hotkey`, `write_ascii`,
`paste_text`). Windows is implemented here; macOS is the next unit and is a
second backend, not a rewrite. No backend → every tool answers with a U247
marker naming the `desktop` capability, so the model climbs to the next rung
and the skill evidence counts it as the failure it is.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import time
from typing import Any

from shared_schemas.tool_outcome import mark_unavailable

logger = logging.getLogger(__name__)

CAPABILITY = "desktop"

#: The real Start-menu list, refreshed at most every few minutes: a PowerShell
#: round trip costs ~1 s, and apps are not installed between two sentences.
_APPS_CACHE: dict[str, Any] = {}
_APPS_TTL_S = 300.0

#: How long a freshly launched app gets to show its first window.
_WINDOW_WAIT_S = 12.0
_POLL_S = 0.4

#: Names people say → the name the Start menu uses.
_NAME_ALIASES = {
    "vscode": "visual studio code", "vs code": "visual studio code",
    "code": "visual studio code", "ppt": "powerpoint",
    "calc": "calculator", "claude desktop": "claude",
}

#: App → the executable basenames its windows belong to (lowercase, no .exe).
#: Titles are the fallback; an exe is the certain match.
_EXES = {
    "visual studio code": {"code"}, "powerpoint": {"powerpnt"},
    "word": {"winword"}, "excel": {"excel"}, "outlook": {"outlook", "olk"},
    "claude": {"claude"}, "chatgpt": {"chatgpt"}, "chatgpt classic": {"chatgpt"},
    "microsoft teams": {"ms-teams", "teams"}, "teams": {"ms-teams", "teams"},
    "spotify": {"spotify"}, "google chrome": {"chrome"}, "chrome": {"chrome"},
    "notepad": {"notepad"}, "calculator": {"calculatorapp", "calculator"},
}

#: Modifier and key names a shortcut may use. Anything else is refused rather
#: than guessed — a mistyped combination can be a different, real shortcut.
_MODIFIERS = {"ctrl", "alt", "shift", "win", "cmd", "command", "option"}
_MAX_KEYS = 4


def _sleep(seconds: float) -> None:          # a seam: tests do not wait
    time.sleep(seconds)


# ── the backend ────────────────────────────────────────────────────────────

_WINDOWS_BACKEND: Any = None


def _backend() -> Any:
    """The desktop of this machine, or None where there is none to drive."""
    global _WINDOWS_BACKEND
    if sys.platform == "win32":
        if _WINDOWS_BACKEND is None:
            try:
                _WINDOWS_BACKEND = _WindowsDesktop()
            except ImportError as exc:      # pywin32 / pyautogui not installed
                logger.warning("desktop control unavailable: %s", exc)
                return None
        return _WINDOWS_BACKEND
    return None                              # macOS: U379


class _Win:
    def __init__(self, handle: int, title: str, exe: str) -> None:
        self.handle, self.title, self.exe = handle, title, exe


class _WindowsDesktop:
    """Windows, through PowerShell's Start list, pywin32 and pyautogui."""

    def __init__(self) -> None:
        import pyautogui  # noqa: F401 — fail here, not mid-action
        import win32gui  # noqa: F401

    def start_apps(self) -> list[dict]:
        now = time.monotonic()
        if _APPS_CACHE.get("apps") and now - _APPS_CACHE.get("at", 0) < _APPS_TTL_S:
            return list(_APPS_CACHE["apps"])
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                  "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False)
        data = json.loads(out.stdout or "[]") if out.stdout.strip() else []
        apps = [data] if isinstance(data, dict) else list(data)
        apps = [a for a in apps if a.get("Name") and a.get("AppID")]
        _APPS_CACHE.update({"apps": apps, "at": now})
        return list(apps)

    def windows(self) -> list[_Win]:
        import win32gui

        found: list[_Win] = []

        def visit(handle: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(handle):
                return True
            title = win32gui.GetWindowText(handle)
            if title.strip():
                found.append(_Win(handle, title, _exe_of(handle)))
            return True

        win32gui.EnumWindows(visit, None)
        return found

    def launch(self, app_id: str) -> None:
        # explorer resolves AppIDs of both packaged and classic desktop apps;
        # argv list, no shell, and the id comes from Windows' own list.
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"],  # noqa: S603, S607
                         close_fds=True)

    def focus(self, handle: int) -> bool:
        import ctypes

        import win32con
        import win32gui

        try:
            if win32gui.IsIconic(handle):
                win32gui.ShowWindow(handle, win32con.SW_RESTORE)
            # Windows only lets the process with the last input set the
            # foreground window; a released Alt satisfies that rule.
            user32 = ctypes.windll.user32
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            win32gui.SetForegroundWindow(handle)
            return True
        except Exception as exc:  # noqa: BLE001 — a refusal is an answer
            logger.info("desktop: focus refused for %s: %s", handle, exc)
            return False

    def foreground(self) -> int | None:
        import win32gui

        return win32gui.GetForegroundWindow() or None

    def hotkey(self, *keys: str) -> None:
        import pyautogui

        pyautogui.hotkey(*keys)

    def write_ascii(self, text: str) -> None:
        import pyautogui

        pyautogui.write(text, interval=0.01)

    def paste_text(self, text: str) -> None:
        """Text a keyboard cannot type (é, ë, ü) goes via the clipboard, and
        whatever text the owner had there is put back afterwards."""
        import pyautogui
        import win32clipboard as cb
        import win32con

        previous: str | None = None
        cb.OpenClipboard()
        try:
            if cb.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previous = cb.GetClipboardData(win32con.CF_UNICODETEXT)
            cb.EmptyClipboard()
            cb.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            cb.CloseClipboard()
        pyautogui.hotkey("ctrl", "v")
        _sleep(0.3)
        if previous is not None:
            cb.OpenClipboard()
            try:
                cb.EmptyClipboard()
                cb.SetClipboardData(win32con.CF_UNICODETEXT, previous)
            finally:
                cb.CloseClipboard()


def _exe_of(handle: int) -> str:
    """The executable behind a window, or "" — never raises."""
    try:
        import ctypes
        from ctypes import wintypes

        import win32process

        _, pid = win32process.GetWindowThreadProcessId(handle)
        k32 = ctypes.windll.kernel32
        proc = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if not proc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if k32.QueryFullProcessImageNameW(proc, 0, buf, ctypes.byref(size)):
                return buf.value
        finally:
            k32.CloseHandle(proc)
    except Exception:  # noqa: BLE001
        pass
    return ""


# ── matching ───────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    q = " ".join((name or "").lower().split())
    return _NAME_ALIASES.get(q, q)


def match_apps(query: str) -> list[dict]:
    """Installed apps for a spoken name, best first. Launches nothing."""
    b = _backend()
    if b is None:
        return []
    q = _norm(query)
    if not q:
        return []
    ranked: list[tuple[int, str, dict]] = []
    for app in b.start_apps():
        name = app["Name"].lower()
        if name == q:
            score = 0
        elif name.startswith(q):
            score = 1
        elif q in name.split():
            score = 2
        elif q in name:
            score = 3
        elif q.replace(" ", "") in app["AppID"].lower().replace(" ", ""):
            # U378: the Start list is localized — on the owner's Dutch Windows
            # 'calculator' is 'Rekenmachine' — but the AppID is not
            # (Microsoft.WindowsCalculator_…). Found live, not guessed.
            score = 4
        else:
            continue
        ranked.append((score, name, app))
    ranked.sort(key=lambda t: (t[0], len(t[1])))
    return [app for _, _, app in ranked]


def _exe_base(path: str) -> str:
    base = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _windows_for(query: str, b: Any) -> list[Any]:
    """Open windows belonging to an app, by executable first and title second."""
    q = _norm(query)
    exes = set(_EXES.get(q, set()))
    display = {q}
    for app in (match_apps(query) or [])[:1]:
        display.add(app["Name"].lower())
        exes |= _EXES.get(app["Name"].lower(), set())
    hits = []
    for w in b.windows():
        title = (w.title or "").lower()
        if (exes and _exe_base(w.exe) in exes) or any(
                title == d or title.endswith(f" - {d}") for d in display):
            hits.append(w)
    return hits


def _focus_verified(b: Any, handle: int) -> bool:
    """Bring a window forward AND confirm it is the one in front."""
    if not b.focus(handle):
        return False
    _sleep(0.15)
    return b.foreground() == handle


def _parse_keys(keys: str) -> list[str] | None:
    parts = [p.strip().lower() for p in (keys or "").split("+")]
    if not parts or any(not p for p in parts) or len(parts) > _MAX_KEYS:
        return None
    *mods, last = parts
    if any(m not in _MODIFIERS for m in mods):
        return None
    return parts


def _unavailable(message: str) -> str:
    return mark_unavailable(CAPABILITY, message)


_NO_DESKTOP = ("[desktop: there is no desktop to drive on this machine (not "
               "Windows, or the screen-control components are not installed). "
               "Use use_computer, or ask the owner.]")


# ── the tools ──────────────────────────────────────────────────────────────

async def find_app(query: str) -> str:
    return await asyncio.to_thread(_find_app, query)


def _find_app(query: str) -> str:
    if _backend() is None:
        return _unavailable(_NO_DESKTOP)
    matches = match_apps(query)
    if not matches:
        return (f"[find_app: {query!r} is not installed on this laptop. "
                f"Try another name the owner might use for it.]")
    names = ", ".join(dict.fromkeys(a["Name"] for a in matches[:6]))
    return f"Installed and openable with open_app: {names}."


async def list_windows() -> str:
    return await asyncio.to_thread(_list_windows)


def _list_windows() -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    rows = [f"{_exe_base(w.exe) or '?'}: {w.title[:80]}" for w in b.windows()]
    return "Open windows — " + ("; ".join(rows) if rows else "none") + "."


async def focus_window(app: str) -> str:
    return await asyncio.to_thread(_focus_window, app)


def _focus_window(app: str) -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    wins = _windows_for(app, b)
    if not wins:
        return (f"[focus_window: {app} is not open. open_app({app!r}) starts it "
                f"and brings it to the front.]")
    if _focus_verified(b, wins[0].handle):
        return f"{app} is in front now ({wins[0].title[:60]})."
    return _unavailable(f"[focus_window: Windows would not bring {app} to the front. "
                        f"Try again, or use_computer to click its taskbar button.]")


async def open_app(name: str) -> str:
    return await asyncio.to_thread(_open_app, name)


def _open_app(name: str) -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    already = _windows_for(name, b)
    if already:
        if _focus_verified(b, already[0].handle):
            return f"{name} was already open — brought it to the front."
        return _unavailable(f"[open_app: {name} is already open, but Windows would "
                            f"not bring it to the front.]")
    matches = match_apps(name)
    if not matches:
        return (f"[open_app: nothing called {name!r} is installed. find_app lists "
                f"what is — try the name the owner might use for it.]")
    chosen = matches[0]
    before = {w.handle for w in b.windows()}
    logger.info("desktop: opening %r (%s)", chosen["Name"], chosen["AppID"])
    b.launch(chosen["AppID"])
    others = [a for a in matches[1:] if a["Name"].lower() == chosen["Name"].lower()]
    note = (f" (another {chosen['Name']} is also installed; say if that one was meant)"
            if others else "")

    waited = 0.0
    while waited <= _WINDOW_WAIT_S:
        fresh = [w for w in _windows_for(chosen["Name"], b) if w.handle not in before]
        if fresh:
            if _focus_verified(b, fresh[0].handle):
                return f"Opened {chosen['Name']} — its window is in front{note}."
            return f"Opened {chosen['Name']}, but it did not come to the front{note}."
        _sleep(_POLL_S)
        waited += _POLL_S
    return (f"Started {chosen['Name']}, but no window appeared within "
            f"{_WINDOW_WAIT_S:.0f}s — it may still be loading or live in the tray{note}.")


async def send_keys(app: str, keys: str) -> str:
    return await asyncio.to_thread(_send_keys, app, keys)


def _send_keys(app: str, keys: str) -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    parsed = _parse_keys(keys)
    if parsed is None:
        return (f"[send_keys: {keys!r} is not a key combination I will press. Use "
                f"modifiers joined by + and one key, e.g. 'ctrl+alt+i' or 'f5'.]")
    wins = _windows_for(app, b)
    if not wins:
        return f"[send_keys: {app} is not open, so nothing was pressed. open_app first.]"
    # THE property: verified in front, immediately before pressing.
    if not _focus_verified(b, wins[0].handle):
        logger.warning("desktop: %s not in front — refused to press %s", app, keys)
        return _unavailable(f"[send_keys: {app} could not be brought to the front, so "
                            f"nothing was pressed — keys never go to the wrong window.]")
    b.hotkey(*parsed)
    logger.info("desktop: pressed %s in %s", "+".join(parsed), app)
    return f"Pressed {'+'.join(parsed)} in {app}."


async def type_into(app: str, text: str) -> str:
    return await asyncio.to_thread(_type_into, app, text)


def _type_into(app: str, text: str) -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    if not text:
        return "[type_into: there is no text to type.]"
    wins = _windows_for(app, b)
    if not wins:
        return f"[type_into: {app} is not open, so nothing was typed. open_app first.]"
    if not _focus_verified(b, wins[0].handle):
        logger.warning("desktop: %s not in front — refused to type", app)
        return _unavailable(f"[type_into: {app} could not be brought to the front, so "
                            f"nothing was typed — text never goes to the wrong window.]")
    if text.isascii():
        b.write_ascii(text)
    else:
        b.paste_text(text)
    logger.info("desktop: typed %d characters into %s", len(text), app)
    return f"Typed {len(text)} characters into {app}."


DESKTOP_TOOLS = {
    "find_app": lambda a: find_app(a.get("name", "")),
    "list_windows": lambda a: list_windows(),
    "focus_window": lambda a: focus_window(a.get("app", "")),
    "open_app": lambda a: open_app(a.get("name", "")),
    "send_keys": lambda a: send_keys(a.get("app", ""), a.get("keys", "")),
    "type_into": lambda a: type_into(a.get("app", ""), a.get("text", "")),
}

__all__ = ["DESKTOP_TOOLS", "find_app", "focus_window", "list_windows",
           "match_apps", "open_app", "send_keys", "type_into"]
