"""U377: "can you start VS Code" — auto-approved, and dead in two milliseconds.

Reported with a screenshot (translated): *"why does this not work? It is in
the skills too — but even without that he should go looking for a solution,
or ask for permission somewhere."* The header said `tools 2ms`, and the brain
log said:

    14:17:07 orchestrator.approval_manager :: Auto-approved (remembered): launch_app

So approval was never the obstacle. The tool ran and failed before starting
anything, and said nothing in the log while doing it.

**The cause is one line, and its fix was already in the same file.**
`_open_in_vscode` resolves the CLI with `shutil.which("code")`, commented
*"resolves code.cmd on Windows"*. `_launch_app` handed the bare word `code` to
`create_subprocess_exec`. On Windows `code` is a batch shim, `code.cmd`, and
CreateProcess only appends `.exe` — PATHEXT is a shell convention, not a
process one. Measured on the owner's machine:

    exec('code', '--version')         -> FileNotFoundError: [WinError 2]
    exec(which('code'), '--version')  -> started

Of the seven registered apps exactly two were broken, `vscode` and `code`,
and they are the two whose command is a shim; the other five start with a
real `.exe` (`notepad`, `explorer.exe`, `cmd`).

**The second half is what he did next.** The tool's reply was "command not
found — check its path in Capabilities": a job for the owner, not a next step
for him. The skill's escalation order then says `use_computer` "needs
approval", and nothing anywhere says that *calling* it is how approval is
asked — the gate shows the owner a card. So he wrote "I need your approval for
a next step" in a sentence, with no card and no statement of what the step
was. And the failure carried no U247 marker, so the skill's usage evidence
recorded it as a success: the `2×` on the skill card is two failures.
"""

from __future__ import annotations

import asyncio
import os
import shutil

import pytest
from orchestrator import pipeline
from shared_schemas.tool_outcome import unavailable_capability


class _Proc:
    returncode = None


@pytest.fixture()
def captured(monkeypatch):
    """Record what would be executed, and execute nothing."""
    seen: list[tuple[str, ...]] = []

    async def fake_exec(*argv, **kw):
        seen.append(argv)
        return _Proc()

    monkeypatch.setattr(pipeline.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    return seen


async def test_the_command_is_resolved_the_way_the_shell_would(captured, monkeypatch) -> None:
    """The bare word must be resolved through PATHEXT before it is executed —
    the same `shutil.which` `_open_in_vscode` has always used."""
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    shim = r"C:\Program Files\Microsoft VS Code\bin\code.CMD"
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: shim if name == "code" else None)

    reply = await pipeline._launch_app("vscode")

    assert captured == [(shim,)], f"it executed {captured} instead of the resolved shim"
    assert reply == "Launched vscode."


async def test_arguments_from_the_allow_list_travel_unchanged(captured, monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_APPS", "chrome=cmd /c start chrome --remote-debugging-port=9222")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: r"C:\Windows\System32\cmd.EXE")

    await pipeline._launch_app("chrome")

    assert captured[0][0].lower().endswith("cmd.exe")
    assert captured[0][1:] == ("/c", "start", "chrome", "--remote-debugging-port=9222")


async def test_an_absolute_command_is_not_second_guessed(captured, monkeypatch) -> None:
    """An owner who wrote a full path meant that file."""
    path = r"D:\Tools\thing.exe" if os.name == "nt" else "/opt/tools/thing"
    monkeypatch.setenv("ALLOWED_APPS", f"thing={path}")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)

    await pipeline._launch_app("thing")

    assert captured and captured[0][0] == path


# ── when it really cannot start: say what to do next, and say it failed ─────

async def test_a_missing_command_is_a_marked_failure_not_a_success(captured, monkeypatch) -> None:
    """U247: prose alone is read only by the model. The marker is what lets the
    skill evidence count this as the failure it is."""
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)

    reply = await pipeline._launch_app("vscode")

    assert captured == [], "nothing should be executed when nothing was found"
    assert unavailable_capability(reply) is not None, reply


async def test_the_failure_gives_him_a_next_step_not_a_chore_for_the_owner(captured, monkeypatch) -> None:
    """"Check its path in Capabilities" is a job for the owner. What he needs is
    a move he can make: another tool, or the one that raises the card."""
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)

    reply = await pipeline._launch_app("vscode")

    assert "open_in_vscode" in reply, "VS Code has a dedicated tool; the reply must name it"
    assert "use_computer" in reply
    assert "approval card" in reply, "calling the gated tool IS the request — say so"


async def test_an_app_without_a_dedicated_tool_still_gets_a_next_step(captured, monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_APPS", "notepad=notepad")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)

    reply = await pipeline._launch_app("notepad")

    assert "use_computer" in reply and "approval card" in reply
    assert "open_in_vscode" not in reply, "do not suggest a VS Code tool for Notepad"


async def test_an_os_refusal_is_marked_too(monkeypatch) -> None:
    """Found → started is not guaranteed: a managed laptop can refuse the
    launcher (U344's Defender ASR). That must not read as success either."""
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: r"C:\x\code.CMD")

    async def refuse(*a, **k):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(pipeline.asyncio, "create_subprocess_exec", refuse)
    reply = await pipeline._launch_app("vscode")
    assert unavailable_capability(reply) is not None, reply
    assert "Access is denied" in reply


# ── and on a real Windows machine, the real thing ──────────────────────────

@pytest.mark.skipif(os.name != "nt" or shutil.which("code") is None,
                    reason="needs Windows with the VS Code CLI on PATH")
async def test_the_real_shim_starts_on_windows(monkeypatch) -> None:
    """The measurement from the report, as a test. `--version` so nothing
    opens a window on the machine running the suite."""
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code --version")
    reply = await pipeline._launch_app("vscode")
    assert reply == "Launched vscode.", reply
    await asyncio.sleep(0)


# ── the skill text teaches the same lesson ─────────────────────────────────

def test_the_built_in_skills_say_that_calling_use_computer_is_the_request() -> None:
    """U377: the old step 3 said use_computer "needs approval", and he read that
    as "ask in words first" — then stopped. Every built-in desktop skill shares
    this preamble, so the correction lands in all of them at once."""
    from orchestrator.builtin_skills import BUILTIN_SKILLS

    for skill in BUILTIN_SKILLS:
        if "Escalation order" not in skill.body:
            continue
        assert "approval card" in skill.body, skill.name
        assert "call it" in skill.body, skill.name


def test_the_vscode_skill_has_a_way_round_a_failed_launch() -> None:
    from orchestrator.builtin_skills import BUILTIN_SKILLS

    body = next(s.body for s in BUILTIN_SKILLS if s.name == "desktop-vscode")
    opening = body.split("Finding a repo")[0]
    assert "launch_app('vscode')" in opening
    assert "If that fails" in opening and "open_in_vscode" in opening
