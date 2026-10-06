"""BehaviorEngine — drives BehaviorState transitions and motion timelines."""

from __future__ import annotations

import asyncio
import logging
import random

from shared_events.bus import AsyncEventBus
from shared_personas import Persona, get_persona_config
from shared_schemas.events.audio import AudioInputStarted, UserSpeechDetected
from shared_schemas.events.behavior import (
    BehaviorPlanned,
    BehaviorStateChanged,
    MotionCompleted,
    MotionFailed,
    MotionStarted,
    SpeechPlaybackCompleted,
    SpeechPlaybackStarted,
)
from shared_schemas.events.conversation import ResponseDrafted
from shared_schemas.events.robot import RobotModeChanged
from shared_schemas.robot.adapter import RobotAdapter
from shared_schemas.robot.models import (
    BehaviorState,
    MotionCommand,
    MotionTimeline,
    RobotMode,
)

from robot_runtime import sleep_state
from robot_runtime.behavior.states import TransitionBlockedError, is_valid_transition
from robot_runtime.behavior.timeline_builder import (
    create_idle_timeline,
    create_speaking_timeline,
)

logger = logging.getLogger(__name__)

# Time between idle fidget motions (seconds)
_IDLE_FIDGET_INTERVAL_S = 30.0
_IDLE_FIDGET_JITTER_S = 10.0


#: The brain's TTS: PCM s16le mono at 24 kHz (U36b).
_SPEECH_RATE = 24_000


