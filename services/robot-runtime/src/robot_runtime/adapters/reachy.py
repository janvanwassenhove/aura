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
        # Speaker gain 0.0–1.0, applied to every PCM sample (U36e volume).
        self._volume = float(os.environ.get("ROBOT_VOLUME", "0.8"))
        # Whether follow-me head tracking is active. Motions pause it so they
        # play at full amplitude, then resume it (U38-fix).
        self._tracking_on = False
        self._body_follow = False  # U37: torso turns with the tracked face
        import threading

        self._audio_abort = threading.Event()  # U84: barge-in cuts speech
        # Raw (pre-normalization) peak of the last mic capture — lets the voice
        # loop tell silence from speech cheaply, without transcribing (U47).
        self._last_raw_peak = 0.0

    def last_capture_peak(self) -> float:
        return self._last_raw_peak

    def set_volume(self, level: float) -> float:
        self._volume = max(0.0, min(1.0, level))
        return self._volume

    def get_volume(self) -> float:
        return self._volume

    @staticmethod
    def _set_hardware_volume_max() -> None:
        """Force the speaker's ALSA PCM control to 0 dB (U82). Best-effort:
        overridable via SPEAKER_ALSA_CONTROL / SPEAKER_ALSA_CARD; skipped when
        SPEAKER_ALSA_MAX=false."""
        if os.environ.get("SPEAKER_ALSA_MAX", "true").lower() != "true":
            return
        import subprocess

        card = os.environ.get("SPEAKER_ALSA_CARD", "0")
        control = os.environ.get("SPEAKER_ALSA_CONTROL", "PCM")
        try:
            subprocess.run(
                ["amixer", "-c", card, "sset", control, "100%"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5,
            )
            logger.info("speaker ALSA %s set to 100%% (card %s)", control, card)
        except Exception as exc:  # noqa: BLE001 — audio is best-effort
            logger.warning("could not set speaker ALSA volume: %s", exc)

    async def set_tracking(self, enabled: bool) -> bool:
        """Follow-me: daemon-side face tracking (U36g)."""
        if self._mini is None:
            raise RuntimeError("not connected")

        def _toggle() -> None:
            if enabled:
                self._mini.start_head_tracking()
                if self._body_follow:  # re-apply torso follow with tracking
                    self._mini.set_automatic_body_yaw(True)
            else:
                self._mini.stop_head_tracking()
                self._mini.goto_target(head=_NEUTRAL, duration=1.0)

        async with self._motion_lock:
            await asyncio.to_thread(_toggle)
        self._tracking_on = enabled
        return enabled

    async def set_body_follow(self, enabled: bool) -> bool:
        """U37: turn the torso along with the face. The SDK's head tracking only
        moves the neck (mechanically limited); automatic body yaw makes the
        daemon rotate the body toward the tracked face as well."""
        if self._mini is None:
            raise RuntimeError("not connected")

        def _apply() -> None:
            self._mini.set_automatic_body_yaw(enabled)
            if not enabled:
                self._mini.set_target_body_yaw(0.0)  # settle the torso forward

        async with self._motion_lock:
            await asyncio.to_thread(_apply)
        self._body_follow = enabled
        return enabled

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
                # The wake emote can end slightly off-pose — settle upright.
                mini.goto_target(head=_NEUTRAL, antennas=[0.0, 0.0], duration=0.8)
            except Exception as exc:  # noqa: BLE001 — wake is best-effort
                logger.warning("wake-up on connect failed: %s", exc)
            # U82: the SDK/daemon resets the speaker's ALSA PCM volume to ~62%
            # (-23 dB) on init, which made TTS "enorm stil". Force the hardware
            # mixer to max on every connect so speech is audible; fine loudness
            # control stays digital via the app volume slider (self._volume).
            self._set_hardware_volume_max()
            # U36g: follow the person — the daemon tracks the nearest face and
            # keeps looking at them (looks up when you stand in front of it).
            if os.environ.get("HEAD_TRACKING", "true").lower() == "true":
                try:
                    mini.start_head_tracking()
                    self._tracking_on = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("head tracking not started: %s", exc)
                # U37: BODY_FOLLOW — the daemon also rotates the torso toward
                # the tracked face (head tracking alone only moves the neck).
                if os.environ.get("BODY_FOLLOW", "false").lower() == "true":
                    try:
                        mini.set_automatic_body_yaw(True)
                        self._body_follow = True
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("body follow not started: %s", exc)
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
            import struct
            import tempfile
            import time
            import wave

            # s16le mono → peak-normalize to 0.95 (quiet TTS uses full range),
            # then apply the app volume (U36e/U36g).
            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
            if peak > 0.01:
                pcm = pcm * (0.95 / peak)
            pcm = np.clip(pcm * self._volume, -1.0, 1.0)
            samples = (pcm * 32767.0).astype(np.int16)
            duration = len(samples) / sample_rate if sample_rate else 0.0

            # U83: play the WHOLE utterance as one WAV via GStreamer playbin
            # (media.play_sound). The push_audio_sample/appsrc path drained its
            # small buffer and stopped, chopping long replies into fragments;
            # playbin plays a complete file end-to-end on the same audio sink.
            path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False, dir="/dev/shm"
                ) as fh:
                    path = fh.name
                with wave.open(path, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(sample_rate)
                    w.writeframes(struct.pack(f"<{len(samples)}h", *samples.tolist()))
                media.play_sound(path)
                # playbin is async; block for the audio duration (+margin) so
                # nothing else grabs the sink — but wake every 100 ms so a
                # barge-in can cut the speech instantly (U84).
                deadline = time.monotonic() + duration + 0.4
                while time.monotonic() < deadline:
                    if self._audio_abort.is_set():
                        try:  # stop the playbin NOW
                            playbin = getattr(media, "_playbin", None)
                            if playbin is not None:
                                from gi.repository import Gst  # type: ignore

                                playbin.set_state(Gst.State.NULL)
                        except Exception:  # noqa: BLE001 — stop is best-effort
                            pass
                        logger.info("audio playback aborted (barge-in)")
                        break
                    time.sleep(0.1)
            finally:
                if path:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        self._audio_abort.clear()
        async with self._motion_lock:  # hold the lock so nothing cuts the speech
            await asyncio.to_thread(_play)

    def stop_audio(self) -> bool:
        """U84 barge-in: abort the current utterance immediately."""
        self._audio_abort.set()
        return True

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
            pcm = np.concatenate(chunks).astype(np.float32)
            if pcm.max() > 1.5 or pcm.min() < -1.5:  # already int-scaled
                pcm = pcm / 32768.0
            # Resample to 16 kHz mono s16le — the standard STT input rate.
            if rate and rate > 0 and rate != 16_000:
                n_out = int(len(pcm) * 16_000 / rate)
                if n_out > 0:
                    x_old = np.linspace(0.0, 1.0, num=len(pcm), endpoint=False)
                    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                    pcm = np.interp(x_new, x_old, pcm).astype(np.float32)
            # The Reachy mic array is low-sensitivity even at max hardware gain,
            # so peak-normalize each capture toward a usable level (capped, so
            # near-silence isn't blown up into noise). Whisper then hears speech.
            peak = float(np.abs(pcm).max()) if len(pcm) else 0.0
            self._last_raw_peak = peak  # raw level for the voice loop's VAD
            # Only boost when there's clearly speech-level signal, so true
            # silence stays quiet → Whisper returns empty instead of
            # hallucinating a phrase from amplified room noise (U49).
            gate = float(os.environ.get("MIC_NORMALIZE_GATE", "0.008"))
            if peak > gate:
                target = float(os.environ.get("MIC_TARGET_PEAK", "0.5"))
                max_gain = float(os.environ.get("MIC_MAX_GAIN", "40"))
                pcm = pcm * min(target / peak, max_gain)
            return (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16).tobytes()

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
            await asyncio.to_thread(self._run_motion_tracked, command)

    # Reply-time gestures (embodiment): keep looking at the person while doing
    # them so follow-me is not interrupted every time the robot speaks (U81).
    _FOLLOW_GESTURES = frozenset({"nod", "tilt", "shake", "gesture", "wave"})

    def _run_motion_tracked(self, command: MotionCommand) -> None:
        """Run a motion at FULL amplitude: pause follow-me tracking (which
        would otherwise pull the head straight back to the face and dampen the
        move), play it, then resume tracking. Sync; runs inside the lock.

        U81: with FOLLOW_WHILE_SPEAKING (default on) the small reply gestures
        DON'T pause tracking — the robot keeps its eyes on you while gesturing
        and speaking. Big emotes still manage the head themselves."""
        motion = command.motion_id.lower()
        follow_while_speaking = (
            os.environ.get("FOLLOW_WHILE_SPEAKING", "true").lower() == "true"
        )
        keep_tracking = follow_while_speaking and motion in self._FOLLOW_GESTURES
        paused = False
        # wake_up/sleep/look_around manage the head themselves; don't touch them.
        if self._tracking_on and not keep_tracking and motion not in (
            "wake_up", "sleep", "look_around", "point"
        ):
            try:
                self._mini.stop_head_tracking()
                paused = True
            except Exception:  # noqa: BLE001
                pass
        try:
            self._run_motion(command)
        finally:
            if paused:
                try:
                    self._mini.start_head_tracking()
                except Exception:  # noqa: BLE001
                    pass

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
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=0.8)  # settle upright
        elif motion == "sleep":
            mini.goto_sleep()
        elif motion == "look_around":  # idle curiosity: glance at 2 spots, settle
            import random

            for _ in range(2):
                mini.look_at_world(
                    0.6,
                    random.uniform(-0.45, 0.45),
                    random.uniform(0.0, 0.35),
                    duration=random.uniform(1.2, 1.8),
                )
            go(head=_NEUTRAL, duration=1.2)
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
