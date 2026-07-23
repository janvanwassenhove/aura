"""U36: /robot proxy — console reaches the robot through the brain."""

from __future__ import annotations

import httpx
import pytest
from aura_brain import robot_api
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeRobotClient:
    def __init__(self, *, up: bool = True) -> None:
        self.up = up
        self.motions: list = []
        self.spoken: list[tuple[str, str | None]] = []

    def _check(self) -> None:
        if not self.up:
            raise httpx.ConnectError("robot down")

    async def status(self) -> dict:
        self._check()
        return {"mode": "online", "connected": True, "adapter_name": "reachy"}

    async def camera_frame(self) -> bytes:
        self._check()
        return b"\x89PNG-fake"

    async def execute_motion(self, command) -> bool:
        self._check()
        self.motions.append(command)
        return True

    async def speak(self, text: str, audio_b64: str | None = None) -> bool:
        self._check()
        self.spoken.append((text, audio_b64))
        return True


@pytest.fixture()
def client_and_robot():
    robot = FakeRobotClient()
    robot_api.init(robot)
    app = FastAPI()
    app.include_router(robot_api.router)
    yield TestClient(app), robot
    robot_api.init(None)


def test_status_proxies_robot_state(client_and_robot) -> None:
    client, _ = client_and_robot
    body = client.get("/robot/status").json()
    assert body["adapter_name"] == "reachy"


def test_camera_frame_returns_png_bytes(client_and_robot) -> None:
    client, _ = client_and_robot
    resp = client.get("/robot/camera/frame")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")


def test_motion_forwards_command(client_and_robot) -> None:
    client, robot = client_and_robot
    resp = client.post("/robot/motion", json={"motion_id": "wave", "amplitude": 0.6})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert robot.motions[0].motion_id == "wave"


