"""Tests for HeartbeatMonitor — mode transitions and event emission."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.heartbeat import HeartbeatMonitor
from shared_events.bus import AsyncEventBus
from shared_schemas.events.robot import RobotModeChanged
from shared_schemas.events.system import BackendHeartbeatFailed, BackendHeartbeatOk
from shared_schemas.robot.models import RobotMode


@pytest.fixture
async def bus():
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def make_monitor(bus, services=None, failure_threshold=3, stability_window_s=0.0):
    return HeartbeatMonitor(
        bus,
        services=services or {"llm": "http://llm/health"},
        interval_s=999,          # prevent auto-looping in tests
        failure_threshold=failure_threshold,
        stability_window_s=stability_window_s,
    )


# --------------------------------------------------------------------------- #
# BackendHeartbeatOk emitted when service responds 200
# --------------------------------------------------------------------------- #

async def test_healthy_service_emits_heartbeat_ok(bus):
    events: list = []
    bus.subscribe(BackendHeartbeatOk, lambda e: events.append(e))

    monitor = make_monitor(bus)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_response = AsyncMock()
        mock_response.is_success = True
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await monitor._run_once()
        await asyncio.sleep(0)

    assert len(events) == 1
    assert events[0].service == "llm"


# --------------------------------------------------------------------------- #
# BackendHeartbeatFailed emitted on failure
# --------------------------------------------------------------------------- #

async def test_failing_service_emits_heartbeat_failed(bus):
    events: list = []
    bus.subscribe(BackendHeartbeatFailed, lambda e: events.append(e))

    monitor = make_monitor(bus)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await monitor._run_once()
        await asyncio.sleep(0)

    assert len(events) == 1
    assert events[0].consecutive_failures == 1


# --------------------------------------------------------------------------- #
# ONLINE → DEGRADED after 3 consecutive failures
# --------------------------------------------------------------------------- #

async def test_mode_transitions_to_degraded_after_threshold(bus):
    mode_events: list[RobotModeChanged] = []
    bus.subscribe(RobotModeChanged, lambda e: mode_events.append(e))

    monitor = make_monitor(bus, failure_threshold=3)
    assert monitor.mode == RobotMode.ONLINE

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # Run 3 times — failure count hits threshold on 3rd run
        for _ in range(3):
            await monitor._run_once()
            await asyncio.sleep(0)

    assert monitor.mode == RobotMode.DEGRADED
    assert any(e.to_mode == RobotMode.DEGRADED for e in mode_events)


# --------------------------------------------------------------------------- #
# DEGRADED → RECOVERING when all healthy
# --------------------------------------------------------------------------- #

async def test_mode_transitions_to_recovering_when_healthy(bus):
    monitor = make_monitor(bus, failure_threshold=1)

    # Drive to DEGRADED
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client
        await monitor._run_once()
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.DEGRADED

    # Now services recover
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_response = AsyncMock()
        mock_response.is_success = True
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client
        await monitor._run_once()
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.RECOVERING


# --------------------------------------------------------------------------- #
# RECOVERING → ONLINE after stability window
# --------------------------------------------------------------------------- #

async def test_mode_transitions_to_online_after_stability_window(bus):
    # stability_window_s=0 → transitions to ONLINE immediately on next healthy check
    monitor = make_monitor(bus, failure_threshold=1, stability_window_s=0.0)

    mock_fail = AsyncMock(side_effect=Exception("down"))
    mock_ok_response = AsyncMock()
    mock_ok_response.is_success = True
    mock_ok = AsyncMock(return_value=mock_ok_response)

    def _make_mock_client(get_fn):
        m = AsyncMock()
        m.get = get_fn
        m.__aenter__ = AsyncMock(return_value=m)
        m.__aexit__ = AsyncMock(return_value=False)
        return m

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _make_mock_client(mock_fail)
        await monitor._run_once()
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.DEGRADED

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _make_mock_client(mock_ok)
        await monitor._run_once()   # → RECOVERING
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.RECOVERING

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _make_mock_client(mock_ok)
        await monitor._run_once()   # → ONLINE (stability_window=0)
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.ONLINE


# --------------------------------------------------------------------------- #
# RECOVERING → DEGRADED if health lost again
# --------------------------------------------------------------------------- #

async def test_recovering_drops_back_to_degraded_on_failure(bus):
    monitor = make_monitor(bus, failure_threshold=1, stability_window_s=999.0)

    mock_fail = AsyncMock(side_effect=Exception("down"))
    mock_ok_response = AsyncMock()
    mock_ok_response.is_success = True
    mock_ok = AsyncMock(return_value=mock_ok_response)

    def _mk(get_fn):
        m = AsyncMock()
        m.get = get_fn
        m.__aenter__ = AsyncMock(return_value=m)
        m.__aexit__ = AsyncMock(return_value=False)
        return m

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mk(mock_fail)
        await monitor._run_once()
        await asyncio.sleep(0)

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mk(mock_ok)
        await monitor._run_once()
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.RECOVERING

    with patch("httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mk(mock_fail)
        await monitor._run_once()
        await asyncio.sleep(0)

    assert monitor.mode == RobotMode.DEGRADED
