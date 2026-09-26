"""U378: he finds his own way on the desktop — any app, its window, its keys.

Asked, after U377 (translated): *"but he must also be able to go looking by
himself (screen recognition?) to take action, like opening a window or starting
Copilot chat — for all kinds of apps, also Claude desktop or PowerPoint."*

What existed: `launch_app` for seven allow-listed names, and `use_computer`,
which screenshots the screen and has gpt-4o guess pixel coordinates. The
automation ladder went cli → fs → browser → gui with nothing in between, so
anything beyond the seven names went straight to the slowest, least reliable
rung there is.

What was measured on the owner's machine before designing anything: Windows
knows **191** installed apps by name (`Get-StartApps`) — PowerPoint, Claude,
VS Code, ChatGPT, Word, Excel, Outlook, Teams among them — each launchable as
`shell:AppsFolder\\<AppID>` with no allow-list and no screenshot; and the app's
own Python can enumerate every open window (pywin32 is installed). None of the
owner's three examples needs a pixel:

* open PowerPoint / Claude desktop     → find it by name, open it
* bring a window forward               → it has a handle; ask for it
* start Copilot Chat                   → focus VS Code, press Ctrl+Alt+I

So there is a **desktop** rung now, between cli and gui. These tests pin its
behaviour against a fake Windows (CI is Linux), plus two read-only checks
against the real one.

The single most important property is at the bottom of the "acting" section:
**nothing is pressed or typed unless the intended window is verifiably in front
at that moment.** A shortcut sent to the wrong window is the one failure here
that can do real damage — Ctrl+Enter sends a mail in Outlook.
"""

from __future__ import annotations

import os
import shutil

import pytest
from orchestrator import desktop
from shared_schemas.tool_outcome import unavailable_capability


class Win:
    def __init__(self, handle: int, title: str, exe: str) -> None:
        self.handle, self.title, self.exe = handle, title, exe


