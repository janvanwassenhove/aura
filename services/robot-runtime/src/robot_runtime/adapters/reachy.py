"""ReachyRobotAdapter — the real Reachy Mini via the ``reachy-mini`` SDK (U16).

The ONLY module in the repo allowed to import Reachy SDK types (constitution).

Runs in two placements with the same code:
  - ON the Pi (production): connects to the local daemon (``localhost_only``).
  - On the laptop (bring-up/dev): ``REACHY_CONNECTION=network`` +
    ``REACHY_HOST=reachy-mini.local`` talks to the wireless robot's daemon
    directly — no code on the Pi needed.

The SDK is synchronous; every call is pushed through ``asyncio.to_thread`` and
motions are serialized behind a lock (the daemon interpolates one target at a
time). Motion vocabulary (personas + presentations) maps to head-pose/antenna
primitives:

  nod      pitch down/up            tilt     roll left/right
  wave     antenna wiggle           gesture  head sway + antennas
  point    look at a world point    bow      slow deep pitch + return
  wake_up / sleep                   SDK emotes

Media (speaker/mic/camera) goes through the SDK MediaManager — local ALSA on
the Pi, WebRTC when connecting over the network. ``REACHY_MEDIA=no_media``
disables it (motion-only bring-up); audio/camera then degrade gracefully.
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
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

_NEUTRAL = np.eye(4)


def _rot(axis: str, angle_rad: float) -> np.ndarray:
    """4x4 homogeneous rotation about x (pitch), y (roll), or z (yaw)."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4)
    if axis == "x":
        m[1:3, 1:3] = [[c, -s], [s, c]]
    elif axis == "y":
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    else:  # z
        m[0:2, 0:2] = [[c, -s], [s, c]]
    return m