class BehaviorEngine:
    """Manages the robot's behavior state and coordinates speech + motion.

    Subscribes to bus events (AudioInputStarted, UserSpeechDetected,
    ResponseDrafted, RobotModeChanged) to drive state transitions automatically.
    Emits BehaviorStateChanged events on every transition.
    Idle fidget task runs in the background while in IDLE state.
    """

    def __init__(
        self,
        adapter: RobotAdapter,
        bus: AsyncEventBus,
        session_id: str,
        persona: Persona = Persona.WORK,
    ) -> None:
        self._adapter = adapter
        self._bus = bus
        self._session_id = session_id
        self._persona = persona
        self._persona_cfg = get_persona_config(persona)
        self._state = BehaviorState.IDLE
        self._idle_task: asyncio.Task[None] | None = None
        self._speak_task: asyncio.Task[None] | None = None
        # U408: the gestures of a line the laptop is playing, and its end.
        self._along_over: asyncio.Event | None = None
        self._along_gestures: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._bus.subscribe(AudioInputStarted, self._on_audio_input_started)
        self._bus.subscribe(UserSpeechDetected, self._on_user_speech_detected)
        self._bus.subscribe(ResponseDrafted, self._on_response_drafted)
        self._bus.subscribe(RobotModeChanged, self._on_mode_changed)
        self._idle_task = asyncio.create_task(self._idle_fidget_loop())
        logger.info("BehaviorEngine started (persona=%s)", self._persona)

    async def stop(self) -> None:
        self._bus.unsubscribe(AudioInputStarted, self._on_audio_input_started)
        self._bus.unsubscribe(UserSpeechDetected, self._on_user_speech_detected)
        self._bus.unsubscribe(ResponseDrafted, self._on_response_drafted)
        self._bus.unsubscribe(RobotModeChanged, self._on_mode_changed)
        if self._idle_task:
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()

    # ------------------------------------------------------------------
    # Bus event handlers
    # ------------------------------------------------------------------

    async def _on_audio_input_started(self, event: AudioInputStarted) -> None:
        if self._state == BehaviorState.IDLE:
            await self.transition(BehaviorState.LISTENING)

    async def _on_user_speech_detected(self, event: UserSpeechDetected) -> None:
        if self._state == BehaviorState.LISTENING:
            await self.transition(BehaviorState.THINKING)

    async def _on_response_drafted(self, event: ResponseDrafted) -> None:
        if self._state in (BehaviorState.THINKING, BehaviorState.LISTENING):
            self._speak_task = asyncio.create_task(
                self.speak(event.response_text)
            )

    async def _on_mode_changed(self, event: RobotModeChanged) -> None:
        if event.to_mode in (RobotMode.MAINTENANCE, RobotMode.OFFLINE):
            await self.interrupt()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    async def transition(self, new_state: BehaviorState) -> None:
        if not is_valid_transition(self._state, new_state):
            raise TransitionBlockedError(self._state, new_state)
        old = self._state
        self._state = new_state
        await self._adapter.set_state(RobotMode.ONLINE, new_state)
        await self._bus.publish(
            BehaviorStateChanged(
                session_id=self._session_id,
                from_state=old,
                to_state=new_state,
            )
        )
        logger.debug("Behavior: %s → %s", old, new_state)

    async def interrupt(self) -> None:
        """Cancel any active speech/motion task and return to IDLE."""
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
            try:
                await self._speak_task
            except asyncio.CancelledError:
                pass
        self._state = BehaviorState.IDLE
        await self._adapter.set_state(RobotMode.ONLINE, BehaviorState.IDLE)
        await self._bus.publish(
            BehaviorStateChanged(
                session_id=self._session_id,
                from_state=self._state,
                to_state=BehaviorState.IDLE,
            )
        )

    @property
    def current_state(self) -> BehaviorState:
        return self._state

    # ------------------------------------------------------------------
    # Speech with synchronized gestures
    # ------------------------------------------------------------------

    async def speak(
        self,
        text: str,
        audio_bytes: bytes | None = None,
        *,
        with_gestures: bool = True,
    ) -> None:
        await self.transition(BehaviorState.SPEAKING)
        # U408: spread over the line's real length when the audio is here.
        duration_ms = (int(len(audio_bytes) / 2 / _SPEECH_RATE * 1000)
                       if audio_bytes else None)
        timeline = (
            create_speaking_timeline(text, self._persona_cfg, duration_ms)
            if with_gestures and self._persona_cfg.gesture_profile.motion_ids
            else None
        )
        motion_ids_str = ",".join(
            self._persona_cfg.gesture_profile.motion_ids[:3]
        ) if timeline else "none"
        await self._bus.publish(
            BehaviorPlanned(
                session_id=self._session_id,
                behavior_state=f"speak gestures:{motion_ids_str}",
            )
        )
        await self._bus.publish(
            SpeechPlaybackStarted(
                session_id=self._session_id,
                text_length=len(text),
            )
        )

        # U408: the gestures run beside the line and end with it. They used to
        # be gathered with it, and they queued behind his voice on the motion
        # lock — so every one of them played after the sentence, and this
        # waited for them, starting a talk's next beat late. A gesture still
        # moving when the line ends finishes; one not yet begun is dropped.
        line_over = asyncio.Event()
        gestures = (asyncio.create_task(self._run_timeline(timeline, line_over))
                    if timeline else None)

        # U359: the state comes back whatever happens to the audio.
        #
        # Found one slide into a conference talk: the first line played, and
        # every line after it came back `500 Internal Server Error`. This ran
        # transition(SPEAKING) → play → transition(IDLE) with nothing guarded,
        # so a playback that raised skipped the last step and left the engine
        # in SPEAKING — and SPEAKING → SPEAKING is not a legal transition
        # (behavior/states.py). One transient audio failure therefore turned
        # into a robot that could not speak again for the rest of the session.
        #
        # The failure still propagates: the caller must hear that the line was
        # not said (U269). What must not survive it is the state.
        try:
            await self._adapter.speak(text, audio_bytes)
        finally:
            line_over.set()
            if gestures is not None:
                await gestures
            # Completed means "no longer playing", not "played well" — the
            # console derives its speaking indicator from the pair, and a start
            # with no completion is a subtitle that never clears.
            await self._bus.publish(
                SpeechPlaybackCompleted(session_id=self._session_id)
            )
            await self.transition(BehaviorState.IDLE)

    # ------------------------------------------------------------------
    # Motion helpers
    # ------------------------------------------------------------------

    async def add_motion(self, motion_id: str) -> None:
        """Trigger a one-off motion by ID (for direct API calls)."""
        cmd = MotionCommand(motion_id=motion_id, speed=0.5, amplitude=0.5, direction=None)
        await self._bus.publish(MotionStarted(session_id=self._session_id, motion_id=motion_id))
        try:
            await self._adapter.execute_motion(cmd)
            await self._bus.publish(MotionCompleted(session_id=self._session_id, motion_id=motion_id))
        except Exception as exc:
            logger.exception("Motion %s failed", motion_id)
            await self._bus.publish(
                MotionFailed(session_id=self._session_id, motion_id=motion_id, reason=str(exc))
            )

    async def move_along(self, audio_bytes: bytes, sample_rate: int = _SPEECH_RATE) -> dict | None:
        """U408: a line the laptop plays. The adapter moves along with it
        (U407) and the persona's gestures go with it, as they do with a line he
        plays himself. None when the adapter cannot move along at all."""
        mover = getattr(self._adapter, "talk_along", None)
        if mover is None:
            return None
        result = await mover(audio_bytes, sample_rate)
        self.end_line()
        if result.get("moving") and self._persona_cfg.gesture_profile.motion_ids:
            seconds = float(result.get("seconds") or 0.0)
            timeline = create_speaking_timeline("", self._persona_cfg, int(seconds * 1000))
            if timeline.cues:
                over = asyncio.Event()
                asyncio.get_running_loop().call_later(seconds, over.set)
                self._along_over = over
                self._along_gestures = asyncio.ensure_future(self._run_timeline(timeline, over))
        return result

    def end_line(self) -> None:
        """U408: the line the laptop was playing is over — Stop, or the next
        one. Its gestures still to come are dropped."""
        if self._along_over is not None:
            self._along_over.set()
            self._along_over = None

    async def _run_timeline(self, timeline: MotionTimeline,
                            line_over: asyncio.Event | None = None) -> None:
        """Each cue at its time, counted from the start of the cue before it
        rather than from the end of its motion, so a slow gesture does not push
        the rest later. U408: with `line_over`, nothing starts once the line
        has ended."""
        loop = asyncio.get_running_loop()
        start = loop.time()
        at = 0.0
        for cue in timeline.cues:
            at += cue.offset_ms / 1000.0
            delay = start + at - loop.time()
            if line_over is None:
                if delay > 0:
                    await asyncio.sleep(delay)
            else:
                if delay > 0:
                    try:
                        await asyncio.wait_for(line_over.wait(), timeout=delay)
                    except TimeoutError:
                        pass
                if line_over.is_set():
                    return
            cmd = MotionCommand(
                motion_id=cue.motion_id,
                speed=cue.speed,
                amplitude=cue.amplitude,
                direction=None,
            )
            await self._bus.publish(
                MotionStarted(
                    session_id=self._session_id,
                    motion_id=cue.motion_id,
                )
            )
            try:
                await self._adapter.execute_motion(cmd)
                await self._bus.publish(
                    MotionCompleted(
                        session_id=self._session_id,
                        motion_id=cue.motion_id,
                    )
                )
            except Exception as exc:
                logger.exception("Motion %s failed", cue.motion_id)
                await self._bus.publish(
                    MotionFailed(
                        session_id=self._session_id,
                        motion_id=cue.motion_id,
                        reason=str(exc),
                    )
                )

    # ------------------------------------------------------------------
    # Idle fidget loop
    # ------------------------------------------------------------------

    async def _idle_fidget_loop(self) -> None:
        while True:
            jitter = random.uniform(0, _IDLE_FIDGET_JITTER_S)
            await asyncio.sleep(_IDLE_FIDGET_INTERVAL_S + jitter)
            if self._state != BehaviorState.IDLE:
                continue
            if sleep_state.is_asleep():   # U237: no fidgeting a sleeping robot
                continue
            timeline = create_idle_timeline(self._persona_cfg)
            for cue in timeline.cues:
                if self._state != BehaviorState.IDLE:
                    break
                cmd = MotionCommand(
                    motion_id=cue.motion_id,
                    speed=cue.speed,
                    amplitude=cue.amplitude,
                    direction=None,
                )
                try:
                    await self._adapter.execute_motion(cmd)
                except Exception:
                    logger.exception("Idle fidget motion failed")
