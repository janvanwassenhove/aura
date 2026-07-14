"""U40: allow-listed app launcher tool."""

from __future__ import annotations

import pytest

from orchestrator.pipeline import _allowed_apps, _launch_app


def test_allowed_apps_parsing(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code ; Spotify=spotify;bad")
    apps = _allowed_apps()
    assert apps == {"vscode": "code", "spotify": "spotify"}


async def test_launch_rejects_unregistered_app(monkeypatch) -> None:
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    result = await _launch_app("spotify")
    assert "not in your allow-list" in result
    assert "vscode" in result  # lists what IS available


async def test_launch_blocked_when_capability_off(monkeypatch) -> None:
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "false")
    monkeypatch.setenv("ALLOWED_APPS", "vscode=code")
    assert "disabled" in await _launch_app("vscode")


async def test_launch_registered_app(monkeypatch) -> None:
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    # A command that exists on every platform and exits 0.
    import sys
    monkeypatch.setenv("ALLOWED_APPS", f"probe={sys.executable} -c pass")
    result = await _launch_app("probe")
    assert result.startswith("Launched probe")


async def test_launch_missing_name(monkeypatch) -> None:
    monkeypatch.setenv("APP_LAUNCH_ENABLED", "true")
    assert "name is required" in await _launch_app("")