def test_say_synthesizes_and_speaks(client_and_robot, monkeypatch) -> None:
    from aura_brain import voice

    async def fake_tts(text: str) -> str:
        return "UEND-b64"

    monkeypatch.setattr(voice, "synthesize_b64", fake_tts)
    client, robot = client_and_robot
    resp = client.post("/robot/say", json={"text": "Hallo Jan!"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "voiced": True}
    assert robot.spoken == [("Hallo Jan!", "UEND-b64")]


def test_say_degrades_to_text_only_without_tts(client_and_robot, monkeypatch) -> None:
    from aura_brain import voice

    async def no_tts(text: str) -> None:
        return None

    monkeypatch.setattr(voice, "synthesize_b64", no_tts)
    client, robot = client_and_robot
    resp = client.post("/robot/say", json={"text": "stil"})
    assert resp.json() == {"ok": True, "voiced": False}
    assert robot.spoken == [("stil", None)]


def test_say_requires_text(client_and_robot) -> None:
    client, _ = client_and_robot
    assert client.post("/robot/say", json={}).status_code == 422


def test_unreachable_robot_returns_503() -> None:
    robot_api.init(FakeRobotClient(up=False))
    app = FastAPI()
    app.include_router(robot_api.router)
    client = TestClient(app)
    try:
        assert client.get("/robot/status").status_code == 503
        assert client.get("/robot/camera/frame").status_code == 503
        assert client.post("/robot/motion", json={"motion_id": "nod"}).status_code == 503
    finally:
        robot_api.init(None)


# ------------------------------------------------------------------
# U196: the live view must survive a robot older than this app
# ------------------------------------------------------------------

def _jpeg(width: int = 1280, height: int = 720, seed: int = 0) -> bytes:
    import io

    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_camera_probe():
    """Each test decides for itself what the robot supports."""
    robot_api._robot_has_frame_jpg = None
    robot_api._LATEST["jpeg"] = b""
    robot_api._LATEST["task"] = None
    yield
    robot_api._robot_has_frame_jpg = None
    robot_api._LATEST["jpeg"] = b""
    robot_api._LATEST["task"] = None


async def test_frame_jpg_prefers_the_robots_own_endpoint(monkeypatch) -> None:
    """A current robot downscales at the source — far less over the WiFi hop."""
    payload = _jpeg(640, 360)

    class _Resp:
        status_code = 200
        content = payload

    class _Client:
        async def get(self, url, *a, **k):
            assert url.endswith("/robot/camera/frame.jpg")
            return _Resp()

    monkeypatch.setattr(robot_api, "_client", lambda: _Client())
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": "http://r"})())

    resp = _client_for(robot_api).get("/robot/camera/frame.jpg")
    assert resp.status_code == 200
    assert resp.content == payload
    assert robot_api._robot_has_frame_jpg is True


async def test_frame_jpg_falls_back_when_the_robot_is_older(monkeypatch) -> None:
    """The case measured on the owner's own setup.

    The desktop app updates itself; the Pi does not. A live check found it
    still serving unscaled 1280x720 frames — code from before U188 — so the
    robot has no /camera/frame.jpg. Requiring it would answer 404 and the panel
    would read "No camera feed": a fix that breaks the thing it fixes.
    """
    class _Resp404:
        status_code = 404
        content = b""

    class _Client:
        async def get(self, url, *a, **k):
            return _Resp404()

    monkeypatch.setattr(robot_api, "_client", lambda: _Client())
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": "http://r"})())

    # The background reader stands in for "a frame arrived off the MJPEG stream".
    async def _fake_pump() -> None:
        robot_api._LATEST["jpeg"] = _jpeg(640, 360, seed=3)

    monkeypatch.setattr(robot_api, "_pump_latest_frame", _fake_pump)

    resp = _client_for(robot_api).get("/robot/camera/frame.jpg")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xff\xd8")
    assert robot_api._robot_has_frame_jpg is False   # probed once, remembered


def test_shrink_downscales_a_legacy_frame() -> None:
    """An old robot's 1280px frame renders into a panel a few hundred px wide."""
    import io

    from PIL import Image

    big = _jpeg(1280, 720, seed=5)
    small = robot_api._shrink(big)
    assert Image.open(io.BytesIO(small)).width == robot_api._FALLBACK_WIDTH
    assert len(small) < len(big)


def test_shrink_never_loses_the_picture_on_bad_input() -> None:
    assert robot_api._shrink(b"not a jpeg") == b"not a jpeg"


def _client_for(mod) -> TestClient:
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


# ------------------------------------------------------------------
# U198: say WHY the robot is unreachable, not just that it is
# ------------------------------------------------------------------

def test_diagnose_names_the_three_causes(monkeypatch) -> None:
    """Each cause needs a different action from the owner:

    - the name does not resolve  -> use an IP, mDNS is not working
    - the connection is refused  -> robot-runtime is not running there
    - it times out               -> wrong network / WiFi down

    "Robot: offline" pointed at none of them; the exception knew all along.
    """
    monkeypatch.setattr(
        robot_api, "_robot",
        type("R", (), {"_base_url": "http://reachy-mini.local:8001"})())

    dns = robot_api._diagnose(
        httpx.ConnectError("[Errno 11001] getaddrinfo failed"))
    assert "resolve" in dns and "ROBOT_RUNTIME_URL" in dns

    refused = robot_api._diagnose(httpx.ConnectError("Connection refused"))
    assert "robot-runtime is not running" in refused

    slow = robot_api._diagnose(httpx.ConnectTimeout("timed out"))
    assert "did not answer in time" in slow

    for text in (dns, refused, slow):
        assert "reachy-mini.local:8001" in text   # always name the host tried


def test_status_failure_carries_the_reason(monkeypatch) -> None:
    """The console renders this sentence; a bare 503 leaves it guessing."""
    class _Down:
        _base_url = "http://reachy-mini.local:8001"

        async def status(self):
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(robot_api, "_robot", _Down())
    resp = _client_for(robot_api).get("/robot/status")
    assert resp.status_code == 503
    body = resp.json()
    assert body["reason"]
    assert body["robot_url"] == "http://reachy-mini.local:8001"


# ------------------------------------------------------------------
# U199: the owner can point the brain at a different robot
# ------------------------------------------------------------------

def test_set_address_persists_and_applies_live(monkeypatch, tmp_path) -> None:
    """U198 told the owner to set ROBOT_RUNTIME_URL; that meant editing a file
    inside the app's data directory. Advice with nowhere to act on it is worse
    than none, so the address is settable — and takes effect without a restart.
    """
    import os

    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))

    class _R:
        _base_url = "http://reachy-mini.local:8001"
        async def status(self): return {}

    robot = _R()
    monkeypatch.setattr(robot_api, "_robot", robot)

    resp = _client_for(robot_api).post(
        "/robot/address", json={"url": "http://192.168.0.42:8001"})
    assert resp.status_code == 200
    assert resp.json()["url"] == "http://192.168.0.42:8001"
    assert robot._base_url == "http://192.168.0.42:8001"      # live, no restart
    assert os.environ["ROBOT_RUNTIME_URL"] == "http://192.168.0.42:8001"
    assert "192.168.0.42" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_set_address_adds_a_missing_scheme(monkeypatch, tmp_path) -> None:
    """Owners type '192.168.0.42:8001'. Refusing that on a technicality, while
    the panel is already telling them something is broken, is unkind."""
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())

    resp = _client_for(robot_api).post(
        "/robot/address", json={"url": "192.168.0.42:8001"})
    assert resp.json()["url"] == "http://192.168.0.42:8001"


