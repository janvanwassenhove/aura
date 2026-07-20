"""U58: tool-ladder basistools — path bounds, git prep, ladder policy."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from orchestrator import laptop_tools
from orchestrator.tool_schemas import LADDER_NOTE, TOOL_LAYERS, TOOL_SCHEMAS
from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FS_ROOTS", str(tmp_path))
    return tmp_path


# ── file system: bounded ─────────────────────────────────────────────

async def test_read_file_inside_root(roots) -> None:
    f = roots / "note.txt"
    f.write_text("hello agent", encoding="utf-8")
    assert await laptop_tools.read_file(str(f)) == "hello agent"


async def test_read_file_outside_root_refused(roots) -> None:
    out = await laptop_tools.read_file("C:/Windows/win.ini" if os.name == "nt" else "/etc/hosts")
    assert "outside the allowed roots" in out


async def test_traversal_escape_refused(roots) -> None:
    sneaky = roots / ".." / ".." / "secrets.txt"
    out = await laptop_tools.read_file(str(sneaky))
    assert "outside the allowed roots" in out


async def test_write_then_read_roundtrip(roots) -> None:
    target = roots / "sub" / "made.txt"
    out = await laptop_tools.write_file(str(target), "content!")
    assert "Wrote 8 chars" in out
    assert target.read_text(encoding="utf-8") == "content!"


async def test_write_outside_root_refused(roots, tmp_path_factory) -> None:
    elsewhere = tmp_path_factory.mktemp("elsewhere") / "x.txt"
    out = await laptop_tools.write_file(str(elsewhere), "nope")
    assert "outside the allowed roots" in out
    assert not elsewhere.exists()


# ── output cap ───────────────────────────────────────────────────────

async def test_read_file_output_is_capped(roots) -> None:
    big = roots / "big.txt"
    big.write_text("x" * 20_000, encoding="utf-8")
    out = await laptop_tools.read_file(str(big))
    assert len(out) < 7_000
    assert "truncated" in out


# ── git prepare (read-only) ──────────────────────────────────────────

async def test_git_prepare_rejects_unknown_action(roots) -> None:
    out = await laptop_tools.git_prepare("push")
    assert "must be one of" in out


async def test_git_prepare_status_runs_in_a_repo(roots) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(roots)], check=True)
    out = await laptop_tools.git_prepare("status", str(roots))
    assert "##" in out or "branch" in out.lower()


# ── powershell ───────────────────────────────────────────────────────

async def test_run_powershell_requires_command() -> None:
    assert "required" in await laptop_tools.run_powershell("")


async def test_run_powershell_working_dir_bounded(roots) -> None:
    out = await laptop_tools.run_powershell("Get-Location", working_dir="/definitely/elsewhere")
    assert "outside the allowed roots" in out


@pytest.mark.skipif(os.name != "nt", reason="PowerShell only on Windows")
async def test_run_powershell_echo(roots) -> None:
    out = await laptop_tools.run_powershell("Write-Output 'ladder ok'")
    assert "ladder ok" in out


# ── ladder policy wiring ─────────────────────────────────────────────

def test_sensitive_ladder_tools_require_approval() -> None:
    assert "run_powershell" in APPROVAL_REQUIRED
    assert "write_file" in APPROVAL_REQUIRED
    assert "read_file" not in APPROVAL_REQUIRED   # read-only, path-bounded
    assert "git_prepare" not in APPROVAL_REQUIRED  # read-only


def test_ladder_tools_advertised_in_work_mode() -> None:
    for tool in ("run_powershell", "read_file", "write_file", "git_prepare"):
        assert tool in MODE_TOOL_MAP["work"]
        assert tool in TOOL_SCHEMAS


def test_gui_is_the_emergency_exit() -> None:
    assert TOOL_LAYERS["use_computer"] == "gui"
    assert "emergency exit" in LADDER_NOTE