class ReachyRobotAdapter(RobotAdapter):
    """RobotAdapter over the reachy-mini SDK."""

    def __init__(
        self,
        host: str | None = None,
        connection_mode: str | None = None,
        media_backend: str | None = None,
    ) -> None:
        self._host = host or os.environ.get("REACHY_HOST", "localhost")
        self._connection_mode = connection_mode or os.environ.get(
            "REACHY_CONNECTION", "auto"
        )
        self._media_backend = media_backend or os.environ.get("REACHY_MEDIA", "default")
        self._mini: Any = None  # reachy_mini.ReachyMini once connected
        self._mode = RobotMode.OFFLINE
        self._behavior_state = BehaviorState.IDLE
        self._motion_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        def _open() -> Any:
            from reachy_mini import ReachyMini  # lazy: optional dependency

            if self._media_backend != "no_media":
                self._prime_media()

            mini = ReachyMini(
                host=self._host,
                connection_mode=self._connection_mode,
                media_backend=self._media_backend,
                log_level="WARNING",
            )
            # After a daemon (re)start the motors are compliant — every motion
            # command would silently do nothing. Wake the robot so commands
            # always have a visible effect.
            try:
                mini.enable_motors()
                mini.wake_up()
            except Exception as exc:  # noqa: BLE001 — wake is best-effort
                logger.warning("wake-up on connect failed: %s", exc)
            return mini

        self._mini = await asyncio.to_thread(_open)
        self._mode = RobotMode.ONLINE
        logger.info(
            "ReachyRobotAdapter connected (host=%s mode=%s media=%s)",
            self._host, self._connection_mode, self._media_backend,
        )

    async def disconnect(self) -> None:
        if self._mini is None:
            return
        mini = self._mini
        self._mini = None
        self._mode = RobotMode.OFFLINE

        def _close() -> None:
            try:
                if not getattr(mini, "media_released", True):
                    mini.release_media()
            finally:
                client = getattr(mini, "client", None)
                if client is not None and hasattr(client, "disconnect"):
                    client.disconnect()

        await asyncio.to_thread(_close)
        logger.info("ReachyRobotAdapter disconnected")

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def get_status(self) -> RobotState:
        return RobotState(
            mode=self._mode,
            behavior_state=self._behavior_state,
            battery_pct=100.0,  # SDK exposes no battery reading yet
            connected=self._mini is not None,
            adapter_name="reachy",
        )

    async def set_state(self, mode: RobotMode, behavior_state: BehaviorState) -> None:
        self._mode = mode
        self._behavior_state = behavior_state

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    async def speak(self, text: str, audio_bytes: bytes | None = None) -> None:
        """Play synthesized speech. TTS happens brain-side; the robot plays PCM.

        Without audio bytes (or without media) this logs — text-only turns are
        rendered in the console, not on the speaker.
        """
        if audio_bytes:
            await self.play_audio(audio_bytes)
        else:
            logger.info("Reachy speak (no audio payload): %r", text[:80])

    async def play_audio(self, audio_bytes: bytes, sample_rate: int = 24_000) -> None:
        """Play PCM s16le mono. Default rate 24 kHz (OpenAI TTS output)."""
        media = self._media()
        if media is None:
            logger.warning("play_audio skipped: media backend disabled")
            return

        def _play() -> None:
            # s16le → float32 [-1, 1], resampled to the device output rate
            # (push_audio_sample wants float32; channels are adapted by the SDK).
            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            out_rate = media.get_output_audio_samplerate()
            if out_rate and out_rate > 0 and out_rate != sample_rate:
                n_out = int(len(pcm) * out_rate / sample_rate)
                x_old = np.linspace(0.0, 1.0, num=len(pcm), endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                pcm = np.interp(x_new, x_old, pcm).astype(np.float32)
            media.start_playing()
            media.push_audio_sample(pcm)

        async with self._motion_lock:  # don't fight a wake_up emote's sound
            await asyncio.to_thread(_play)

    async def capture_audio(self, duration_s: float = 3.0) -> bytes:
        media = self._media()
        if media is None:
            logger.warning("capture_audio: media disabled — returning silence")
            return bytes(int(duration_s * 16_000) * 2)

        def _record() -> bytes:
            import time

            media.start_recording()
            rate = media.get_input_audio_samplerate()
            chunks: list[np.ndarray] = []
            deadline = time.monotonic() + duration_s
            needed = int(rate * duration_s)
            got = 0
            while time.monotonic() < deadline and got < needed:
                sample = media.get_audio_sample()
                if sample is not None and len(sample):
                    arr = np.asarray(sample)
                    if arr.ndim > 1:  # downmix to mono
                        arr = arr.mean(axis=1)
                    chunks.append(arr)
                    got += len(arr)
                else:
                    time.sleep(0.01)
            media.stop_recording()
            if not chunks:
                return b""
            pcm = np.concatenate(chunks)
            if pcm.dtype != np.int16:  # float [-1,1] → int16
                pcm = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
            return pcm.tobytes()

        return await asyncio.to_thread(_record)

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    async def get_camera_frame_jpeg(self) -> bytes:
        """Raw JPEG straight from the SDK — no transcode, for the MJPEG stream."""
        media = self._media()
        if media is None:
            raise RuntimeError("camera unavailable: media backend disabled")

        def _grab_jpeg() -> bytes:
            jpeg = media.get_frame_jpeg()
            if jpeg is None:
                raise RuntimeError("no camera frame available")
            return bytes(jpeg)

        return await asyncio.to_thread(_grab_jpeg)

    async def get_camera_frame(self) -> bytes:
        media = self._media()
        if media is None:
            raise RuntimeError("camera unavailable: media backend disabled")

        def _grab() -> bytes:
            import time

            # The WebRTC/gstreamer pipeline needs a few seconds after (re)start
            # before the first frame lands — poll briefly instead of failing.
            jpeg = None
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                jpeg = media.get_frame_jpeg()
                if jpeg is not None:
                    break
                time.sleep(0.25)
            if jpeg is None:
                raise RuntimeError("no camera frame available")
            # Contract says PNG bytes; transcode.
            from PIL import Image

            img = Image.open(io.BytesIO(bytes(jpeg)))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        return await asyncio.to_thread(_grab)

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    async def execute_motion(self, command: MotionCommand) -> None:
        if self._mini is None:
            raise RuntimeError("not connected")
        async with self._motion_lock:
            await asyncio.to_thread(self._run_motion, command)

    async def execute_timeline(self, timeline: MotionTimeline) -> None:
        for cue in timeline.cues:
            await asyncio.sleep(cue.offset_ms / 1000.0)
            await self.execute_motion(
                MotionCommand(
                    motion_id=cue.motion_id,
                    speed=cue.speed,
                    amplitude=cue.amplitude,
                    direction=None,
                )
            )

    # -- motion primitives (sync; called inside to_thread + lock) --------

    def _run_motion(self, cmd: MotionCommand) -> None:
        mini = self._mini
        amp = max(0.05, min(cmd.amplitude, 1.0))
        speed = max(0.1, min(cmd.speed if cmd.speed > 0 else 1.0, 2.0))
        dur = 0.4 / speed  # base leg duration, faster speed → shorter
        motion = cmd.motion_id.lower()

        def go(head: np.ndarray | None = None, antennas: list[float] | None = None,
               duration: float = dur) -> None:
            mini.goto_target(head=head, antennas=antennas, duration=duration)

        if motion == "nod":  # pitch down, back up
            angle = 0.35 * amp
            go(head=_rot("x", angle))
            go(head=_NEUTRAL)
        elif motion == "tilt":  # roll to one side, back
            angle = 0.4 * amp * (1 if cmd.direction != "left" else -1)
            go(head=_rot("y", angle))
            go(head=_NEUTRAL)
        elif motion == "shake":  # yaw left/right/centre
            angle = 0.5 * amp
            go(head=_rot("z", angle))
            go(head=_rot("z", -angle))
            go(head=_NEUTRAL)
        elif motion == "wave":  # antennas wiggle
            a = 1.2 * amp
            go(antennas=[a, -a])
            go(antennas=[-a, a])
            go(antennas=[0.0, 0.0])
        elif motion == "gesture":  # lively sway + antennas
            angle = 0.3 * amp
            go(head=_rot("z", angle), antennas=[amp, amp])
            go(head=_rot("z", -angle), antennas=[-amp, -amp])
            go(head=_NEUTRAL, antennas=[0.0, 0.0])
        elif motion == "point":  # look at a point ahead-right
            mini.look_at_world(0.5, -0.3, 0.2, duration=dur * 2)
            go(head=_NEUTRAL, duration=dur * 2)
        elif motion == "bow":  # slow, deep pitch + hold + return
            go(head=_rot("x", 0.5 * amp), duration=dur * 3)
            go(head=_rot("x", 0.5 * amp), duration=0.4)  # hold
            go(head=_NEUTRAL, duration=dur * 3)
        elif motion == "wake_up":
            mini.wake_up()
        elif motion == "sleep":
            mini.goto_sleep()
        else:  # unknown id → gentle nod so behavior never crashes on vocabulary
            logger.warning("Unknown motion_id %r — defaulting to nod", cmd.motion_id)
            go(head=_rot("x", 0.2 * amp))
            go(head=_NEUTRAL)

    # ------------------------------------------------------------------

    def _prime_media(self) -> None:
        """Ask the daemon to power up the media pipeline BEFORE the SDK connects.

        The daemon starts its WebRTC signaling server (:8443) lazily on
        ``/api/media/acquire``; the SDK's MediaManager dials that port at init
        and dies with ConnectionRefused if we don't prime it first.
        """
        import socket
        import time
        import urllib.request

        try:
            req = urllib.request.Request(
                f"http://{self._host}:8000/api/media/acquire", method="POST"
            )
            urllib.request.urlopen(req, timeout=5.0).read()
        except OSError as exc:
            logger.warning("media acquire failed (%s) — continuing, SDK may retry", exc)
            return
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((self._host, 8443), timeout=1.0):
                    logger.info("media signaling up on :8443")
                    return
            except OSError:
                time.sleep(0.5)
        logger.warning("media signaling (:8443) not up after acquire — SDK init may fail")

    def _media(self) -> Any:
        if self._mini is None:
            raise RuntimeError("not connected")
        if self._media_backend == "no_media":
            return None
        try:
            return self._mini.media
        except Exception:  # media acquisition failed / released
            return None
