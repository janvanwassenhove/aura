"""U336: he changes address, and AURA finds him again by itself.

Asked as "kunnen we alles niet comfortabeler maken vanuit aura?", about taking
the laptop and the robot to a conference or to work.

What made it uncomfortable: the brain reads the robot's address once, at
startup, and never looks again. Move to another network — a phone hotspot, an
office — and the robot gets a new address from DHCP, while the brain keeps
calling the old one. Everything then says "offline", correctly and uselessly,
until the owner opens the Robot panel, presses Scan my network and picks the
new address by hand. `/robot/discover` has existed since U200; nothing ever
called it on its own.

So: when the address stops answering, look for him — the address we have, then
his mDNS name, then every host on our own /24 (the bound U200 already set) —
and adopt the first thing that answers like a robot.

What this cannot do, and no amount of app can: put him on a Wi-Fi network he is
not on yet. If he cannot reach the network, nothing here can reach him. That
part stays a one-time job at home.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.robot_finder import MDNS_URL, find_robot, watch_address

HOME = "http://192.168.0.178:8001"
HOTSPOT = "http://192.168.43.51:8001"


def _prober(*answering: str):
    """A probe that says yes only for the addresses given."""
    seen: list[str] = []

    async def probe(url: str) -> bool:
        seen.append(url)
        return url in answering

    probe.seen = seen  # type: ignore[attr-defined]
    return probe


def _hosts(*ips: str):
    return lambda: list(ips)


async def test_the_address_we_have_is_tried_first_and_nothing_else() -> None:
    """The common case must cost one request, not a network sweep."""
    probe = _prober(HOME)
    assert await find_robot(HOME, probe=probe, scan_hosts=_hosts("192.168.0.1")) == HOME
    assert probe.seen == [HOME]


async def test_his_name_is_tried_before_the_whole_network() -> None:
    probe = _prober(MDNS_URL)
    found = await find_robot(HOME, probe=probe, scan_hosts=_hosts("192.168.43.51"))
    assert found == MDNS_URL
    assert probe.seen[:2] == [HOME, MDNS_URL], probe.seen


async def test_otherwise_he_is_found_on_the_new_network() -> None:
    """A phone hotspot hands out a different subnet entirely."""
    probe = _prober(HOTSPOT)
    found = await find_robot(HOME, probe=probe,
                             scan_hosts=_hosts("192.168.43.10", "192.168.43.51"))
    assert found == HOTSPOT


async def test_something_else_on_that_port_is_not_adopted() -> None:
    """Port 8001 is not proof. Only a robot-shaped answer counts — otherwise a
    printer becomes the robot and every call fails in a new way."""
    probe = _prober()          # nothing answers like a robot
    assert await find_robot(HOME, probe=probe, scan_hosts=_hosts("192.168.0.9")) is None


async def test_no_address_yet_still_searches() -> None:
    probe = _prober(HOTSPOT)
    assert await find_robot("", probe=probe, scan_hosts=_hosts("192.168.43.51")) == HOTSPOT


# ── the watch ──────────────────────────────────────────────────────────────

async def test_it_looks_nowhere_while_he_answers() -> None:
    adopted: list[str] = []
    probe = _prober(HOME)
    task = asyncio.ensure_future(watch_address(
        lambda: HOME, adopted.append, interval_s=0.01, probe=probe,
        scan_hosts=_hosts("192.168.43.51")))
    await asyncio.sleep(0.08)
    task.cancel()
    assert adopted == [], "it moved house while he was still home"


async def test_it_adopts_the_new_address_once_the_old_one_goes_quiet() -> None:
    adopted: list[str] = []
    probe = _prober(HOTSPOT)          # only the hotspot answers now
    task = asyncio.ensure_future(watch_address(
        lambda: HOME, adopted.append, interval_s=0.01, probe=probe,
        scan_hosts=_hosts("192.168.43.51")))
    try:
        for _ in range(50):
            if adopted:
                break
            await asyncio.sleep(0.02)
    finally:
        task.cancel()
    assert adopted and adopted[0] == HOTSPOT


async def test_it_adopts_once_not_once_a_tick() -> None:
    """Adopting rewrites the stored address; doing it every tick would churn
    the settings file and the log for no reason."""
    current = HOME
    adopted: list[str] = []

    def _adopt(url: str) -> None:
        nonlocal current
        current = url
        adopted.append(url)

    probe = _prober(HOTSPOT)
    task = asyncio.ensure_future(watch_address(
        lambda: current, _adopt, interval_s=0.01, probe=probe,
        scan_hosts=_hosts("192.168.43.51")))
    try:
        for _ in range(50):
            if adopted:
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)       # keep ticking, now that he answers
    finally:
        task.cancel()
    assert len(adopted) == 1, adopted


async def test_a_failure_in_the_search_never_kills_the_watch() -> None:
    calls = {"n": 0}

    async def _angry(url: str) -> bool:
        calls["n"] += 1
        raise OSError("network unreachable")

    task = asyncio.ensure_future(watch_address(
        lambda: HOME, lambda url: None, interval_s=0.01, probe=_angry,
        scan_hosts=_hosts("192.168.43.51")))
    await asyncio.sleep(0.08)
    alive = not task.done()
    task.cancel()
    assert alive and calls["n"] > 1, "the watch died on the first bad network"


def test_it_can_be_switched_off(monkeypatch) -> None:
    from aura_brain.robot_finder import autofind_enabled

    assert autofind_enabled() is True
    monkeypatch.setenv("ROBOT_AUTOFIND", "false")
    assert autofind_enabled() is False
