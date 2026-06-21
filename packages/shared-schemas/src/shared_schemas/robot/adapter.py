"""RobotAdapter abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared_schemas.robot.models import MotionCommand, MotionTimeline, RobotState


class RobotAdapter(ABC):
    """Contract that every robot adapter must satisfy.

    Implementations: FakeRobotAdapter, ReachyRobotAdapter.
    No Reachy SDK types may appear outside services/robot-runtime/adapters/reachy.py.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection to the robot (or fake equivalent)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection gracefully."""

    @abstractmethod
    async def get_status(self) -> RobotState:
        """Return the current robot state snapshot."""

    @abstractmethod
    async def speak(self, text: str) -> None:
        """Play synthesised speech on the robot's speaker.

        For FakeRobot: log the text; emit SpeechPlaybackStarted.
        For Reachy: send audio to the on-board speaker.
        """

    @abstractmethod
    async def play_audio(self, audio_chunk: bytes) -> None:
        """Play a raw PCM audio chunk (16kHz, 16-bit mono)."""

    @abstractmethod
    async def capture_audio(self) -> bytes:
        """Capture one second of audio from the robot's microphone.

        Returns raw PCM bytes (16kHz, 16-bit mono, 1 second = 32000 bytes).
        FakeRobot returns silence.
        """

    @abstractmethod
    async def get_camera_frame(self) -> bytes:
        """Return the latest camera frame as PNG bytes.

        FakeRobot returns a static grey 320×240 PNG.
        """

    @abstractmethod
    async def execute_motion(self, motion_command: MotionCommand) -> None:
        """Execute a single motion command.

        Emits MotionStarted then MotionCompleted (or MotionFailed).
        """

    @abstractmethod
    async def execute_timeline(self, motion_timeline: MotionTimeline) -> None:
        """Execute a sequence of timed motion cues.

        Cues are executed in order; each cue waits offset_ms from the previous cue.
        """

    @abstractmethod
    async def set_state(self, robot_state: RobotState) -> None:
        """Update the robot's internal state model.

        Emits RobotModeChanged if the mode field changes.
        """