class FakeWindows:
    """A Windows desktop that does exactly what it is told, and records it."""

    def __init__(self) -> None:
        self.apps = [
            {"Name": "PowerPoint", "AppID": "Microsoft.Office.POWERPNT.EXE.15"},
            {"Name": "Claude", "AppID": "Claude_pzs8sxrjxfjjc!Claude"},
            {"Name": "Visual Studio Code", "AppID": "Microsoft.VisualStudioCode"},
            {"Name": "Outlook", "AppID": "Microsoft.Office.OUTLOOK.EXE.15"},
            {"Name": "Outlook", "AppID": "Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows"},
            {"Name": "Calculator", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
        ]
        self.open: list[Win] = [Win(1, "Inbox - Outlook", r"C:\Office\OUTLOOK.EXE")]
        self.fg: int | None = 1
        self.launched: list[str] = []
        self.pressed: list[tuple[str, ...]] = []
        self.pasted: list[str] = []
        self.typed: list[str] = []
        self.focus_works = True
        self.on_launch = {
            "Microsoft.Office.POWERPNT.EXE.15": Win(7, "Presentation1 - PowerPoint", r"C:\Office\POWERPNT.EXE"),
            "Claude_pzs8sxrjxfjjc!Claude": Win(8, "Claude", r"C:\Apps\claude.exe"),
            "Microsoft.VisualStudioCode": Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"),
        }

    # the backend surface desktop.py drives
    def start_apps(self) -> list[dict]:
        return list(self.apps)

    def windows(self) -> list[Win]:
        return list(self.open)

    def launch(self, app_id: str) -> None:
        self.launched.append(app_id)
        w = self.on_launch.get(app_id)
        if w is not None:
            self.open.append(w)

    def focus(self, handle: int) -> bool:
        if self.focus_works:
            self.fg = handle
        return self.focus_works

    def foreground(self) -> int | None:
        return self.fg

    def hotkey(self, *keys: str) -> None:
        self.pressed.append(keys)

    def paste_text(self, text: str) -> None:
        self.pasted.append(text)

    def write_ascii(self, text: str) -> None:
        self.typed.append(text)


@pytest.fixture()
def win(monkeypatch):
    fake = FakeWindows()
    monkeypatch.setattr(desktop, "_backend", lambda: fake)
    monkeypatch.setattr(desktop, "_sleep", lambda s: None)   # no real waiting
    desktop._APPS_CACHE.clear()
    return fake


# ── finding ────────────────────────────────────────────────────────────────

async def test_find_app_finds_by_name_and_launches_nothing(win) -> None:
    reply = await desktop.find_app("powerpoint")
    assert "PowerPoint" in reply
    assert win.launched == [], "finding must never start anything"


async def test_an_exact_name_ranks_above_a_partial_one(win) -> None:
    win.apps.append({"Name": "PowerPoint Viewer Legacy", "AppID": "x!legacy"})
    matches = desktop.match_apps("powerpoint")
    assert matches[0]["Name"] == "PowerPoint"


async def test_nothing_installed_is_said_plainly_not_as_a_fault(win) -> None:
    reply = await desktop.find_app("photoshop")
    assert "photoshop" in reply.lower() and "not installed" in reply.lower()
    assert unavailable_capability(reply) is None, "an absent app is an answer, not a broken capability"


async def test_list_windows_names_what_is_open(win) -> None:
    reply = await desktop.list_windows()
    assert "Outlook" in reply


# ── opening ────────────────────────────────────────────────────────────────

async def test_open_app_opens_any_installed_app_by_name(win) -> None:
    """PowerPoint was never on the allow-list. It does not need to be."""
    reply = await desktop.open_app("PowerPoint")
    assert win.launched == ["Microsoft.Office.POWERPNT.EXE.15"]
    assert win.fg == 7, "the new window must end up in front"
    assert "PowerPoint" in reply and "front" in reply.lower()


async def test_an_app_that_is_already_open_is_brought_forward_not_started_twice(win) -> None:
    reply = await desktop.open_app("outlook")
    assert win.launched == [], "a second Outlook is not what 'open Outlook' means"
    assert win.fg == 1
    assert "already open" in reply.lower()


async def test_claude_desktop_opens_the_same_way(win) -> None:
    await desktop.open_app("claude")
    assert win.launched == ["Claude_pzs8sxrjxfjjc!Claude"]
    assert win.fg == 8


async def test_an_ambiguous_name_says_which_one_it_chose(win) -> None:
    win.open.clear()
    reply = await desktop.open_app("outlook")
    assert len(win.launched) == 1
    assert "also installed" in reply.lower() or "other" in reply.lower()


async def test_an_app_that_never_shows_a_window_is_reported_honestly(win) -> None:
    """Started is not the same as visible. Constitution XI."""
    win.on_launch.pop("Microsoft.Office.POWERPNT.EXE.15")
    reply = await desktop.open_app("powerpoint")
    assert win.launched == ["Microsoft.Office.POWERPNT.EXE.15"]
    assert "no window" in reply.lower()


async def test_focus_window_brings_an_open_app_forward(win) -> None:
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    reply = await desktop.focus_window("vscode")
    assert win.fg == 9 and "front" in reply.lower()


async def test_focus_window_on_an_app_that_is_not_open_says_so_and_how(win) -> None:
    reply = await desktop.focus_window("powerpoint")
    assert "not open" in reply.lower() and "open_app" in reply


# ── acting: never into the wrong window ────────────────────────────────────

async def test_send_keys_starts_copilot_chat_in_vscode(win) -> None:
    """The owner's own example: focus VS Code, press Ctrl+Alt+I."""
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    reply = await desktop.send_keys("vscode", "ctrl+alt+i")
    assert win.pressed == [("ctrl", "alt", "i")]
    assert win.fg == 9
    assert "ctrl+alt+i" in reply.lower()


async def test_nothing_is_pressed_if_the_window_would_not_come_forward(win) -> None:
    """THE property. Ctrl+Enter in the wrong window sends a mail."""
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    win.focus_works = False
    reply = await desktop.send_keys("vscode", "ctrl+alt+i")
    assert win.pressed == [], "keys were sent to whatever happened to be in front"
    assert unavailable_capability(reply) is not None


async def test_nothing_is_pressed_if_something_else_stole_focus(win, monkeypatch) -> None:
    """Focus can succeed and be lost before the keys go out (a notification,
    a dialog). The check is made immediately before pressing, not once."""
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    real_focus = win.focus

    def focus_then_lose(handle: int) -> bool:
        ok = real_focus(handle)
        win.fg = 1                      # Outlook pops up in between
        return ok

    win.focus = focus_then_lose
    await desktop.send_keys("vscode", "ctrl+enter")
    assert win.pressed == []


async def test_send_keys_to_an_app_that_is_not_open_presses_nothing(win) -> None:
    reply = await desktop.send_keys("powerpoint", "ctrl+m")
    assert win.pressed == [] and "not open" in reply.lower()


@pytest.mark.parametrize("keys", ["", "+", "ctrl++", "ctrl+alt+shift+win+x+y"])
async def test_nonsense_key_combinations_are_refused(win, keys) -> None:
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    await desktop.send_keys("vscode", keys)
    assert win.pressed == []


async def test_type_into_types_ascii_directly(win) -> None:
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    await desktop.type_into("vscode", "explain this repo")
    assert win.typed == ["explain this repo"] and win.pasted == []


async def test_type_into_pastes_text_a_keyboard_cannot_type(win) -> None:
    """Dutch text has é, ë, ü — pyautogui.write drops them silently."""
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    await desktop.type_into("vscode", "leg uit wat één functie doet")
    assert win.pasted == ["leg uit wat één functie doet"] and win.typed == []


async def test_type_into_the_wrong_window_types_nothing(win) -> None:
    win.open.append(Win(9, "aura - Visual Studio Code", r"C:\VSCode\Code.exe"))
    win.focus_works = False
    await desktop.type_into("vscode", "hello")
    assert win.typed == [] and win.pasted == []


# ── without Windows ────────────────────────────────────────────────────────

async def test_without_a_desktop_backend_every_tool_says_so(monkeypatch) -> None:
    monkeypatch.setattr(desktop, "_backend", lambda: None)
    for reply in (await desktop.find_app("x"), await desktop.open_app("x"),
                  await desktop.list_windows(), await desktop.focus_window("x"),
                  await desktop.send_keys("x", "ctrl+s"), await desktop.type_into("x", "y")):
        assert unavailable_capability(reply) == "desktop", reply


# ── wired into the policy exactly like launch_app ──────────────────────────

NEW = ("find_app", "open_app", "list_windows", "focus_window", "send_keys", "type_into")


def test_each_tool_has_a_schema_a_layer_and_a_group() -> None:
    from orchestrator import mode_policy
    from orchestrator.tool_schemas import TOOL_LAYERS, TOOL_SCHEMAS

    screen = next(g for g in mode_policy.TOOL_GROUPS if g[0] == "screen control")[3]
    for name in NEW:
        assert name in TOOL_SCHEMAS, name
        assert TOOL_LAYERS.get(name) == "desktop", name
        assert name in screen, f"{name} must follow the owner's screen-control setting"


def test_what_acts_asks_and_what_only_looks_does_not() -> None:
    from shared_policies import APPROVAL_REQUIRED

    for name in ("open_app", "send_keys", "type_into"):
        assert name in APPROVAL_REQUIRED, f"{name} changes the owner's desktop"
    for name in ("find_app", "list_windows", "focus_window"):
        assert name not in APPROVAL_REQUIRED, f"{name} should not cost a card"


def test_the_modes_that_allow_launch_app_allow_the_desktop_rung_and_no_others() -> None:
    from shared_policies import MODE_TOOL_MAP

    for mode, tools in MODE_TOOL_MAP.items():
        for name in NEW:
            assert (name in tools) == ("launch_app" in tools), (mode, name)


def test_the_ladder_puts_the_desktop_before_the_screen() -> None:
    from orchestrator.tool_schemas import LADDER_NOTE

    assert "desktop" in LADDER_NOTE
    assert LADDER_NOTE.index("desktop") < LADDER_NOTE.index("use_computer")
    assert "open_app" in LADDER_NOTE and "send_keys" in LADDER_NOTE


def test_the_vscode_skill_starts_copilot_chat_with_a_shortcut() -> None:
    from orchestrator.builtin_skills import BUILTIN_SKILLS

    body = next(s.body for s in BUILTIN_SKILLS if s.name == "desktop-vscode")
    assert "send_keys('vscode', 'ctrl+alt+i')" in body


# ── the real Windows, read-only ────────────────────────────────────────────

def _real_desktop() -> bool:
    """Windows AND the screen-control components (pyautogui, pywin32) — the
    packaged app has them; a dev venv synced without the extras does not, and
    there the product rightly answers "unavailable" instead."""
    import importlib.util as u

    return (os.name == "nt" and shutil.which("powershell") is not None
            and u.find_spec("pyautogui") is not None and u.find_spec("win32gui") is not None)


@pytest.mark.skipif(not _real_desktop(), reason="needs Windows with the desktop components")
async def test_the_real_start_menu_is_readable() -> None:
    desktop._APPS_CACHE.clear()
    apps = desktop._backend().start_apps()
    assert len(apps) > 10 and all("AppID" in a for a in apps)


@pytest.mark.skipif(not _real_desktop(), reason="needs Windows with the desktop components")
async def test_the_real_windows_are_listable() -> None:
    wins = desktop._backend().windows()
    assert wins, "a Windows session with no visible window at all is not plausible"


# ── a Dutch Windows (found live on the owner's machine) ────────────────────

async def test_a_localized_app_is_found_by_its_language_independent_id(win) -> None:
    """The first live run asked for 'calculator' and got "not installed". The
    owner's Windows is Dutch: the Start list says 'Rekenmachine'. Office keeps
    its English names, which is why PowerPoint worked and this did not. The
    AppID does not translate — match on it after the name."""
    win.apps = [{"Name": "Rekenmachine", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
                {"Name": "Kladblok", "AppID": "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"}]
    assert desktop.match_apps("calculator")[0]["Name"] == "Rekenmachine"
    assert desktop.match_apps("notepad")[0]["Name"] == "Kladblok"


async def test_a_name_match_still_ranks_above_an_id_match(win) -> None:
    win.apps = [{"Name": "Claude", "AppID": "Claude_x!Claude"},
                {"Name": "Something", "AppID": "Vendor.ClaudeHelper_y!App"}]
    assert desktop.match_apps("claude")[0]["Name"] == "Claude"


async def test_a_localized_window_is_found_by_its_localized_title(win) -> None:
    """Packaged apps live under ApplicationFrameHost.exe, so the exe says
    nothing; the title is in the owner's language."""
    win.apps = [{"Name": "Rekenmachine", "AppID": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"}]
    win.open = [Win(4, "Rekenmachine", r"C:\Windows\System32\ApplicationFrameHost.exe")]
    reply = await desktop.focus_window("calculator")
    assert win.fg == 4 and "front" in reply.lower()
