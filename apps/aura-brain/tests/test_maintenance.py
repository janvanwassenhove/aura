"""U36g: the brain's self-maintenance loop checks and heals."""

from __future__ import annotations

import pytest

from aura_brain.maintenance import MaintenanceLoop


class FakeBus:
    def __init__(self) -> None:
        self.published: list = []

    async def publish(self, event) -> None:
        self.published.append(event)


class FakeRobot:
    def __init__(self, connected: bool = True, reconnect_ok: bool = True) -> None:
        self._connected = connected
        self._reconnect_ok = reconnect_ok
        self.reconnects = 0

    async def status(self) -> dict:
        return {"connected": self._connected, "mode": "online"}

    async def connect(self) -> bool:
        self.reconnects += 1
        if not self._reconnect_ok:
            raise ConnectionError("robot down")
        self._connected = True
        return True


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


async def test_healthy_pass_reports_ok() -> None:
    bus = FakeBus()
    loop = MaintenanceLoop(bus, FakeRobot(), knowledge_encrypted=lambda: True)
    report = await loop.tick()
    assert report["healthy"] is True
    assert report["checks"]["robot"] == "ok"
    assert report["checks"]["knowledge"] == "encrypted"
    (event,) = bus.published
    assert event.event_type == "MaintenanceReport" and event.healthy is True


async def test_disconnected_robot_is_reconnected() -> None:
    robot = FakeRobot(connected=False)
    loop = MaintenanceLoop(FakeBus(), robot, knowledge_encrypted=lambda: True)
    report = await loop.tick()
    assert robot.reconnects == 1
    assert report["checks"]["robot"] == "recovered"
    assert "reconnected robot adapter" in report["actions"]
    assert report["healthy"] is True


async def test_missing_key_flags_unhealthy(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    loop = MaintenanceLoop(FakeBus(), FakeRobot(), knowledge_encrypted=lambda: False)
    report = await loop.tick()
    assert report["healthy"] is False
    assert report["checks"]["llm_key"] == "missing"
    assert report["checks"]["knowledge"].startswith("unencrypted")
