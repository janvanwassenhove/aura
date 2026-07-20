"""U43: desktop media control via Windows media keys."""

from __future__ import annotations

from orchestrator import pipeline as pipeline_mod
from orchestrator.pipeline import _MEDIA_KEYS, _media_control


async def test_unknown_action_lists_valid_ones() -> None:
    result = await _media_control("teleport")
    assert "unknown action" in result
    assert "play_pause" in result


async def test_known_actions_map_to_keys() -> None:
    assert _MEDIA_KEYS["play_pause"] == 0xB3
    assert _MEDIA_KEYS["next"] == 0xB0
    assert _MEDIA_KEYS["previous"] == 0xB1


async def test_play_pause_sends_key(monkeypatch) -> None:
    sent: list[int] = []
    monkeypatch.setattr(pipeline_mod, "_send_media_key", lambda vk: sent.append(vk))
    # U168: patch the seam, NOT the global os.name — that flips
    # pathlib.Path to WindowsPath process-wide and crashes pytest
    # internals on Linux CI.
    monkeypatch.setattr(pipeline_mod, "_is_windows", lambda: True)
    result = await _media_control("play_pause")
    assert sent == [0xB3]
    assert "play pause" in result


async def test_non_windows_is_graceful(monkeypatch) -> None:
    monkeypatch.setattr(pipeline_mod, "_is_windows", lambda: False)
    result = await _media_control("next")
    assert "only supported on Windows" in result
