"""Spotify music control, with Sonos targeting via Spotify Connect (U39).

A Sonos speaker linked to Spotify shows up in the Spotify Connect device list,
so "play on the Sonos" = find that device and start playback there — no separate
Sonos API needed.

Auth: set ``SPOTIFY_ACCESS_TOKEN`` (a user token with the scopes
user-modify-playback-state, user-read-playback-state, playlist-read-private,
user-library-read). Obtain it once via Spotify's OAuth (developer.spotify.com).
Without a token the client runs in MOCK mode so the flow is demoable.

Every method returns a short human-readable string for the assistant to speak.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API = "https://api.spotify.com/v1"


class SpotifyMusic:
    def __init__(self) -> None:
        self._token = os.environ.get("SPOTIFY_ACCESS_TOKEN", "").strip()
        self._default_device = os.environ.get("SONOS_DEVICE_NAME", "Sonos")

    @property
    def mock(self) -> bool:
        return not self._token

    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _api(self, method: str, path: str, **kw: Any) -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.request(method, f"{_API}{path}", headers=self._headers(), **kw)

    async def _devices(self) -> list[dict]:
        resp = await self._api("GET", "/me/player/devices")
        resp.raise_for_status()
        return resp.json().get("devices", [])

    async def _find_device_id(self, name: str | None) -> str | None:
        """Match a device by (partial, case-insensitive) name; prefer the Sonos."""
        wanted = (name or self._default_device).lower()
        devices = await self._devices()
        for d in devices:
            if wanted in d.get("name", "").lower():
                return d["id"]
        # Fall back to the currently active device, if any.
        for d in devices:
            if d.get("is_active"):
                return d["id"]
        return devices[0]["id"] if devices else None

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    async def list_devices(self) -> str:
        if self.mock:
            return ("Speakers (mock): Sonos Living Room, Kitchen Sonos, Laptop. "
                    "Set SPOTIFY_ACCESS_TOKEN for real playback.")
        try:
            devices = await self._devices()
        except httpx.HTTPError as exc:
            return f"[music: could not reach Spotify — {type(exc).__name__}]"
        if not devices:
            return "No Spotify Connect speakers are online. Open Spotify on your Sonos first."
        return "Available speakers: " + ", ".join(
            f"{d['name']}{' (active)' if d.get('is_active') else ''}" for d in devices
        )

    async def list_playlists(self) -> str:
        if self.mock:
            return "Playlists (mock): Favorites, Focus, Dinner, Party Mix."
        try:
            resp = await self._api("GET", "/me/playlists?limit=20")
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except httpx.HTTPError as exc:
            return f"[music: could not list playlists — {type(exc).__name__}]"
        if not items:
            return "You have no Spotify playlists."
        return "Your playlists: " + ", ".join(p["name"] for p in items[:20])

    async def pause(self) -> str:
        if self.mock:
            return "Paused the music (mock)."
        try:
            await self._api("PUT", "/me/player/pause")
            return "Paused the music."
        except httpx.HTTPError as exc:
            return f"[music: pause failed — {type(exc).__name__}]"

    async def next_track(self) -> str:
        if self.mock:
            return "Skipped to the next track (mock)."
        try:
            await self._api("POST", "/me/player/next")
            return "Skipped to the next track."
        except httpx.HTTPError as exc:
            return f"[music: skip failed — {type(exc).__name__}]"

    async def play(
        self,
        query: str | None = None,
        playlist: str | None = None,
        favorites: bool = False,
        device: str | None = None,
    ) -> str:
        target = device or self._default_device
        if self.mock:
            what = query or playlist or ("their favorites" if favorites else "music")
            # Be HONEST: nothing actually plays without a Spotify token. Tell the
            # assistant so it doesn't claim success, and offer the real fallback.
            return (
                f"NOT PLAYED. Spotify isn't connected to an account here, so I "
                f"cannot start {what} or pick {target} automatically. Two options: "
                f"(1) I can open Spotify and press Play on whatever is loaded "
                f"(use launch_app then media_control play_pause) — but I can't "
                f"choose the Sonos or a specific playlist that way; or (2) add a "
                f"SPOTIFY_ACCESS_TOKEN for real playback + Sonos targeting. Tell "
                f"the user this honestly; do not claim the music is playing."
            )
        try:
            device_id = await self._find_device_id(device)
            if device_id is None:
                return ("No Spotify speaker is online. Open Spotify on your Sonos, "
                        "then ask again.")
            body, label = await self._resolve_playback(query, playlist, favorites)
            if body is None:
                return label  # error/no-match message
            await self._api("PUT", f"/me/player/play?device_id={device_id}", json=body)
            dev_name = await self._device_name(device_id)
            return f"Playing {label} on {dev_name}."
        except httpx.HTTPError as exc:
            return f"[music: playback failed — {type(exc).__name__}]"

    # ------------------------------------------------------------------

    async def _device_name(self, device_id: str) -> str:
        for d in await self._devices():
            if d["id"] == device_id:
                return d["name"]
        return "the speaker"

    async def _resolve_playback(
        self, query: str | None, playlist: str | None, favorites: bool
    ) -> tuple[dict | None, str]:
        if favorites:
            resp = await self._api("GET", "/me/tracks?limit=30")
            resp.raise_for_status()
            uris = [t["track"]["uri"] for t in resp.json().get("items", []) if t.get("track")]
            if not uris:
                return None, "You have no liked songs yet."
            return {"uris": uris}, "your favorites"
        if playlist:
            resp = await self._api("GET", "/me/playlists?limit=50")
            resp.raise_for_status()
            for p in resp.json().get("items", []):
                if playlist.lower() in p["name"].lower():
                    return {"context_uri": p["uri"]}, f"the '{p['name']}' playlist"
            return None, f"I couldn't find a playlist matching '{playlist}'."
        if query:
            resp = await self._api("GET", "/search", params={"q": query, "type": "track", "limit": 1})
            resp.raise_for_status()
            tracks = resp.json().get("tracks", {}).get("items", [])
            if not tracks:
                return None, f"I couldn't find anything for '{query}'."
            t = tracks[0]
            return {"uris": [t["uri"]]}, f"{t['name']} by {t['artists'][0]['name']}"
        # Nothing specified → resume playback.
        return {}, "your music"
