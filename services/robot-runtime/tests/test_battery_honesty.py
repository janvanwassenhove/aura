"""U270: the battery reading must be measured, or absent — never invented.

Asked as "kunnen we batterij status toevoegen (indien versie met batterij)".
The "indien" turned out to be the whole problem. `ReachyRobotAdapter.get_status`
returned `battery_pct=100.0` with the comment "SDK exposes no battery reading
yet", and the setup wizard printed that as "battery 100%" — so the first thing
an owner read about their robot was a full charge nobody had measured. A full
battery is the most reassuring thing a status line can say, which makes it the
worst thing to make up.

Firmware 1.9.0 answers 93 routes and not one mentions battery, power or
charge; even /api/state/full carries only pose. But it DOES report
`wireless_version`, which answers the owner's actual question: is there a
battery in this robot at all.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from robot_runtime.adapters.reachy import ReachyRobotAdapter


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _adapter() -> ReachyRobotAdapter:
    return ReachyRobotAdapter(host="robot.test")


async def test_a_wireless_robot_has_a_battery_but_no_reading() -> None:
    """Exactly what the owner's robot reports today."""
    a = _adapter()
    with patch("urllib.request.urlopen", return_value=_Resp({
        "type": "daemon_status", "robot_name": "reachy_mini",
        "state": "running", "wireless_version": True,
    })):
        st = await a.get_status()

    assert st.has_battery is True        # there IS one to ask about...
    assert st.battery_pct is None        # ...and nothing has measured it


async def test_a_wired_robot_reports_no_battery_at_all() -> None:
    a = _adapter()
    with patch("urllib.request.urlopen", return_value=_Resp({
        "state": "running", "wireless_version": False,
    })):
        st = await a.get_status()

    assert st.has_battery is False
    assert st.battery_pct is None


async def test_a_firmware_that_grows_a_reading_is_used_as_is() -> None:
    """The day the daemon reports a level, nothing else has to change."""
    a = _adapter()
    with patch("urllib.request.urlopen", return_value=_Resp({
        "wireless_version": True, "battery_pct": 42,
    })):
        st = await a.get_status()

    assert st.has_battery is True
    assert st.battery_pct == 42.0


async def test_an_unreachable_daemon_says_unknown_not_full() -> None:
    """The old code answered 100% to this. Silence is the honest answer."""
    a = _adapter()
    with patch("urllib.request.urlopen", side_effect=OSError("no route to host")):
        st = await a.get_status()

    assert st.has_battery is None
    assert st.battery_pct is None
