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
        self._tracking_watchdog: asyncio.Task | None = None  # U126
        self._groove_files: list[str] = []  # U138: dance-music temp WAVs
        import threading

        self._audio_abort = threading.Event()  # U84: barge-in cuts speech
        # Raw (pre-normalization) peak of the last mic capture — lets the voice
        # loop tell silence from speech cheaply, without transcribing (U47).
        self._last_raw_peak = 0.0
        # U155: appsrc streaming playback — estimated monotonic time until the
        # pushed audio finishes. Past it → the next push starts a NEW utterance
        # (start_playing re-stamps the PTS so the mixer doesn't place it in the
        # past after a silence gap).
        self._appsrc_until = 0.0
        # U156: whether the WebRTC AEC pipeline was activated on connect.
        self._aec_active = False
        # U157: conversational body language while speaking + idle re-acquire.
        self._talk_task: asyncio.Task | None = None
        self._idle_scan_task: asyncio.Task | None = None

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

    # U161: manual aiming (console joystick). Head yaw/pitch and torso yaw are
    # driven directly; ranges are conservative so the pad can never command a
    # pose the neck can't reach.
    AIM_YAW_MAX = 0.70      # rad, ±40°
    AIM_PITCH_MAX = 0.40    # rad, ±23°
    AIM_BODY_MAX = 1.20     # rad, ±69°

    async def aim(
        self,
        yaw: float = 0.0,
        pitch: float = 0.0,
        body_yaw: float | None = None,
        duration: float = 0.35,
    ) -> dict:
        """Point the head (and optionally the torso) at a normalized direction.

        ``yaw``/``pitch``/``body_yaw`` are -1..1 fractions of the safe range,
        which is what a 2-D joystick naturally produces.

        Face tracking is PAUSED on the first aim: the daemon would otherwise
        pull the head straight back to the nearest face and the pad would feel
        dead (the same fight U137 hit with quick actions). Follow-me is resumed
        explicitly via the console toggle — auto-resuming would snap the head
        away from wherever the operator just pointed it.
        """
        if self._mini is None:
            raise RuntimeError("not connected")

        def _clamp(v: float, lim: float) -> float:
            return max(-lim, min(lim, float(v) * lim))

        y = _clamp(yaw, self.AIM_YAW_MAX)
        p = _clamp(pitch, self.AIM_PITCH_MAX)
        b = None if body_yaw is None else _clamp(body_yaw, self.AIM_BODY_MAX)

        paused = False
        if self._tracking_on:
            try:
                await asyncio.to_thread(self._mini.stop_head_tracking)
                if self._body_follow:
                    await asyncio.to_thread(self._mini.set_automatic_body_yaw, False)
                self._tracking_on = False   # stops the U126 watchdog re-asserting
                paused = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not pause tracking for manual aim: %s", exc)

        pose = _rot("z", y) @ _rot("x", p)

        def _go() -> None:
            self._mini.goto_target(head=pose, duration=max(0.05, duration),
                                   body_yaw=b)

        async with self._motion_lock:
            await asyncio.to_thread(_go)
        return {"yaw": y, "pitch": p, "body_yaw": b, "tracking_paused": paused}

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

    def _force_webrtc_aec(self) -> None:
        """U156: route audio through the SDK's WebRTC echo-cancellation path.

        The SDK ships webrtcdsp + webrtcechoprobe wiring (software AEC: the
        speaker signal is the far-end reference, subtracted from the mic), but
        only builds it in the autoaudiosrc fallback branch — the presence of
        ~/.asoundrc (our robot) selects plain alsasrc/alsasink instead, and the
        measured echo residual there is ~9x louder than user speech at the mic
        (raw rms 1900 vs ~400 peak speech). Forcing the fallback branch enables
        the AEC chain; ALSA's default device is the same XMOS card, so audio
        still flows through the same hardware. Guarded by ROBOT_WEBRTC_AEC.
        """
        try:
            from reachy_mini.media import audio_gstreamer

            audio_gstreamer.has_reachymini_asoundrc = lambda: False
            audio_gstreamer.get_audio_device = lambda *_a, **_k: None
            # The fallback branch creates autoaudiosrc/autoaudiosink, but
            # autodetect picks pulse/openal here (no PulseAudio on the Pi →
            # "Connection refused" / "Could not open device", capture dead).
            # Map them to the explicit ALSA devices from ~/.asoundrc instead —
            # same XMOS card, but now routed through webrtcdsp + echoprobe.
            Gst = audio_gstreamer.Gst
            orig_make = Gst.ElementFactory.make

            def _make(factory_name, name=None):
                if factory_name == "autoaudiosrc":
                    el = orig_make("alsasrc", name)
                    if el is not None:
                        el.set_property("device", "reachymini_audio_src")
                    return el
                if factory_name == "autoaudiosink":
                    el = orig_make("alsasink", name)
                    if el is not None:
                        el.set_property("device", "reachymini_audio_sink")
                    return el
                if factory_name == "webrtcdsp":
                    el = orig_make("webrtcdsp", name)
                    if el is not None:
                        # Measured: without this the echo passes through
                        # uncancelled — webrtcdsp relies on pipeline latency
                        # accounting to align the far-end reference, and the
                        # dmix/dsnoop topology breaks it. Delay-agnostic mode
                        # estimates the delay from the signals themselves.
                        el.set_property("delay-agnostic", True)
                        el.set_property("extended-filter", True)
                        el.set_property("noise-suppression", True)
                        # AGC re-amplifies the cancelled residual back to
                        # speech level, defeating the AEC — measured: residual
                        # rms ~4400 with AGC vs the converging trend without.
                        el.set_property("gain-control", False)
                    return el
                return orig_make(factory_name, name)

            Gst.ElementFactory.make = staticmethod(_make)
            self._aec_active = True
            logger.info("WebRTC AEC forced: alsa reachymini devices + webrtcdsp/echoprobe")
        except Exception as exc:  # noqa: BLE001 — fall back to plain audio
            logger.warning("could not force WebRTC AEC path: %s", exc)

    async def connect(self) -> None:
        def _open() -> Any:
            from reachy_mini import ReachyMini  # lazy: optional dependency

            if os.environ.get("ROBOT_WEBRTC_AEC", "false").lower() == "true":
                self._force_webrtc_aec()

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
            # U157: audio-reactive head sway — the SDK analyses everything the
            # robot plays (incl. our U155 streamed reply segments) and composes
            # subtle PTS-synced head offsets ON TOP of face tracking daemon-side.
            # He keeps looking at you AND moves like he's talking.
            if os.environ.get("HEAD_WOBBLE", "true").lower() == "true":
                try:
                    # U158: the SDK default YAW sway is 7.5° at 0.6 Hz — a slow
                    # gaze wander that reads as "looking past you" while he
                    # talks. Tame yaw hard, keep the nodding (pitch) alive.
                    from reachy_mini.motion import speech_tapper as _tapper

                    _tapper.SWAY_A_YAW_DEG = float(os.environ.get("WOBBLE_YAW_DEG", "2.0"))
                    _tapper.SWAY_A_PITCH_DEG = float(os.environ.get("WOBBLE_PITCH_DEG", "4.0"))
                    _tapper.SWAY_A_ROLL_DEG = float(os.environ.get("WOBBLE_ROLL_DEG", "2.0"))
                    mini.enable_wobbling()
                except Exception as exc:  # noqa: BLE001 — cosmetic
                    logger.warning("head wobble not enabled: %s", exc)
            return mini

        self._mini = await asyncio.to_thread(_open)
        self._mode = RobotMode.ONLINE
        # U126: follow-me watchdog — head tracking silently dies (a motion pauses
        # it and a resume fails, the daemon drops the face, etc.) and then never
        # comes back until a manual toggle. Re-assert it periodically so it
        # self-heals within a few seconds. TRACKING_WATCHDOG_S=0 disables it.
        if self._tracking_watchdog is None or self._tracking_watchdog.done():
            self._tracking_watchdog = asyncio.ensure_future(self._tracking_watchdog_loop())
        # U157: idle re-acquire — the daemon only follows a face it can SEE;
        # once you leave the narrow camera view for >2 s it drops the aim and
        # the head just sits there ("follow me stopt buiten een gesprek").
        # A slow periodic look-around lets the tracker re-find you.
        if self._idle_scan_task is None or self._idle_scan_task.done():
            self._idle_scan_task = asyncio.ensure_future(self._idle_scan_loop())
        logger.info(
            "ReachyRobotAdapter connected (host=%s mode=%s media=%s)",
            self._host, self._connection_mode, self._media_backend,
        )

    async def _tracking_watchdog_loop(self) -> None:
        interval = float(os.environ.get("TRACKING_WATCHDOG_S", "5"))
        if interval <= 0:
            return
        while self._mini is not None:
            await asyncio.sleep(interval)
            # Only when follow-me SHOULD be on, and never mid-motion (the lock is
            # held during a gesture/speech — re-asserting then would fight it).
            if not self._tracking_on or self._mini is None or self._motion_lock.locked():
                continue
            try:
                await asyncio.to_thread(self._mini.start_head_tracking)
                if self._body_follow:
                    await asyncio.to_thread(self._mini.set_automatic_body_yaw, True)
            except Exception as exc:  # noqa: BLE001 — best-effort re-assert
                logger.debug("tracking watchdog re-assert failed: %s", exc)

    async def _idle_scan_loop(self) -> None:
        """U157: when follow-me is on but nobody is (or was) in view, sweep the
        head slowly every IDLE_SCAN_S so the face tracker can re-acquire. The
        daemon composes our sweep with the face aim by tracking weight: with a
        face in view the aim dominates (sweep is invisible); with no face the
        sweep drives the head. IDLE_SCAN_S=0 disables."""
        import random
        import time

        interval = float(os.environ.get("IDLE_SCAN_S", "25"))
        if interval <= 0:
            return
        while self._mini is not None:
            await asyncio.sleep(interval)
            mini = self._mini
            if mini is None:
                break
            if not self._tracking_on:            # follow-me off, or asleep
                continue
            if time.monotonic() < self._appsrc_until + 2.0:
                continue                          # talking — don't scan mid-reply
            if self._motion_lock.locked():
                continue                          # a gesture/speech is running
            try:
                async with self._motion_lock:
                    def _scan() -> None:
                        # U158: wider sweep (±~40°) WITH holds — the detector
                        # needs a few steady frames at each heading to spot a
                        # face; a continuous pan gave it nothing to lock onto.
                        # body_yaw=None: keep the torso where it is (the
                        # goto_target default of 0.0 silently recentred it).
                        for yaw in (0.7, -0.7, 0.0):
                            mini.goto_target(
                                head=_rot("z", yaw * random.uniform(0.85, 1.15)),
                                duration=1.4, body_yaw=None)
                            time.sleep(0.6)  # hold: give detection a chance

                    await asyncio.to_thread(_scan)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — scan is best-effort
                logger.debug("idle scan failed: %s", exc)

    def _ensure_talk_task(self) -> None:
        """U157: start the talking-antenna loop for the current utterance."""
        if os.environ.get("TALK_ANTENNAS", "true").lower() != "true":
            return
        if self._talk_task is None or self._talk_task.done():
            self._talk_task = asyncio.ensure_future(self._talk_gesture_loop())

    async def _talk_gesture_loop(self) -> None:
        """Subtle antenna accents while streamed speech is playing — antennas
        don't touch the head, so face tracking (and the wobbler) keep working.
        Ends by itself shortly after the playback clock runs out."""
        import random
        import time

        try:
            while self._mini is not None and time.monotonic() < self._appsrc_until + 0.5:
                await asyncio.sleep(random.uniform(1.2, 2.4))
                mini = self._mini
                if mini is None or time.monotonic() >= self._appsrc_until:
                    break
                if self._motion_lock.locked():
                    continue
                a = random.uniform(0.25, 0.55) * random.choice((1.0, -1.0))
                b = a * random.uniform(0.3, 1.0)
                async with self._motion_lock:
                    def _wiggle() -> None:
                        # U158: body_yaw=None — the default 0.0 silently spun
                        # the torso back to centre on EVERY wiggle, turning the
                        # robot away from the person he's talking to.
                        mini.goto_target(antennas=[a, b], duration=0.5, body_yaw=None)
                        mini.goto_target(antennas=[0.0, 0.0], duration=0.7, body_yaw=None)

                    await asyncio.to_thread(_wiggle)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001 — decoration only
            logger.debug("talk gesture loop failed: %s", exc)

    async def disconnect(self) -> None:
        if self._mini is None:
            return
        if self._tracking_watchdog is not None:
            self._tracking_watchdog.cancel()
            self._tracking_watchdog = None
        if self._idle_scan_task is not None:
            self._idle_scan_task.cancel()
            self._idle_scan_task = None
        if self._talk_task is not None:
            self._talk_task.cancel()
            self._talk_task = None
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
            tracking=self._tracking_on,  # U126: is follow-me actually on?
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

    async def play_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int = 24_000,
        *,
        normalize: bool = True,
        tail_margin: float = 0.4,
    ) -> None:
        """Play PCM s16le mono. Default rate 24 kHz (OpenAI TTS output).

        U153 streaming: when playing a reply as consecutive segments, pass
        ``normalize=False`` (each segment's own peak would otherwise be pushed
        to 0.95, pumping the volume between segments — Realtime PCM is already
        near full-scale) and a small ``tail_margin`` (the default 0.4 s wait
        after every segment would insert audible gaps into one continuous
        reply).
        """
        media = self._media()
        if media is None:
            logger.warning("play_audio skipped: media backend disabled")
            return

        def _play() -> None:
            import struct
            import tempfile
            import time
            import wave

            # s16le mono → (optionally) peak-normalize to 0.95 (quiet TTS uses
            # full range), then apply the app volume (U36e/U36g).
            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if normalize:
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
                deadline = time.monotonic() + duration + tail_margin
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

    async def play_stream_segment(self, audio_bytes: bytes, sample_rate: int = 24_000) -> None:
        """U155: gapless streaming playback via the SDK's appsrc pipeline.

        push_audio_sample feeds an audiomixer with a live silence branch, so
        consecutive segments play back-to-back with NO per-segment pipeline
        restart (the playbin path rebuilt a playbin per segment — the audible
        stutter). Returns as soon as the audio is buffered; the pipeline plays
        it asynchronously. When the AEC path is active (U156) this route also
        feeds the echo probe, so the mic capture has Richie's voice cancelled.
        """
        media = self._media()
        if media is None:
            logger.warning("play_stream_segment skipped: media backend disabled")
            return

        def _push() -> None:
            import time

            pcm = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            pcm = np.clip(pcm * self._volume, -1.0, 1.0)
            out_rate = media.get_output_audio_samplerate() or 16_000
            if sample_rate != out_rate and len(pcm):
                n_out = int(len(pcm) * out_rate / sample_rate)
                x_old = np.linspace(0.0, 1.0, num=len(pcm), endpoint=False)
                x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                pcm = np.interp(x_new, x_old, pcm).astype(np.float32)
            now = time.monotonic()
            if now >= self._appsrc_until:
                # Previous utterance finished (or first ever) → re-stamp the
                # PTS so the mixer schedules this at the current running time
                # instead of contiguously after audio that ended long ago.
                media.start_playing()
                self._appsrc_until = now
            media.push_audio_sample(pcm)
            self._appsrc_until = max(self._appsrc_until, now) + (
                len(pcm) / out_rate if out_rate else 0.0)

        await asyncio.to_thread(_push)
        # U157: conversational body language for the duration of the utterance.
        self._ensure_talk_task()

    def stop_audio(self) -> bool:
        """U84 barge-in: abort the current utterance immediately. Cuts both
        playback paths: the playbin whole-utterance path (abort event) and the
        U155 appsrc streaming path (clear_player flushes queued audio)."""
        self._audio_abort.set()
        media = self._media()
        if media is not None:
            try:
                media.clear_player()
            except Exception:  # noqa: BLE001 — flush is best-effort
                pass
        self._appsrc_until = 0.0
        return True

    # ------------------------------------------------------------------
    # U138: dance music — a tiny synthesized groove so the moves have a beat
    # ------------------------------------------------------------------

    # A minor pentatonic: any random walk over these notes sounds musical.
    _PENTATONIC = (220.00, 261.63, 293.66, 329.63, 392.00, 440.00)

    def _synth_groove(self, beats: int, bpm: float, rate: int = 22_050) -> np.ndarray:
        """Kick on the downbeats, hats on the offbeats, a pentatonic bass line.
        Returns float32 mono in [-1, 1]."""
        import random

        beat_s = 60.0 / bpm
        out = np.zeros(int(beats * beat_s * rate) + rate // 4, dtype=np.float32)

        def _mix(at_s: float, wave: np.ndarray) -> None:
            i = int(at_s * rate)
            end = min(len(out), i + len(wave))
            if end > i:
                out[i:end] += wave[: end - i]

        for b in range(beats):
            t0 = b * beat_s
            # Kick: 55 Hz sine with a fast exponential decay.
            n = int(0.18 * rate)
            t = np.arange(n) / rate
            _mix(t0, (np.sin(2 * np.pi * 55 * t) * np.exp(-22 * t) * 0.9).astype(np.float32))
            # Hat: filtered noise on the off-beat.
            n = int(0.06 * rate)
            t = np.arange(n) / rate
            noise = np.random.default_rng(b).standard_normal(n).astype(np.float32)
            _mix(t0 + beat_s / 2, (noise * np.exp(-60 * t) * 0.18).astype(np.float32))
            # Bass/lead: one pentatonic note per beat, plucked envelope.
            freq = random.choice(self._PENTATONIC)
            n = int(min(0.9 * beat_s, 0.45) * rate)
            t = np.arange(n) / rate
            tone = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t))
            _mix(t0, (tone * np.exp(-6 * t) * 0.22).astype(np.float32))

        peak = float(np.max(np.abs(out))) or 1.0
        return np.clip(out / peak * 0.85, -1.0, 1.0)

    def _play_groove(self, beats: int, bpm: float) -> None:
        """Start the groove WITHOUT blocking, so the dance moves run over it.
        Best-effort: no media backend or a synth hiccup just means a silent dance."""
        if os.environ.get("DANCE_SOUND", "true").lower() != "true":
            return
        media = self._media()
        if media is None:
            return
        try:
            import struct
            import tempfile
            import wave

            rate = 22_050
            audio = self._synth_groove(beats, bpm, rate) * self._volume
            samples = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir="/dev/shm") as fh:
                path = fh.name
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(struct.pack(f"<{len(samples)}h", *samples.tolist()))
            media.play_sound(path)  # playbin is async → returns immediately
            self._groove_files.append(path)
            # Keep /dev/shm tidy: drop the previous grooves once they're done.
            while len(self._groove_files) > 3:
                old = self._groove_files.pop(0)
                try:
                    os.remove(old)
                except OSError:
                    pass
        except Exception as exc:  # noqa: BLE001 — music is decoration, never fatal
            logger.debug("dance groove unavailable: %s", exc)

    async def capture_audio(self, duration_s: float = 3.0) -> bytes:
        media = self._media()
        if media is None:
            logger.warning("capture_audio: media disabled — returning silence")
            return bytes(int(duration_s * 16_000) * 2)

        # U148 (voice-brief §5.1): endpoint on trailing silence instead of
        # always recording the full window. `duration_s` becomes the MAX; the
        # capture stops ~ENDPOINT_SILENCE_S after speech ends, so a short
        # command returns fast. VOICE_ENDPOINTING=false → the old fixed window.
        # U150: energy-VAD endpointing is OFF by default. Without interim
        # transcripts it can't tell the natural pause BETWEEN the wake word and
        # the command ("hey Richie … vertel eens een mop") from the end of the
        # utterance, so it cut mid-sentence ("fertelde") and left Richie with a
        # fragment. The fixed window is reliable; proper (transcript-aware)
        # endpointing returns in Phase 2. Opt back in with VOICE_ENDPOINTING=true.
        endpointing = os.environ.get("VOICE_ENDPOINTING", "false").lower() == "true"
        min_speech_s = float(os.environ.get("ENDPOINT_MIN_SPEECH_S", "0.6"))
        silence_hang_s = float(os.environ.get("ENDPOINT_SILENCE_S", "1.5"))
        vad_gate = float(os.environ.get("ENDPOINT_VAD_GATE", "0.02"))

        def _record() -> bytes:
            import time

            media.start_recording()
            rate = media.get_input_audio_samplerate()
            chunks: list[np.ndarray] = []
            deadline = time.monotonic() + duration_s
            needed = int(rate * duration_s)
            got = 0
            heard_speech = False
            speech_samples = 0
            silent_samples = 0
            hang = int((rate or 16_000) * silence_hang_s)
            min_speech = int((rate or 16_000) * min_speech_s)
            while time.monotonic() < deadline and got < needed:
                sample = media.get_audio_sample()
                if sample is not None and len(sample):
                    arr = np.asarray(sample)
                    if arr.ndim > 1:  # downmix to mono
                        arr = arr.mean(axis=1)
                    chunks.append(arr)
                    got += len(arr)
                    if endpointing:
                        # Cheap frame VAD: is this chunk above the speech gate?
                        level = float(np.abs(arr.astype(np.float32) /
                                             (32768.0 if np.abs(arr).max() > 1.5 else 1.0)).mean())
                        if level > vad_gate:
                            heard_speech = True
                            speech_samples += len(arr)
                            silent_samples = 0
                        elif heard_speech:
                            silent_samples += len(arr)
                            # Enough real speech, then a clear pause → done.
                            if speech_samples >= min_speech and silent_samples >= hang:
                                break
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

    async def stream_audio(self, chunk_ms: int = 100, raw: bool = False):
        """U154: continuous mic stream — yields s16le mono 16 kHz PCM chunks of
        ~chunk_ms until the consumer stops iterating (conversation-session mode:
        the brain forwards these to the Realtime API, which does the endpointing
        server-side — no fixed windows, no local STT).

        Gain: a slowly-decaying running peak instead of per-capture
        normalization, so the level is smooth across chunks (per-chunk peak
        normalization would pump the noise floor between words). ``raw=True``
        skips gain entirely — needed for echo/AEC measurements (U156): the AGC
        normalizes both room noise and speaker echo to the same peak, hiding
        the true attenuation.
        """
        media = self._media()
        chunk_n16 = int(16_000 * chunk_ms / 1000)
        if media is None:
            # Dev without hardware: a finite silence stream so a session can
            # open and idle-close instead of hanging forever.
            for _ in range(50):
                await asyncio.sleep(chunk_ms / 1000)
                yield bytes(chunk_n16 * 2)
            return

        import queue as _queue
        import threading

        stop = threading.Event()
        out: _queue.Queue[bytes | None] = _queue.Queue(maxsize=100)

        def _pump() -> None:
            import time

            media.start_recording()
            rate = media.get_input_audio_samplerate() or 16_000
            chunk_n = int(rate * chunk_ms / 1000)
            buf = np.zeros(0, dtype=np.float32)
            target = float(os.environ.get("MIC_TARGET_PEAK", "0.5"))
            max_gain = float(os.environ.get("MIC_MAX_GAIN", "40"))
            # U163: the AGC must never chase the room's noise floor. Gate on
            # RMS, not peak: measured in a normal room, ambient clatter is
            # ~0.010 RMS with transient peaks up to 0.09, while speech is
            # sustained (0.05+ RMS). A peak gate lets every door-click through;
            # an RMS gate tells "someone is talking" from "something ticked".
            # Below the gate the chunk is passed through UNGAINED. Without this
            # a quiet room decayed running_peak toward ~0, the gain ran up to
            # 40x, and room tone reached the server at speech level — the
            # remote VAD then "heard" a turn every few seconds and Richie
            # answered noise ("conversatie slaat op hol").
            gate = float(os.environ.get("MIC_STREAM_GATE", "0.02"))
            running_peak = max(gate, 0.02)
            try:
                while not stop.is_set():
                    sample = media.get_audio_sample()
                    if sample is None or not len(sample):
                        time.sleep(0.01)
                        continue
                    arr = np.asarray(sample)
                    if arr.ndim > 1:
                        arr = arr.mean(axis=1)
                    arr = arr.astype(np.float32)
                    if np.abs(arr).max() > 1.5:  # int-scaled → float
                        arr = arr / 32768.0
                    buf = np.concatenate([buf, arr])
                    while len(buf) >= chunk_n:
                        chunk, buf = buf[:chunk_n], buf[chunk_n:]
                        if rate != 16_000:
                            n_out = int(len(chunk) * 16_000 / rate)
                            x_old = np.linspace(0.0, 1.0, num=len(chunk), endpoint=False)
                            x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
                            chunk = np.interp(x_new, x_old, chunk).astype(np.float32)
                        if not raw:
                            rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
                            if rms >= gate:
                                # Someone is actually talking: level it toward
                                # the target using the peak (avoids clipping).
                                peak = float(np.abs(chunk).max())
                                running_peak = max(peak, running_peak * 0.98, gate)
                                chunk = chunk * min(target / running_peak, max_gain)
                            else:
                                # Room tone / a stray click: pass it through
                                # ungained so the far-end VAD hears quiet as
                                # quiet instead of a turn.
                                running_peak = max(running_peak * 0.98, gate)
                        data = (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
                        try:
                            out.put_nowait(data)
                        except _queue.Full:  # consumer stalled → drop oldest
                            try:
                                out.get_nowait()
                                out.put_nowait(data)
                            except _queue.Empty:
                                pass
            finally:
                try:
                    media.stop_recording()
                except Exception:  # noqa: BLE001 — teardown is best-effort
                    pass
                out.put(None)

        thread = threading.Thread(target=_pump, name="mic-stream", daemon=True)
        thread.start()
        try:
            while True:
                data = await asyncio.to_thread(out.get)
                if data is None:
                    return
                yield data
        finally:
            stop.set()

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
    # U116: mood poses (U111) belong here too — they're the same class of small
    # reply gesture; leaving them out made every emotional reply pause tracking
    # (and a silently-failed resume killed follow-me until a manual toggle).
    _FOLLOW_GESTURES = frozenset({
        "nod", "tilt", "shake", "gesture", "wave",
        "mood_happy", "mood_excited", "mood_apologetic", "mood_curious", "mood_attentive",
        "listening", "thinking",  # U147: keep eyes on the speaker while listening
    })

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
        # U137: a MANUAL quick action must be fully visible — head tracking
        # would otherwise pull the head straight back mid-move (and the U126
        # watchdog re-asserts it every few seconds), which is why nod/shake/
        # wave/gesture looked like they "didn't work" from the panel.
        keep_tracking = (
            follow_while_speaking
            and motion in self._FOLLOW_GESTURES
            and not getattr(command, "manual", False)
        )
        paused = False
        # wake_up/sleep/look_around manage the head themselves; don't touch them.
        # wake_up/sleep manage tracking themselves (U102/U116) — never touch
        # those. look_around/point normally steer the head on their own, but a
        # MANUAL one still needs tracking paused to be visible (U137).
        _self_managed = ("wake_up", "sleep") if getattr(command, "manual", False) else (
            "wake_up", "sleep", "look_around", "point")
        if self._tracking_on and not keep_tracking and motion not in _self_managed:
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
                except Exception as exc:  # noqa: BLE001
                    # U116: don't die silently — this was how follow-me "randomly" stopped.
                    logger.warning("could not resume head tracking after %s: %s", motion, exc)

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
            # U158: body_yaw=None keeps the torso where it is — the SDK default
            # of 0.0 silently recentred the body on every gesture leg, turning
            # the robot away from the person it was facing. Dance routines steer
            # the torso explicitly via set_target_body_yaw, unaffected.
            mini.goto_target(head=head, antennas=antennas, duration=duration,
                             body_yaw=None)

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
            # U116: sleep hard-stops head tracking + body yaw; waking must undo
            # that, or follow-me stays dead until a manual toggle.
            try:
                mini.start_head_tracking()
                self._tracking_on = True
                if self._body_follow:
                    mini.set_automatic_body_yaw(True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not resume tracking after wake_up: %s", exc)
        elif motion == "sleep":
            # U102: use the SDK's default goto_sleep() emote. It sometimes
            # didn't "take" because head-tracking / automatic body-yaw kept
            # pulling the head back toward the face while the emote played —
            # so hard-stop both first, then call goto_sleep with one retry.
            for _fn in (mini.stop_head_tracking, lambda: mini.set_automatic_body_yaw(False)):
                try:
                    _fn()
                except Exception:  # noqa: BLE001
                    pass
            self._tracking_on = False
            for _attempt in range(2):
                try:
                    mini.goto_sleep()
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("goto_sleep() failed (attempt %d): %s", _attempt + 1, exc)
        # U137/U138: dance moves — rhythmic, repeating, and set to a groove the
        # robot synthesizes itself (DANCE_SOUND=false for a silent disco).
        elif motion == "bop":  # head bobbing to a beat, antennas keeping time
            bpm = 120.0 * speed
            beat = 60.0 / bpm
            self._play_groove(beats=6, bpm=bpm)
            for i in range(6):
                a = 0.9 * amp if i % 2 == 0 else -0.9 * amp
                go(head=_rot("x", 0.28 * amp), antennas=[a, a], duration=beat / 2)
                go(head=_NEUTRAL, antennas=[-a, -a], duration=beat / 2)
        elif motion == "sway":  # slow side-to-side roll, body following
            bpm = 84.0 * speed
            beat = 60.0 / bpm
            self._play_groove(beats=7, bpm=bpm)
            for _ in range(3):
                go(head=_rot("y", 0.35 * amp), antennas=[0.6 * amp, -0.6 * amp], duration=beat)
                go(head=_rot("y", -0.35 * amp), antennas=[-0.6 * amp, 0.6 * amp], duration=beat)
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=beat)
        elif motion == "spin":  # body twirl — the daemon turns the torso
            import time

            self._play_groove(beats=4, bpm=110.0 * speed)
            try:
                mini.set_automatic_body_yaw(False)
                for target in (1.2 * amp, -1.2 * amp, 0.0):
                    mini.set_target_body_yaw(target)
                    time.sleep(0.55 / speed)
            except Exception as exc:  # noqa: BLE001 — body yaw is optional
                logger.warning("spin unavailable (%s) — swaying instead", exc)
                go(head=_rot("z", 0.5 * amp)); go(head=_rot("z", -0.5 * amp)); go(head=_NEUTRAL)
            finally:
                if self._body_follow:
                    try:
                        mini.set_automatic_body_yaw(True)
                    except Exception:  # noqa: BLE001
                        pass
        elif motion == "dance":
            # U139: the whole body goes in — head, antennas AND torso. The
            # daemon eases the body toward each yaw target, so setting one
            # between head legs makes the torso swing THROUGH the moves rather
            # than after them.
            bpm = 120.0 * speed
            half = 30.0 / bpm            # eighth notes — two moves per beat
            twist = 1.0 * amp            # torso swing, radians
            self._play_groove(beats=12, bpm=bpm)

            def _yaw(target: float) -> None:
                try:
                    mini.set_target_body_yaw(target)
                except Exception:  # noqa: BLE001 — no body yaw → head-only dance
                    pass

            try:
                try:
                    mini.set_automatic_body_yaw(False)  # don't fight the routine
                except Exception:  # noqa: BLE001
                    pass

                # 1) Warm-up: bob with the torso rocking side to side.
                for i in range(4):
                    a = amp if i % 2 == 0 else -amp
                    _yaw(twist * 0.5 if i % 2 == 0 else -twist * 0.5)
                    go(head=_rot("x", 0.3 * amp), antennas=[a, -a], duration=half)
                    go(head=_rot("y", 0.32 * amp * (1 if i % 2 else -1)),
                       antennas=[-a, a], duration=half)

                # 2) Big swings: torso and head lean into the same side.
                for i in range(3):
                    side = 1 if i % 2 == 0 else -1
                    _yaw(twist * side)
                    go(head=_rot("z", 0.5 * amp * side), antennas=[amp, amp], duration=half)
                    go(head=_rot("y", 0.3 * amp * side), antennas=[-amp, -amp], duration=half)

                # 3) Finale: a full twirl, then land square with a flourish.
                for target in (twist, -twist, 0.0):
                    _yaw(target)
                    go(head=_rot("z", 0.45 * amp * (1 if target > 0 else -1)),
                       antennas=[amp, -amp], duration=half)
                go(head=_rot("x", 0.25 * amp), antennas=[amp, amp], duration=half)
                go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=half * 1.5)
            finally:
                _yaw(0.0)  # always land facing forward
                if self._body_follow:
                    try:
                        mini.set_automatic_body_yaw(True)
                    except Exception:  # noqa: BLE001
                        pass
        elif motion == "listening":
            # U147: attentive-listening cue — a small lean toward the speaker
            # with antennas perked forward, held briefly. Deliberately gentle:
            # a big move would add motor noise to the mic mid-capture (brief §5.3).
            perk = 0.5 * amp
            go(head=_rot("x", 0.12 * amp), antennas=[perk, perk], duration=0.35)
        elif motion == "thinking":
            # U147: a slow "let me think" head roll while a reply is generated,
            # so the delay reads as considered, not frozen.
            go(head=_rot("y", 0.18 * amp), antennas=[0.3 * amp, 0.5 * amp], duration=0.5)
            go(head=_rot("y", -0.12 * amp), antennas=[0.5 * amp, 0.3 * amp], duration=0.5)
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
        # U111: emotion & mimicry — small mood poses played WHILE speaking.
        # Antenna/head signs are gentle and return to neutral; tune on hardware
        # via the MOOD_* envs if a pose reads wrong. _rot("x", +) pitches down.
        elif motion == "mood_happy":  # chin up, antennas perked forward
            a = float(os.environ.get("MOOD_HAPPY_ANTENNA", "-0.5")) * amp
            go(head=_rot("x", -0.15 * amp), antennas=[a, a], duration=0.6)
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=0.7)
        elif motion == "mood_excited":  # antennas wiggle, lively
            a = float(os.environ.get("MOOD_EXCITED_ANTENNA", "0.9")) * amp
            go(head=_rot("x", -0.12 * amp), antennas=[a, -a], duration=0.35)
            go(antennas=[-a, a], duration=0.35)
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=0.5)
        elif motion == "mood_apologetic":  # head bowed, antennas droop back
            a = float(os.environ.get("MOOD_SAD_ANTENNA", "1.0")) * amp
            go(head=_rot("x", 0.3 * amp), antennas=[a, a], duration=1.0)
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=1.0)
        elif motion == "mood_curious":  # head tilt + asymmetric antennas
            roll = 0.35 * amp * (1 if cmd.direction != "left" else -1)
            a = float(os.environ.get("MOOD_CURIOUS_ANTENNA", "0.4")) * amp
            go(head=_rot("y", roll), antennas=[-a, a], duration=0.7)
            go(head=_NEUTRAL, antennas=[0.0, 0.0], duration=0.7)
        elif motion == "mood_attentive":  # a subtle lean-in, antennas still
            go(head=_rot("x", -0.1 * amp), duration=0.5)
            go(head=_NEUTRAL, duration=0.6)
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
