"""U220 (S5): the Pi must not hand its camera and mic to the whole WiFi."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


def _app(monkeypatch, secret: str | None):
    """Build the app fresh — the guard is installed at create_app() time."""
    if secret is None:
        monkeypatch.delenv("ROBOT_SHARED_SECRET", raising=False)
    else:
        monkeypatch.setenv("ROBOT_SHARED_SECRET", secret)
    from robot_runtime import main as rr_main
    importlib.reload(rr_main)
    return rr_main.create_app()


def test_without_a_secret_nothing_changes(monkeypatch) -> None:
    """Opt-in: deploying this must never strand a robot whose brain has no
    secret yet."""
    with TestClient(_app(monkeypatch, None)) as c:
        assert c.get("/health").status_code == 200
        # A protected path is reachable exactly as before (503 = no adapter in
        # this bare app, NOT 401 — the point is that it isn't refused).
        assert c.get("/robot/camera/frame.jpg").status_code != 401


def test_with_a_secret_the_camera_needs_it(monkeypatch) -> None:
    with TestClient(_app(monkeypatch, "s3cr3t")) as c:
        # The LAN neighbour: no header, no camera, no mic, no motors.
        assert c.get("/robot/camera/frame.jpg").status_code == 401
        assert c.get("/robot/audio/stream").status_code == 401
        assert c.post("/robot/motion", json={"motion_id": "wave"}).status_code == 401
        # A wrong secret is refused too.
        assert c.get("/robot/camera/frame.jpg",
                     headers={"X-AURA-Secret": "wrong"}).status_code == 401
        # The brain, which knows it, is let through (not 401).
        assert c.get("/robot/camera/frame.jpg",
                     headers={"X-AURA-Secret": "s3cr3t"}).status_code != 401


def test_health_stays_open_for_discovery(monkeypatch) -> None:
    """The brain's LAN scan finds robots via /health; locking it would break
    'Find the robot' while revealing only mode/battery."""
    with TestClient(_app(monkeypatch, "s3cr3t")) as c:
        assert c.get("/health").status_code == 200


def test_brain_sends_the_secret(monkeypatch) -> None:
    """The other half: the header the robot checks is actually sent."""
    monkeypatch.setenv("ROBOT_SHARED_SECRET", "s3cr3t")
    from aura_brain.robot_client import robot_auth_headers
    assert robot_auth_headers() == {"X-AURA-Secret": "s3cr3t"}
    monkeypatch.delenv("ROBOT_SHARED_SECRET")
    assert robot_auth_headers() == {}
