"""U18: GET /robot/camera/frame serves one PNG frame from the adapter."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from robot_runtime import routes
from robot_runtime.adapters.fake import FakeRobotAdapter


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


async def test_camera_frame_returns_png() -> None:
    adapter = FakeRobotAdapter()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().get("/robot/camera/frame")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content.startswith(b"\x89PNG")
    finally:
        routes.adapter = None


async def test_camera_unavailable_returns_503() -> None:
    class NoCamera(FakeRobotAdapter):
        async def get_camera_frame(self) -> bytes:
            raise RuntimeError("camera unavailable: media backend disabled")

    adapter = NoCamera()
    await adapter.connect()
    routes.adapter = adapter
    try:
        resp = _client().get("/robot/camera/frame")
        assert resp.status_code == 503
        assert "camera" in resp.json()["error"]
    finally:
        routes.adapter = None


# ---------------------------------------------------------------------------
# U188: stream bandwidth — the cause of the laggy video
# ---------------------------------------------------------------------------

def _jpeg(width: int, height: int) -> bytes:
    """A realistic camera-ish frame (noise, so JPEG can't cheat)."""
    import io

    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(42)
    arr = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def test_downscale_cuts_the_bytes_that_caused_the_lag() -> None:
    from robot_runtime.routes import downscale_jpeg

    full = _jpeg(1280, 720)          # what the robot used to send
    small = downscale_jpeg(full, 640, 70)

    import io

    from PIL import Image
    assert Image.open(io.BytesIO(small)).size == (640, 360)
    # The whole point: materially fewer bytes over WiFi per frame.
    assert len(small) < len(full) / 2, (
        f"{len(full)/1024:.0f} KB -> {len(small)/1024:.0f} KB is not enough")


def test_downscale_never_upscales_or_breaks_the_stream() -> None:
    from robot_runtime.routes import downscale_jpeg

    small = _jpeg(320, 180)
    assert downscale_jpeg(small, 640, 70) is small      # already smaller: untouched
    assert downscale_jpeg(b"", 640, 70) == b""          # nothing to do
    assert downscale_jpeg(b"not-a-jpeg", 640, 70) == b"not-a-jpeg"   # never raises
    assert downscale_jpeg(small, 0, 70) is small        # width 0 = full resolution