def test_set_address_rejects_empty_and_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())
    client = _client_for(robot_api)

    assert client.post("/robot/address", json={"url": "  "}).status_code == 422
    # A path here silently breaks every route built on top of it.
    assert client.post(
        "/robot/address",
        json={"url": "http://192.168.0.42:8001/robot"}).status_code == 422


def test_set_address_reports_an_unreachable_robot(monkeypatch, tmp_path) -> None:
    """Saving must not imply it worked — the whole point is to find out."""
    monkeypatch.setenv("AURA_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())

    resp = _client_for(robot_api).post(
        "/robot/address", json={"url": "http://127.0.0.1:9"})   # nothing listens
    body = resp.json()
    assert resp.status_code == 200          # it IS saved
    assert body["reachable"] is False       # but honestly reported
    assert body["detail"]


# ------------------------------------------------------------------
# U200: find the robot, because you cannot type an address you don't know
# ------------------------------------------------------------------

def test_discover_finds_a_robot_on_the_lan(monkeypatch) -> None:
    """Proven on the owner's own network: the robot sat at 192.168.0.178 while
    its .local name refused to resolve AND ping sweeps missed it entirely (a Pi
    need not answer ICMP). Knocking on the port finds what naming and pinging
    both missed.

    A plain threaded HTTP server, not uvicorn: TestClient drives the endpoint on
    its own event loop, so a stub living in the test's loop would sit frozen for
    the whole call and the test would fail for a reason that is not the code.
    """
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Health(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib's name
            body = json.dumps({
                "status": "ok",
                "robot": {"mode": "online", "adapter_name": "reachy"},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # keep pytest output readable
            return

    srv = HTTPServer(("127.0.0.1", 8001), _Health)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())
        # Aim the sweep at loopback — a test must never scan a real LAN. The
        # target list is the seam; interface filtering has its own test below.
        monkeypatch.setattr(robot_api, "_scan_targets", lambda: ["127.0.0.1"])

        body = _client_for(robot_api).get("/robot/discover").json()
        assert body["found"] == [
            {"url": "http://127.0.0.1:8001", "adapter": "reachy", "mode": "online"}
        ]
    finally:
        srv.shutdown()
        srv.server_close()


def test_discover_ignores_something_else_on_port_8001(monkeypatch) -> None:
    """An open port is not a robot. Offering a printer as a robot would send
    the owner chasing a setting that can never work."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _NotARobot(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'{"status": "ok"}'          # no "robot" key
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            return

    srv = HTTPServer(("127.0.0.1", 8001), _NotARobot)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())
        monkeypatch.setattr(robot_api, "_scan_targets", lambda: ["127.0.0.1"])
        assert _client_for(robot_api).get("/robot/discover").json()["found"] == []
    finally:
        srv.shutdown()
        srv.server_close()


def test_local_ipv4s_skips_loopback_and_leaseless_adapters(monkeypatch) -> None:
    """169.254.x means an adapter with no DHCP lease — the owner's WiFi was in
    exactly that state. Scanning it (or loopback) finds nothing and burns the
    seconds someone is watching a spinner for."""
    import socket as _socket

    monkeypatch.setattr(
        _socket, "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("169.254.244.48", 0)),
                         (None, None, None, None, ("127.0.0.1", 0)),
                         (None, None, None, None, ("192.168.0.214", 0))])

    assert robot_api._local_ipv4s() == ["192.168.0.214"]


def test_discover_reports_when_there_is_nothing_to_scan(monkeypatch) -> None:
    monkeypatch.setattr(robot_api, "_robot", type("R", (), {"_base_url": ""})())
    monkeypatch.setattr(robot_api, "_scan_targets", lambda: [])

    body = _client_for(robot_api).get("/robot/discover").json()
    assert body["scanned"] == 0
    assert body["found"] == []
    assert body["note"]
