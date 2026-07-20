"""U39: Spotify + Sonos music control (mock mode without a token)."""

from __future__ import annotations

import pytest
from connector_service.music import SpotifyMusic


@pytest.fixture()
def mock_music(monkeypatch):
    monkeypatch.delenv("SPOTIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("SONOS_DEVICE_NAME", "Sonos")
    return SpotifyMusic()


async def test_mock_mode_active_without_token(mock_music) -> None:
    assert mock_music.mock is True


async def test_play_query_targets_sonos(mock_music) -> None:
    result = await mock_music.play(query="Bohemian Rhapsody")
    assert "Bohemian Rhapsody" in result
    assert "Sonos" in result


async def test_play_favorites(mock_music) -> None:
    result = await mock_music.play(favorites=True)
    assert "favorites" in result.lower()


async def test_play_on_named_device(mock_music) -> None:
    result = await mock_music.play(query="jazz", device="Kitchen")
    assert "Kitchen" in result


async def test_pause_next_playlists_devices(mock_music) -> None:
    assert "aused" in await mock_music.pause()
    assert "next" in (await mock_music.next_track()).lower()
    assert "mock" in (await mock_music.list_playlists()).lower()
    assert "Sonos" in await mock_music.list_devices()


async def test_real_mode_when_token_set(monkeypatch) -> None:
    monkeypatch.setenv("SPOTIFY_ACCESS_TOKEN", "fake-token")
    m = SpotifyMusic()
    assert m.mock is False
    # No network in tests → a play call returns a graceful error string.
    result = await m.pause()
    assert result.startswith("[music:") or result == "Paused the music."
