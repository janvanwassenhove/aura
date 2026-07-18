"""U131: ambient context for natural, non-repetitive spontaneous speech.

When Richie speaks on his own initiative (greeting, idle remark, briefing) it
felt flat and repetitive. This adds real-world context — time of day and the
current weather — plus a short memory of what he just said, so the LLM can be
curious and varied ("Back already, Jan? Still pouring out there?") instead of
"Dag Jan" every time.

Weather comes from Open-Meteo (free, no API key). Location via WEATHER_LAT /
WEATHER_LON (defaults to Brussels). Cached ~15 min. All best-effort — any
failure just drops the weather clause, never blocks speech.
"""

from __future__ import annotations

import logging
import os
import time
from collections import deque

logger = logging.getLogger(__name__)

# WMO weather codes → short human phrases (Open-Meteo `weather_code`).
_WMO = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 77: "snow grains", 80: "rain showers", 81: "rain showers",
    82: "violent rain showers", 85: "snow showers", 86: "snow showers",
    95: "a thunderstorm", 96: "a thunderstorm with hail", 99: "a severe thunderstorm",
}

_cache: dict = {"ts": 0.0, "text": None}


async def current_weather() -> str | None:
    """Short weather phrase like 'light rain, 12°C', or None if unavailable."""
    ttl = float(os.environ.get("WEATHER_TTL_S", "900"))
    if _cache["text"] is not None and (time.time() - _cache["ts"]) < ttl:
        return _cache["text"]
    lat = os.environ.get("WEATHER_LAT", "50.85")
    lon = os.environ.get("WEATHER_LON", "4.35")
    try:
        import httpx

        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon,
                        "current": "temperature_2m,weather_code"},
            )
            r.raise_for_status()
            cur = r.json().get("current", {})
    except Exception as exc:  # noqa: BLE001 — weather is a nicety, never fatal
        logger.debug("weather fetch failed: %s", exc)
        return None
    code = cur.get("weather_code")
    temp = cur.get("temperature_2m")
    if code is None:
        return None
    phrase = _WMO.get(int(code), "changeable weather")
    text = f"{phrase}, {round(temp)}°C" if temp is not None else phrase
    _cache["ts"] = time.time()
    _cache["text"] = text
    return text


def time_of_day(hour: int) -> str:
    if hour < 6:
        return "the middle of the night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    if hour < 22:
        return "evening"
    return "late evening"


# Short ring of recent spontaneous lines so the LLM avoids repeating itself.
_recent: deque[str] = deque(maxlen=6)


def note_spontaneous(text: str) -> None:
    if text and text.strip():
        _recent.append(text.strip())


def recent_lines() -> list[str]:
    return list(_recent)


async def ambient_note(hour: int) -> str:
    """A compact context block for the greeting/idle prompt."""
    parts = [f"It is {time_of_day(hour)}."]
    weather = await current_weather()
    if weather:
        parts.append(f"Current weather outside: {weather}.")
    if _recent:
        parts.append("Do NOT repeat any of your recent lines: "
                     + " | ".join(f'"{r}"' for r in _recent) + ".")
    return " ".join(parts)
