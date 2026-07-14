"""RobotClient — the brain↔robot-runtime boundary (Phase 2, U13).

This is the ONE network hop that survives the Phase 1 collapse: the laptop brain
drives robot-runtime (on the Reachy) over REST commands + a WS event stream. The
contract mirrors robot-runtime's command endpoints exactly:

    GET  /robot/status            → RobotState
    POST /robot/connect           → {connected: true}
    POST /robot/disconnect        → {connected: false}
    POST /robot/speak   {text}    → {ok: true}        (422 if text missing)
    POST /robot/motion  Motion    → {ok: true}
    POST /robot/mode    {mode}    → {mode}            (422 if unknown)
    WS   /ws/events                → robot/behavior event stream

It works against FakeRobot (no hardware) and the real Reachy adapter identically
— the contract is adapter-agnostic. An httpx client may be injected for in-process
contract testing (ASGI transport against robot-runtime's app).
"""

from __future__ import annotations

import os

import httpx

from shared_schemas.robot.models import MotionCommand


class RobotClient:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get(
            "ROBOT_RUNTIME_URL", "http://robot-runtime:8001"
        )).rstrip("/")
        self._client = client  # injected (tests / shared pool); else per-call
        self._timeout = timeout

    async def _request(self, method: str, path: str, json: dict | None = None) -> httpx.Response:
        if self._client is not None:
            resp = await self._client.request(method, path, json=json)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, f"{self._base_url}{path}", json=json)
        resp.raise_for_status()
        return resp

    async def status(self) -> dict:
        return (await self._request("GET", "/robot/status")).json()

    async def connect(self) -> bool:
        return (await self._request("POST", "/robot/connect")).json().get("connected", False)

    async def disconnect(self) -> bool:
        return (await self._request("POST", "/robot/disconnect")).json().get("connected", True)

    async def speak(self, text: str, audio_b64: str | None = None) -> bool:
        """Speak on the robot. With ``audio_b64`` (PCM s16le mono 24 kHz) the
        robot plays real synthesized speech; without it, text-only (logged)."""
        body: dict = {"text": text}
        if audio_b64:
            body["audio_b64"] = audio_b64
        return (await self._request("POST", "/robot/speak", body)).json().get("ok", False)

    async def execute_motion(self, command: MotionCommand) -> bool:
        body = command.model_dump(mode="json")
        return (await self._request("POST", "/robot/motion", body)).json().get("ok", False)

    async def set_mode(self, mode: str) -> str:
        return (await self._request("POST", "/robot/mode", {"mode": mode})).json().get("mode", "")

    async def camera_frame(self) -> bytes:
        """One PNG frame from the robot's camera (U18 perception loop)."""
        return (await self._request("GET", "/robot/camera/frame")).content

    async def set_tracking(self, enabled: bool) -> dict:
        return (await self._request("POST", "/robot/tracking", {"enabled": enabled})).json()

    async def get_volume(self) -> dict:
        return (await self._request("GET", "/robot/volume")).json()

    async def set_volume(self, level: float) -> dict:
        return (await self._request("POST", "/robot/volume", {"volume": level})).json()
