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


# --------------------------------------------------------------------------- #
# U359: what the robot said went wrong must reach the person reading the screen
# --------------------------------------------------------------------------- #

async def test_a_robot_error_carries_its_reason_not_just_a_status() -> None:
    """Reported from a rehearsal: `Server error '500 Internal Server Error' for
    url '.../robot/speak' For more information check: <MDN>`.

    httpx's message is the status and a link to a page about HTTP. The robot
    now answers with a reason (U359), and it was being thrown away one layer
    above — so the presenter got a lecture on status codes instead of "the
    audio device went away".
    """
    import httpx
    from aura_brain.robot_client import RobotClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "the robot could not play that line",
                                         "reason": "RuntimeError: audio device went away"})

    client = RobotClient(client=httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://robot"))
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await client.speak("Ta. Ta. Ta.", audio_b64="AAAA")

    assert "audio device went away" in str(exc.value)
    # Still an HTTPStatusError with its response attached: set_asleep() and
    # friends branch on `exc.response.status_code == 404`.
    assert exc.value.response.status_code == 503


async def test_an_error_with_no_body_still_raises_normally() -> None:
    """An older robot, or a proxy, answers with nothing useful. That must stay
    an ordinary failure rather than becoming a crash in the error path."""
    import httpx
    from aura_brain.robot_client import RobotClient

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="<html>nope</html>")

    client = RobotClient(client=httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://robot"))
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await client.speak("hello")
    assert exc.value.response.status_code == 404
