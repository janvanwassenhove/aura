"""U379: the same desktop rung on a Mac.

Asked while U378 was being built (translated): *"then make sure the same is
possible on Mac."* U378 put every platform call behind one backend surface for
exactly this; this is the second backend.

macOS gives the same handles without a single new dependency:

    installed apps     every *.app under /Applications & co, named by its
                       Info.plist (CFBundleName, CFBundleIdentifier)
    launch             `open -b <bundle id>`
    windows / focus /  System Events through `osascript` — the one part that
    foreground / keys  needs the owner's permission (Privacy & Security →
                       Accessibility), and says so by name when it is missing
    text               `pbcopy` through stdin, then Cmd+V — never an argument,
                       never inside a script, so there is nothing to escape

This file cannot run on a Mac from here: it pins the exact commands against a
fake runner on any OS, and `checks.yml` gains a macOS job that runs the
read-only half against a real one on every push.

**A hole found while designing this, closed on both platforms.** `send_keys`
validated the modifiers, but the final key was free text from the model. On
Windows pyautogui ignores a name it does not know; on a Mac that string lands
inside an AppleScript — and a "key" like `a" & do shell script "…` is a shell
command. The final key now comes from a fixed list everywhere.
"""

from __future__ import annotations

import json
import plistlib
import sys

import pytest
from orchestrator import desktop
from shared_schemas.tool_outcome import unavailable_capability


class Run:
    """A fake of subprocess: records argv (and stdin), answers per command."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.windows: list[dict] = []
        self.front = ""
        self.clipboard = "what the owner had copied"
        self.denied = False

    def __call__(self, argv: list[str], stdin: str | None = None):
        self.calls.append((list(argv), stdin))
        out, rc, err = "", 0, ""
        if argv[0] == "osascript":
            script = argv[-1]
            if self.denied:
                return _R(1, "", "execution error: System Events got an error: "
                                 "osascript is not allowed assistive access. (-1719)")
            if "applicationProcesses.whose({visible: true})" in script:
                out = json.dumps(self.windows)
            elif "frontmost: true" in script:
                out = self.front
            elif "to activate" in script:
                bid = script.split('application id "', 1)[1].split('"', 1)[0]
                self.front = bid
        elif argv[0] == "pbpaste":
            out = self.clipboard
        elif argv[0] == "pbcopy":
            self.clipboard = stdin or ""
        return _R(rc, out, err)

    def osa(self) -> list[str]:
        return [a[-1] for a, _ in self.calls if a[0] == "osascript"]


class _R:
    def __init__(self, rc: int, out: str, err: str) -> None:
        self.returncode, self.stdout, self.stderr = rc, out, err


def _bundle(root, name: str, bid: str, display: str | None = None) -> None:
    app = root / f"{name}.app" / "Contents"
    app.mkdir(parents=True)
    info = {"CFBundleName": name, "CFBundleIdentifier": bid}
    if display:
        info["CFBundleDisplayName"] = display
    (app / "Info.plist").write_bytes(plistlib.dumps(info))


@pytest.fixture()
def mac(tmp_path, monkeypatch):
    apps, system = tmp_path / "Applications", tmp_path / "System" / "Applications"
    apps.mkdir(parents=True)
    system.mkdir(parents=True)
    _bundle(apps, "Visual Studio Code", "com.microsoft.VSCode")
    _bundle(apps, "Microsoft PowerPoint", "com.microsoft.Powerpoint")
    _bundle(apps, "Claude", "com.anthropic.claudefordesktop")
    _bundle(system, "Calculator", "com.apple.calculator")
    (apps / "Broken.app").mkdir()                    # no Info.plist: skipped, not fatal
    run = Run()
    backend = desktop._MacDesktop(run=run, roots=[apps, system])
    monkeypatch.setattr(desktop, "_backend", lambda: backend)
    monkeypatch.setattr(desktop, "_sleep", lambda s: None)
    desktop._APPS_CACHE.clear()
    return run, backend


# ── finding and launching ──────────────────────────────────────────────────

def test_installed_apps_come_from_the_bundles_themselves(mac) -> None:
    _, b = mac
    apps = {a["Name"]: a["AppID"] for a in b.start_apps()}
    assert apps["Visual Studio Code"] == "com.microsoft.VSCode"
    assert apps["Calculator"] == "com.apple.calculator"
    assert "Broken" not in apps, "a bundle without Info.plist must be skipped, not crash"


async def test_powerpoint_is_found_by_the_word_people_use(mac) -> None:
    assert "Microsoft PowerPoint" in await desktop.find_app("powerpoint")


async def test_open_app_launches_by_bundle_id_and_brings_it_forward(mac) -> None:
    run, _ = mac

    real = run.__call__

    def launch_then_show(argv, stdin=None):
        r = real(argv, stdin)
        if argv[:2] == ["open", "-b"]:
            run.windows = [{"bid": argv[2], "app": "Code", "title": "aura"}]
        return r

    run.__call__ = launch_then_show           # type: ignore[method-assign]
    mac[1]._run = launch_then_show
    reply = await desktop.open_app("vscode")

    assert ["open", "-b", "com.microsoft.VSCode"] in [a for a, _ in run.calls]
    assert 'tell application id "com.microsoft.VSCode" to activate' in "\n".join(run.osa())
    assert "front" in reply.lower()


async def test_an_open_app_is_brought_forward_not_started_again(mac) -> None:
    run, _ = mac
    run.windows = [{"bid": "com.anthropic.claudefordesktop", "app": "Claude", "title": "Claude"}]
    reply = await desktop.open_app("claude")
    assert not any(a[:2] == ["open", "-b"] for a, _ in run.calls)
    assert "already open" in reply.lower()


# ── keys and text ──────────────────────────────────────────────────────────

async def test_copilot_chat_on_a_mac_is_ctrl_cmd_i(mac) -> None:
    run, _ = mac
    run.windows = [{"bid": "com.microsoft.VSCode", "app": "Code", "title": "aura"}]
    await desktop.send_keys("vscode", "ctrl+cmd+i")
    assert 'keystroke "i" using {control down, command down}' in "\n".join(run.osa())


@pytest.mark.parametrize("keys, fragment", [
    ("escape", "key code 53"),
    ("cmd+enter", "key code 36 using {command down}"),
    ("shift+cmd+n", 'keystroke "n" using {shift down, command down}'),
    ("f5", "key code 96"),
    ("alt+left", "key code 123 using {option down}"),
])
async def test_named_keys_become_key_codes(mac, keys, fragment) -> None:
    run, _ = mac
    run.windows = [{"bid": "com.microsoft.Powerpoint", "app": "PowerPoint", "title": "Deck"}]
    await desktop.send_keys("powerpoint", keys)
    assert fragment in "\n".join(run.osa())


async def test_text_goes_through_the_clipboard_on_stdin_and_the_clipboard_comes_back(mac) -> None:
    """Never inside a script, never as an argument: nothing to escape, so
    nothing to inject — and the owner's clipboard is put back."""
    run, _ = mac
    run.windows = [{"bid": "com.microsoft.VSCode", "app": "Code", "title": "aura"}]
    await desktop.type_into("vscode", 'leg uit wat "één" functie doet')

    copies = [stdin for a, stdin in run.calls if a[0] == "pbcopy"]
    assert copies[0] == 'leg uit wat "één" functie doet'
    assert copies[-1] == "what the owner had copied"
    assert all("één" not in s for s in run.osa()), "text must never be embedded in a script"
    assert 'keystroke "v" using {command down}' in "\n".join(run.osa())


