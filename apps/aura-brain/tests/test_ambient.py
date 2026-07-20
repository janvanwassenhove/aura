"""U131: ambient context — weather, time-of-day, non-repetition."""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")


from aura_brain import ambient


def test_time_of_day_buckets() -> None:
    assert ambient.time_of_day(3) == "the middle of the night"
    assert ambient.time_of_day(9) == "morning"
    assert ambient.time_of_day(14) == "afternoon"
    assert ambient.time_of_day(20) == "evening"
    assert ambient.time_of_day(23) == "late evening"


def test_recent_lines_ring_and_dedupe_hint() -> None:
    ambient._recent.clear()
    ambient.note_spontaneous("Hey Jan, still raining out there?")
    ambient.note_spontaneous("")  # ignored
    assert ambient.recent_lines() == ["Hey Jan, still raining out there?"]


async def test_current_weather_parses_openmeteo(monkeypatch) -> None:
    ambient._cache.update({"ts": 0.0, "text": None})

    class _Resp:
        def raise_for_status(self): ...
        def json(self):
            return {"current": {"temperature_2m": 11.6, "weather_code": 61}}

    class _Client:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None): return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert await ambient.current_weather() == "light rain, 12°C"


async def test_current_weather_failure_is_none(monkeypatch) -> None:
    ambient._cache.update({"ts": 0.0, "text": None})

    class _Boom:
        def __init__(self, **kw): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise RuntimeError("offline")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Boom)
    assert await ambient.current_weather() is None


async def test_ambient_note_includes_time_weather_and_dedupe(monkeypatch) -> None:
    ambient._recent.clear()
    ambient.note_spontaneous("Morning Jan!")

    async def _w():
        return "clear skies, 8°C"

    monkeypatch.setattr(ambient, "current_weather", _w)
    note = await ambient.ambient_note(9)
    assert "morning" in note
    assert "clear skies, 8°C" in note
    assert "Morning Jan!" in note  # tells the model not to repeat it
