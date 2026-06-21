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

from robot_runtime.behavior.states import TransitionBlockedError, is_valid_transition
from robot_runtime.behavior.timeline_builder import (
    create_idle_timeline,
    create_speaking_timeline,
)

logger = logging.getLogger(__name__)

# Time between idle fidget motions (seconds)
_IDLE_FIDGET_INTERVAL_S = 30.0
_IDLE_FIDGET_JITTER_S = 10.0


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
        timeline = (
            create_speaking_timeline(text, self._persona_cfg)
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

        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(self._adapter.speak(text, audio_bytes))
        ]
        if timeline:
            tasks.append(asyncio.create_task(self._run_timeline(timeline)))

        await asyncio.gather(*tasks)

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

    async def _run_timeline(self, timeline: MotionTimeline) -> None:
        for cue in timeline.cues:
            await asyncio.sleep(cue.offset_ms / 1000.0)
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