# ── the hole, closed on both platforms ─────────────────────────────────────

@pytest.mark.parametrize("keys", [
    'cmd+a" & do shell script "touch /tmp/pwned',
    "ctrl+rm -rf",
    'cmd+"',
    "cmd+\\",
    "ctrl+alt+notakey",
])
def test_the_final_key_comes_from_a_fixed_list(keys) -> None:
    assert desktop._parse_keys(keys) is None, keys


async def test_an_injection_attempt_never_reaches_osascript(mac) -> None:
    run, _ = mac
    run.windows = [{"bid": "com.microsoft.VSCode", "app": "Code", "title": "aura"}]
    await desktop.send_keys("vscode", 'cmd+a" & do shell script "touch /tmp/pwned')
    assert all("do shell script" not in s for s in run.osa())


def test_a_malformed_bundle_id_is_never_put_into_a_script(mac) -> None:
    run, b = mac
    assert b.focus('com.x" to do shell script "id') is False
    assert run.osa() == []


# ── permission ─────────────────────────────────────────────────────────────

async def test_missing_accessibility_permission_is_named_not_mysterious(mac) -> None:
    """The one thing the owner must do by hand on a Mac. Say exactly where."""
    run, _ = mac
    run.denied = True
    reply = await desktop.list_windows()
    assert unavailable_capability(reply) == "desktop"
    assert "Accessibility" in reply and "Privacy & Security" in reply


async def test_missing_permission_during_keys_presses_nothing_and_says_why(mac) -> None:
    run, _ = mac
    run.windows = [{"bid": "com.microsoft.VSCode", "app": "Code", "title": "aura"}]
    run.denied = True
    reply = await desktop.send_keys("vscode", "ctrl+cmd+i")
    assert all("keystroke" not in s for s in run.osa())
    assert "Accessibility" in reply


# ── the model is told the Mac's shortcuts on a Mac ─────────────────────────

def test_the_send_keys_description_uses_the_platform_s_shortcuts(monkeypatch) -> None:
    from orchestrator.tool_schemas import build_tool_specs

    monkeypatch.setattr(sys, "platform", "darwin")
    mac_spec = next(s for s in build_tool_specs(frozenset({"send_keys"}))
                    if s["function"]["name"] == "send_keys")
    assert "ctrl+cmd+i" in mac_spec["function"]["description"]
    assert "ctrl+alt+i" not in mac_spec["function"]["description"]

    monkeypatch.setattr(sys, "platform", "win32")
    win_spec = next(s for s in build_tool_specs(frozenset({"send_keys"}))
                    if s["function"]["name"] == "send_keys")
    assert "ctrl+alt+i" in win_spec["function"]["description"]


# ── a real Mac (the macOS job in checks.yml) ───────────────────────────────

@pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS")
def test_a_real_mac_lists_its_installed_apps() -> None:
    desktop._APPS_CACHE.clear()
    apps = desktop._MacDesktop().start_apps()
    ids = {a["AppID"] for a in apps}
    assert "com.apple.calculator" in ids or "com.apple.Safari" in ids, sorted(ids)[:10]


@pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS")
async def test_a_real_mac_answers_honestly_about_its_windows() -> None:
    """A CI Mac has no Accessibility grant for the runner; a laptop may. Either
    the windows come back, or the reply names the permission — never a crash
    and never a silent empty list."""
    desktop._APPS_CACHE.clear()
    import orchestrator.desktop as d

    reply = await d.list_windows()
    assert reply.startswith("Open windows") or "Accessibility" in reply, reply
