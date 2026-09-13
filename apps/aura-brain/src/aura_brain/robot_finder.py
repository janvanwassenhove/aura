"""U336: the robot changes address, and the brain finds him again.

The address is read once, at startup, and never looked at again. Take the
laptop and the robot to another network — a phone hotspot at a conference, an
office — and DHCP hands him a different address while the brain keeps calling
the old one. Everything then reports "offline": correct, and useless, until
somebody opens the Robot panel, presses *Scan my network* and picks the new
address by hand. The sweep behind that button has existed since U200; nothing
ever called it on its own.

So this watches the address the brain is using, and when it stops answering it
looks in the cheapest order:

1. the address we already have — one request, and the usual answer;
2. `reachy-mini.local`, which costs nothing and often works on a small network;
3. every host on our own /24, which is the bound U200 chose and this keeps:
   never wider than the owner's subnet.

Only something that answers **like a robot** is adopted. An open port 8001 is
not proof; a printer that accepts connections would otherwise become "the
robot" and every later call would fail in a new and confusing way.

What this cannot do — and no amount of app can — is put him on a network he is
not on. If he cannot reach the Wi-Fi, nothing here can reach him; that stays a
one-time job at home (his own setup mode, or one `nmcli` line over SSH).
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

#: The name the robot answers to on a small network, and what the deploy
#: script has always used.
MDNS_URL = "http://reachy-mini.local:8001"

#: The port robot-runtime listens on.
PORT = 8001

Probe = Callable[[str], Awaitable[bool]]


def autofind_enabled() -> bool:
    return os.environ.get("ROBOT_AUTOFIND", "true").lower() == "true"


def local_ipv4s() -> list[str]:
    """Every IPv4 address this machine holds, link-local excluded."""
    import socket

    out: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")):
                out.append(ip)
    except OSError:
        pass
    return sorted(set(out))


def scan_hosts() -> list[str]:
    """Every host on our own /24s — never wider than the owner's subnet."""
    import ipaddress

    hosts: list[str] = []
    for ip in local_ipv4s():
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
        hosts.extend(str(h) for h in net.hosts())
    return hosts


async def looks_like_a_robot(url: str, timeout_s: float = 1.5) -> bool:
    """Does whatever is at this address answer like robot-runtime?

    `/health` is the one route that stays open without the shared secret (U220)
    precisely so it can be found; it reports mode and battery, never the camera
    or the microphone.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(f"{url.rstrip('/')}/health")
            if resp.status_code != 200:
                return False
            body = resp.json()
    except Exception:  # noqa: BLE001 — anything that is not an answer is a no
        return False
    return isinstance(body, dict) and isinstance(body.get("robot"), dict)


async def find_robot(
    current: str = "",
    probe: Probe | None = None,
    scan_hosts: Callable[[], list[str]] | None = None,
) -> str | None:
    """Where is he now? The first address that answers like a robot, or None."""
    ask = probe or looks_like_a_robot
    hosts = (scan_hosts or globals()["scan_hosts"])()

    candidates: list[str] = []
    for url in [current.rstrip("/") if current else "", MDNS_URL,
                *(f"http://{host}:{PORT}" for host in hosts)]:
        if url and url not in candidates:
            candidates.append(url)

    for url in candidates:
        try:
            if await ask(url):
                return url
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a dead host is not an error
            logger.debug("probe failed for %s: %s", url, exc)
    return None


async def watch_address(
    current: Callable[[], str],
    adopt: Callable[[str], None],
    interval_s: float = 30.0,
    probe: Probe | None = None,
    scan_hosts: Callable[[], list[str]] | None = None,
) -> None:
    """Keep the brain pointed at the robot. Runs until cancelled.

    While the current address answers this costs one request per interval and
    does nothing else. When it stops answering — a new network, a reboot, a
    different subnet — it searches once and adopts what it finds, exactly once
    per move: adopting rewrites the stored address, and doing that on every
    tick would churn the settings file and the log for no reason.
    """
    ask = probe or looks_like_a_robot
    while True:
        await asyncio.sleep(interval_s)
        try:
            here = current()
            if here and await ask(here):
                continue                      # still home
            found = await find_robot(here, probe=ask, scan_hosts=scan_hosts)
            if found and found != here:
                logger.info("the robot answers at %s now — pointing there", found)
                adopt(found)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a bad network is not fatal
            logger.debug("robot address watch: %s", exc)
