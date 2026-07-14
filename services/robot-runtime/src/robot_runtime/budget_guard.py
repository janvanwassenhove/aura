"""U26: on-Pi budget guard — keep the robot responsive under load.

The Pi 4 in the Reachy Mini runs the daemon, media pipeline and this runtime;
a hot or saturated Pi turns motions jerky and audio choppy. The guard samples
CPU, memory and SoC temperature and flips a CONSTRAINED flag when any budget
is exceeded. Consumers (idle animations, camera cadence) check the flag and
shed non-essential work; ``GET /robot/budget`` exposes it for the console.

Readers are injectable so the logic is unit-tested off-Pi; the default readers
use /proc and /sys (Linux) and degrade to "unconstrained" elsewhere.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)


# ── default readers (Linux/Pi; graceful None elsewhere) ────────────────

_last_cpu: tuple[int, int] | None = None


def read_cpu_pct() -> float | None:
    """CPU utilisation since the previous call (first call returns None)."""
    global _last_cpu
    try:
        with open("/proc/stat", encoding="ascii") as f:
            fields = [int(x) for x in f.readline().split()[1:]]
    except (OSError, ValueError):
        return None
    idle, total = fields[3] + fields[4], sum(fields)
    if _last_cpu is None:
        _last_cpu = (idle, total)
        return None
    d_idle, d_total = idle - _last_cpu[0], total - _last_cpu[1]
    _last_cpu = (idle, total)
    if d_total <= 0:
        return None
    return 100.0 * (1.0 - d_idle / d_total)


def read_mem_pct() -> float | None:
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])
        total, avail = info["MemTotal"], info["MemAvailable"]
    except (OSError, KeyError, ValueError, IndexError):
        return None
    return 100.0 * (1.0 - avail / total) if total else None


def read_temp_c() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", encoding="ascii") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


# ── the guard ──────────────────────────────────────────────────────────

class BudgetGuard:
    def __init__(
        self,
        cpu_reader: Callable[[], float | None] = read_cpu_pct,
        mem_reader: Callable[[], float | None] = read_mem_pct,
        temp_reader: Callable[[], float | None] = read_temp_c,
        interval_s: float = 5.0,
    ) -> None:
        self._read_cpu = cpu_reader
        self._read_mem = mem_reader
        self._read_temp = temp_reader
        self._interval = interval_s
        self._cpu_budget = float(os.environ.get("BUDGET_CPU_PCT", "85"))
        self._mem_budget = float(os.environ.get("BUDGET_MEM_PCT", "90"))
        self._temp_budget = float(os.environ.get("BUDGET_TEMP_C", "75"))
        self._constrained = False
        self._reasons: list[str] = []
        self._snapshot: dict = {}
        self._task: asyncio.Task | None = None

    @property
    def constrained(self) -> bool:
        return self._constrained

    def status(self) -> dict:
        return {
            "constrained": self._constrained,
            "reasons": list(self._reasons),
            **self._snapshot,
            "budgets": {"cpu_pct": self._cpu_budget, "mem_pct": self._mem_budget,
                        "temp_c": self._temp_budget},
        }

    def sample(self) -> bool:
        """Take one sample; returns the (new) constrained state."""
        cpu, mem, temp = self._read_cpu(), self._read_mem(), self._read_temp()
        self._snapshot = {"cpu_pct": cpu, "mem_pct": mem, "temp_c": temp}
        reasons = []
        if cpu is not None and cpu > self._cpu_budget:
            reasons.append(f"cpu {cpu:.0f}% > {self._cpu_budget:.0f}%")
        if mem is not None and mem > self._mem_budget:
            reasons.append(f"mem {mem:.0f}% > {self._mem_budget:.0f}%")
        if temp is not None and temp > self._temp_budget:
            reasons.append(f"temp {temp:.0f}°C > {self._temp_budget:.0f}°C")
        newly = bool(reasons)
        if newly != self._constrained:
            logger.warning("budget guard: %s (%s)",
                           "CONSTRAINED" if newly else "recovered",
                           "; ".join(reasons) or "all within budget")
        self._constrained = newly
        self._reasons = reasons
        return newly

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_event_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                self.sample()
            except Exception as exc:  # noqa: BLE001 — the guard must never die
                logger.debug("budget sample failed: %s", exc)
            await asyncio.sleep(self._interval)
