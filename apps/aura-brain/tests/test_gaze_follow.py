"""U325: perception knows WHERE the face is, and he turns toward it.

`_area()` computed the bounding box purely to sort faces by size and threw the
position away, and `PersonRecognized` carries identity only — so the app knew
Jan was in the room and never knew he was standing to the left. All looking was
delegated to the daemon's tracker; when that had no lock, nothing in the brain
could point the head (aim() switches follow-me off).

Now the same frame the recogniser already decoded also says where the face is,
and the loop nudges him toward it — a second, slow tracker that works exactly
when the daemon's has lost you.
"""

from __future__ import annotations

import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest
from aura_brain.perception import PerceptionLoop


class _Robot:
    """Camera + gaze. `fail` makes the runtime answer like an older Pi."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.nudges: list[tuple[float, float]] = []
        self.frames = 0
        self._fail = fail

    async def camera_frame(self) -> bytes:
        self.frames += 1
        return b"jpeg"

    async def gaze(self, dyaw: float = 0.0, dpitch: float = 0.0) -> dict:
        if self._fail is not None:
            raise self._fail
        self.nudges.append((dyaw, dpitch))
        return {"moved": True}


class _Embedder:
    """Returns faces already located in the frame, nearest first."""

    name = "fake-located"

    def __init__(self, located=()) -> None:
        self.located = list(located)

    def embed(self, frame: bytes):
        return self.located[0][0] if self.located else None

    def embed_all(self, frame: bytes):
        return [e for e, _ in self.located]

    def embed_all_located(self, frame: bytes):
        return self.located


class _Bus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)


def _loop(embedder, robot) -> PerceptionLoop:
    return PerceptionLoop(_Bus(), None, robot, embedder, interval_s=0.01)


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.delenv("GAZE_FOLLOW", raising=False)
    monkeypatch.setenv("GAZE_DEADZONE", "0.12")


async def test_he_turns_toward_a_face_that_is_off_to_the_side() -> None:
    robot = _Robot()
    # a face to the right of the picture and a little high
    loop = _loop(_Embedder([([0.1] * 8, (0.6, -0.3, 0.05))]), robot)
    await loop.tick()
    assert robot.nudges, "a face off to the side must move him"
    dyaw, dpitch = robot.nudges[0]
    assert dyaw > 0, "+dyaw is toward the right of the picture (U164's frame)"
    assert dpitch < 0, "the face sits above centre, so he looks up"
    assert abs(dyaw) <= 1.0 and abs(dpitch) <= 1.0


async def test_he_does_not_twitch_at_someone_he_is_already_facing() -> None:
    """Without a deadzone he would chase the noise in every frame."""
    robot = _Robot()
    loop = _loop(_Embedder([([0.1] * 8, (0.03, -0.02, 0.05))]), robot)
    await loop.tick()
    assert robot.nudges == []


async def test_an_empty_frame_moves_nothing() -> None:
    robot = _Robot()
    await _loop(_Embedder([]), robot).tick()
    assert robot.nudges == []


async def test_the_nearest_face_is_the_one_he_looks_at() -> None:
    """Same rule as recognition: the person in front of him wins (U288)."""
    robot = _Robot()
    loop = _loop(_Embedder([
        ([0.1] * 8, (0.5, 0.0, 0.20)),    # nearest (largest), to the right
        ([0.2] * 8, (-0.7, 0.0, 0.02)),   # far away, to the left
    ]), robot)
    await loop.tick()
    assert robot.nudges[0][0] > 0


async def test_gaze_following_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("GAZE_FOLLOW", "false")
    robot = _Robot()
    await _loop(_Embedder([([0.1] * 8, (0.6, 0.0, 0.05))]), robot).tick()
    assert robot.nudges == []


async def test_an_older_runtime_is_tolerated_and_not_asked_twice() -> None:
    """Constitution X: the Pi is older than the app. A 404 must degrade, not
    raise into the camera loop — and not be retried every two seconds."""
    import httpx

    def _404() -> Exception:
        request = httpx.Request("POST", "http://robot/robot/gaze")
        response = httpx.Response(404, request=request)
        return httpx.HTTPStatusError("not found", request=request, response=response)

    robot = _Robot(fail=_404())
    loop = _loop(_Embedder([([0.1] * 8, (0.6, 0.0, 0.05))]), robot)
    await loop.tick()
    await loop.tick()
    await loop.tick()
    assert robot.frames == 3, "the camera loop keeps running"
    assert loop._gaze_supported is False


async def test_a_camera_glitch_never_reaches_the_loop() -> None:
    robot = _Robot(fail=RuntimeError("boom"))
    loop = _loop(_Embedder([([0.1] * 8, (0.6, 0.0, 0.05))]), robot)
    await loop.tick()          # must not raise
    assert robot.frames == 1


async def test_an_embedder_without_positions_still_works() -> None:
    """Every injected fake (and an older embedder) only has embed_all."""
    class Plain:
        name = "plain"

        def embed_all(self, frame: bytes):
            return [[0.1] * 8]

        def embed(self, frame: bytes):
            return [0.1] * 8

    robot = _Robot()
    loop = PerceptionLoop(_Bus(), None, robot, Plain(), interval_s=0.01)
    await loop.tick()
    assert robot.nudges == []
