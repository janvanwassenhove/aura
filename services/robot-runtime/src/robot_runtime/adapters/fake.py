"""FakeRobotAdapter — in-process simulation, no hardware required."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator
from typing import Any

import numpy as np

from shared_schemas.robot.adapter import RobotAdapter
from shared_schemas.robot.models import (
    BehaviorState,
    MotionCommand,
    MotionTimeline,
    RobotMode,
    RobotState,
)

logger = logging.getLogger(__name__)

_FAKE_AUDIO_SAMPLE_RATE = 16_000
_FAKE_FRAME_SHAPE = (480, 640, 3)


class FakeRobotAdapter(RobotAdapter):
    """Simulated robot adapter suitable for CI and offline development.

    Every method immediately resolves; audio and camera data are synthetic.
    """

    def __init__(self, adapter_name: str = "fake") -> None:
        self._adapter_name = adapter_name
        self._connected = False
        self._mode = RobotMode.OFFLINE
        self._behavior_state = BehaviorState.IDLE
        self._battery_pct: float = 100.0
        self._spoken: list[str] = []
        self._played_audio: list[bytes] = []
        self._motions: list[MotionCommand] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        await asyncio.sleep(0)  # yield to event loop
        self._connected = True
        self._mode = RobotMode.ONLINE
        logger.info("FakeRobotAdapter connected")

    async def disconnect(self) -> None:
        await asyncio.sleep(0)
        self._connected = False
        self._mode = RobotMode.OFFLINE
        logger.info("FakeRobotAdapter disconnected")

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def get_status(self) -> RobotState:
        return RobotState(
            mode=self._mode,
            behavior_state=self._behavior_state,
            battery_pct=self._battery_pct,
            connected=self._connected,
            adapter_name=self._adapter_name,
        )

    async def set_state(self, mode: RobotMode, behavior_state: BehaviorState) -> None:
        self._mode = mode
        self._behavior_state = behavior_state

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    async def speak(self, text: str, audio_bytes: bytes | None = None) -> None:
        logger.info("FakeRobot speaking: %r", text[:80])
        self._spoken.append(text)
        if audio_bytes is not None:
            self._played_audio.append(audio_bytes)
        await asyncio.sleep(len(text) * 0.01)  # simulate ~10 ms per char

    async def play_audio(self, audio_bytes: bytes) -> None:
        await asyncio.sleep(len(audio_bytes) / _FAKE_AUDIO_SAMPLE_RATE / 2)

    async def capture_audio(self, duration_s: float = 3.0) -> bytes:
        await asyncio.sleep(duration_s)
        # Return synthetic silence (16-bit PCM zeros)
        n_samples = int(duration_s * _FAKE_AUDIO_SAMPLE_RATE)
        return bytes(n_samples * 2)

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    async def get_camera_frame(self) -> bytes:
        """Return a synthetic grey image encoded as PNG bytes."""
        frame = np.full(_FAKE_FRAME_SHAPE, 128, dtype=np.uint8)
        from PIL import Image
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    async def execute_motion(self, command: MotionCommand) -> None:
        logger.info("FakeRobot motion: %s", command.motion_id)
        self._motions.append(command)
        await asyncio.sleep(0.05)

    async def execute_timeline(self, timeline: MotionTimeline) -> None:
        for cue in timeline.cues:
            await asyncio.sleep(cue.offset_ms / 1000.0)
            cmd = MotionCommand(
                motion_id=cue.motion_id,
                speed=cue.speed,
                amplitude=cue.amplitude,
                direction=None,
            )
            await self.execute_motion(cmd)

    # ------------------------------------------------------------------
    # Introspection helpers (not on ABC — for tests only)
    # ------------------------------------------------------------------

    @property
    def spoken_texts(self) -> list[str]:
        return list(self._spoken)

    @property
    def played_audio(self) -> list[bytes]:
        return list(self._played_audio)

    @property
    def executed_motions(self) -> list[MotionCommand]:
        return list(self._motions)

    def drain(self) -> None:
        """Reset recorded interactions."""
        self._spoken.clear()
        self._motions.clear()
