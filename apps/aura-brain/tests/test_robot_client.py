"""U13: brain↔robot boundary contract. RobotClient is exercised against the REAL
robot-runtime app running FakeRobot (in-process via ASGI) — proving the command
contract without hardware. The same client drives the real Reachy adapter (U16).
"""

from __future__ import annotations

import os

os.environ.setdefault("ROBOT_ADAPTER", "fake")

import httpx
import pytest
from aura_brain.robot_client import RobotClient
from shared_schemas.robot.models import MotionCommand


@pytest.fixture()
async def robot_client():
    from robot_runtime.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://robot") as http:
            yield RobotClient(client=http)


async def test_connect_status_speak_motion_mode(robot_client: RobotClient) -> None:
    assert await robot_client.connect() is True

    status = await robot_client.status()
    assert isinstance(status, dict) and "mode" in status

    assert await robot_client.speak("Hello, I am AURA.") is True
    assert await robot_client.execute_motion(MotionCommand(motion_id="nod")) is True

    mode = await robot_client.set_mode("online")  # RobotMode values are lowercase
    assert mode == "online"

    assert await robot_client.disconnect() is False


async def test_speak_requires_text(robot_client: RobotClient) -> None:
    with pytest.raises(httpx.HTTPStatusError):  # 422 — contract: text is required
        await robot_client.speak("")
