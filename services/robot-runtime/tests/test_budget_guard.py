"""U26: on-Pi budget guard — constrained state + idle-motion shedding."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from robot_runtime import routes
from robot_runtime.budget_guard import BudgetGuard


def _guard(cpu=None, mem=None, temp=None) -> BudgetGuard:
    return BudgetGuard(
        cpu_reader=lambda: cpu, mem_reader=lambda: mem, temp_reader=lambda: temp,
    )


def test_within_budget_is_unconstrained() -> None:
    g = _guard(cpu=40.0, mem=55.0, temp=60.0)
    assert g.sample() is False
    assert g.status()["constrained"] is False
    assert g.status()["reasons"] == []


def test_hot_soc_constrains(monkeypatch) -> None:
    monkeypatch.setenv("BUDGET_TEMP_C", "75")
    g = _guard(cpu=40.0, temp=82.0)
    assert g.sample() is True
    assert any("temp" in r for r in g.status()["reasons"])


def test_recovery_clears_constrained() -> None:
    readings = iter([95.0, 30.0])
    g = BudgetGuard(cpu_reader=lambda: next(readings),
                    mem_reader=lambda: None, temp_reader=lambda: None)
    assert g.sample() is True
    assert g.sample() is False


def test_none_readers_never_constrain() -> None:
    g = _guard()  # all readers return None (non-Linux dev box)
    assert g.sample() is False


async def test_idle_motion_is_shed_when_constrained() -> None:
    from robot_runtime.offline_loop import OfflineBehaviorLoop

    class Engine:
        def __init__(self) -> None:
            self.motions: list[str] = []

        async def add_motion(self, motion_id: str) -> None:
            self.motions.append(motion_id)

        async def speak(self, text: str) -> None:
            pass

    class Bus:
        async def publish(self, _e) -> None:
            pass

    engine = Engine()
    loop = OfflineBehaviorLoop(engine, Bus(), timeout_s=0.0)  # instantly 'offline'
    loop.budget_guard = _guard(cpu=99.0)
    loop.budget_guard.sample()
    await loop.check()
    assert engine.motions == []  # idle fidget shed under load

    loop.budget_guard = None
    await loop.check()
    assert engine.motions == ["idle_fidget"]  # normal behavior without a guard


def test_budget_route() -> None:
    app = FastAPI()
    app.include_router(routes.router)
    routes.budget_guard = _guard(cpu=99.0)
    routes.budget_guard.sample()
    try:
        data = TestClient(app).get("/robot/budget").json()
        assert data["constrained"] is True
        assert data["cpu_pct"] == 99.0
    finally:
        routes.budget_guard = None
