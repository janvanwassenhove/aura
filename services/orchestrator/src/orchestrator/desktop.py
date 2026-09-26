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
import os
import plistlib
import re
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

#: U379: the FINAL key comes from this list too. It used to be free text from
#: the model; on Windows pyautogui ignores a name it does not know, but on a
#: Mac the key lands inside an AppleScript, and a "key" like
#: `a" & do shell script "…` is a shell command. Single safe characters (no
#: quote, no backslash) or named keys — nothing else, on either platform.
_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789,./;[]-=`")
_MAC_KEY_CODES = {
    "enter": 36, "return": 36, "tab": 48, "space": 49, "backspace": 51,
    "delete": 117, "escape": 53, "esc": 53, "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121, "left": 123, "right": 124, "down": 125,
    "up": 126, "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
_NAMED_KEYS = set(_MAC_KEY_CODES)


def _sleep(seconds: float) -> None:          # a seam: tests do not wait
    time.sleep(seconds)


# ── the backend ────────────────────────────────────────────────────────────

class DesktopPermissionError(RuntimeError):
    """The OS refused: the owner has to grant something by hand. `advice` says
    exactly what and where, so the reply is an instruction, not a mystery."""

    def __init__(self, advice: str) -> None:
        super().__init__(advice)
        self.advice = advice


_WINDOWS_BACKEND: Any = None
_MAC_BACKEND: Any = None


def _backend() -> Any:
    """The desktop of this machine, or None where there is none to drive."""
    global _WINDOWS_BACKEND, _MAC_BACKEND
    if sys.platform == "win32":
        if _WINDOWS_BACKEND is None:
            try:
                _WINDOWS_BACKEND = _WindowsDesktop()
            except ImportError as exc:      # pywin32 / pyautogui not installed
                logger.warning("desktop control unavailable: %s", exc)
                return None
        return _WINDOWS_BACKEND
    if sys.platform == "darwin":            # U379: built into every Mac
        if _MAC_BACKEND is None:
            _MAC_BACKEND = _MacDesktop()
        return _MAC_BACKEND
    return None


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

    _PYAUTOGUI = {"cmd": "win", "command": "win", "option": "alt",
                  "return": "enter", "esc": "escape"}

    def hotkey(self, *keys: str) -> None:
        import pyautogui

        pyautogui.hotkey(*(self._PYAUTOGUI.get(k, k) for k in keys))

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


def _run_cmd(argv: list[str], stdin: str | None = None) -> Any:
    """argv only — never a shell. stdin carries text, so text is never an argument."""
    return subprocess.run(argv, input=stdin, capture_output=True, text=True,  # noqa: S603
                          timeout=20, check=False)


_BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*$")

_MAC_PERMISSION = (
    "[desktop: macOS has not given AURA permission to control other apps. "
    "Open System Settings → Privacy & Security → Accessibility and allow AURA "
    "(and, under Automation, allow it to control System Events), then try "
    "again. Until then use_computer cannot help either — it needs the same "
    "permission.]")

_MAC_MODIFIERS = {"ctrl": "control down", "alt": "option down", "option": "option down",
                  "shift": "shift down", "cmd": "command down",
                  "command": "command down", "win": "command down"}

_WINDOWS_SCRIPT = """
const se = Application("System Events");
const out = [];
for (const p of se.applicationProcesses.whose({visible: true})()) {
  let bid = ""; try { bid = p.bundleIdentifier() || ""; } catch (e) {}
  let titles = []; try { titles = p.windows.name(); } catch (e) {}
  for (const t of titles) { if (t) out.push({bid: bid, app: p.name(), title: t}); }
}
JSON.stringify(out);
"""

_FRONT_SCRIPT = """
const f = Application("System Events").applicationProcesses.whose({frontmost: true})();
f.length ? (f[0].bundleIdentifier() || "") : "";
"""


class _MacDesktop:
    """macOS, with nothing that is not already on every Mac (U379).

    Apps come from the bundles themselves; launching is `open -b`; windows,
    focus and keys go through System Events, which is the one part that needs
    the owner's Accessibility permission — and says so by name when it is
    missing. A Mac focuses applications, not windows, so a window's handle is
    its app's bundle id: `foreground() == handle` is still the check that
    keys never go to the wrong app.
    """

    ROOTS = ("/Applications", "/Applications/Utilities", "/System/Applications",
             "/System/Applications/Utilities", "~/Applications")

    def __init__(self, run: Any = None, roots: Any = None) -> None:
        self._run = run or _run_cmd
        self._roots = [os.path.expanduser(str(r)) for r in (roots or self.ROOTS)]

    # -- apps ------------------------------------------------------------------
    def start_apps(self) -> list[dict]:
        now = time.monotonic()
        if _APPS_CACHE.get("apps") and now - _APPS_CACHE.get("at", 0) < _APPS_TTL_S:
            return list(_APPS_CACHE["apps"])
        apps: list[dict] = []
        seen: set[str] = set()
        for root in self._roots:
            for bundle in self._bundles(root):
                app = self._read(bundle)
                if app and app["AppID"] not in seen:
                    seen.add(app["AppID"])
                    apps.append(app)
        _APPS_CACHE.update({"apps": apps, "at": now})
        return list(apps)

    @staticmethod
    def _bundles(root: str) -> list[str]:
        if not os.path.isdir(root):
            return []
        found = []
        for entry in sorted(os.listdir(root)):
            path = os.path.join(root, entry)
            if entry.endswith(".app"):
                found.append(path)
            elif os.path.isdir(path):         # e.g. /Applications/Microsoft Office/
                found += [os.path.join(path, e) for e in sorted(os.listdir(path))
                          if e.endswith(".app")]
        return found

    @staticmethod
    def _read(bundle: str) -> dict | None:
        try:
            with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as fh:
                info = plistlib.load(fh)
        except (OSError, ValueError, plistlib.InvalidFileException):
            return None
        bid = str(info.get("CFBundleIdentifier") or "")
        if not bid:
            return None
        name = (info.get("CFBundleDisplayName") or info.get("CFBundleName")
                or os.path.basename(bundle)[:-4])
        return {"Name": str(name), "AppID": bid}

    def launch(self, app_id: str) -> None:
        self._run(["open", "-b", app_id])

    # -- System Events -----------------------------------------------------------
    def _osa(self, script: str, lang: str = "JavaScript") -> str:
        argv = ["osascript", "-l", lang, "-e", script] if lang == "JavaScript" \
            else ["osascript", "-e", script]
        r = self._run(argv)
        if r.returncode != 0:
            err = r.stderr or ""
            if any(m in err for m in ("-1719", "-1743", "assistive access",
                                      "Not authorized to send Apple events")):
                raise DesktopPermissionError(_MAC_PERMISSION)
            raise RuntimeError(f"osascript failed: {err.strip()[:200]}")
        return (r.stdout or "").strip()

    def windows(self) -> list[_Win]:
        raw = self._osa(_WINDOWS_SCRIPT)
        rows = json.loads(raw) if raw else []
        return [_Win(r.get("bid", ""), r.get("title", ""), r.get("bid", "")) for r in rows]

    def focus(self, handle: str) -> bool:
        if not isinstance(handle, str) or not _BUNDLE_ID.match(handle):
            logger.warning("desktop: refused to focus a malformed bundle id")
            return False
        try:
            self._osa(f'tell application id "{handle}" to activate', "AppleScript")
            return True
        except DesktopPermissionError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.info("desktop: activate failed for %s: %s", handle, exc)
            return False

    def foreground(self) -> str | None:
        return self._osa(_FRONT_SCRIPT) or None

    def hotkey(self, *keys: str) -> None:
        *mods, key = keys                     # already validated by _parse_keys
        using = (" using {" + ", ".join(_MAC_MODIFIERS[m] for m in mods) + "}") if mods else ""
        action = (f"key code {_MAC_KEY_CODES[key]}" if key in _MAC_KEY_CODES
                  else f'keystroke "{key}"')
        self._osa(f'tell application "System Events" to {action}{using}', "AppleScript")

    def paste_text(self, text: str) -> None:
        """Through the clipboard on stdin: the text is never an argument and
        never inside a script, so there is nothing to escape and nothing to
        inject. The owner's clipboard text is put back afterwards."""
        previous = self._run(["pbpaste"]).stdout
        self._run(["pbcopy"], stdin=text)
        self._osa('tell application "System Events" to keystroke "v" using {command down}',
                  "AppleScript")
        _sleep(0.3)
        self._run(["pbcopy"], stdin=previous or "")

    def write_ascii(self, text: str) -> None:
        self.paste_text(text)                 # same path: nothing is ever embedded


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
    ids: set[str] = set()
    for app in (match_apps(query) or [])[:1]:
        display.add(app["Name"].lower())
        exes |= _EXES.get(app["Name"].lower(), set())
        ids.add(app["AppID"].lower())
    hits = []
    for w in b.windows():
        title = (w.title or "").lower()
        if (exes and _exe_base(w.exe) in exes) or (w.exe or "").lower() in ids or any(
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
    if not (last in _NAMED_KEYS or (len(last) == 1 and last in _SAFE_CHARS)):
        return None
    return parts


def _unavailable(message: str) -> str:
    return mark_unavailable(CAPABILITY, message)


_NO_DESKTOP = ("[desktop: there is no desktop to drive on this machine (not "
               "Windows, or the screen-control components are not installed). "
               "Use use_computer, or ask the owner.]")


# ── the tools ──────────────────────────────────────────────────────────────

def _guarded(fn):
    """A permission refusal becomes the instruction that fixes it; any other
    fault becomes a marked failure — never a traceback in the owner's chat."""
    def wrapper(*args: Any) -> str:
        try:
            return fn(*args)
        except DesktopPermissionError as exc:
            return _unavailable(exc.advice)
        except Exception as exc:  # noqa: BLE001
            logger.warning("desktop: %s failed: %s", fn.__name__, exc)
            return _unavailable(f"[desktop: {fn.__name__.lstrip('_')} failed — {exc}]")
    wrapper.__name__ = fn.__name__
    return wrapper


async def find_app(query: str) -> str:
    return await asyncio.to_thread(_find_app, query)


@_guarded
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


@_guarded
def _list_windows() -> str:
    b = _backend()
    if b is None:
        return _unavailable(_NO_DESKTOP)
    rows = [f"{_exe_base(w.exe) or '?'}: {w.title[:80]}" for w in b.windows()]
    return "Open windows — " + ("; ".join(rows) if rows else "none") + "."


async def focus_window(app: str) -> str:
    return await asyncio.to_thread(_focus_window, app)


@_guarded
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


@_guarded
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


@_guarded
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


@_guarded
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
