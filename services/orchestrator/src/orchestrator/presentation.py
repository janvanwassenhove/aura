"""PresentationManager — loads scripts, activates slide cues, manages presentation session."""

from __future__ import annotations

import asyncio
import logging
from typing import IO, Protocol

import yaml

from shared_events.bus import AsyncEventBus
from shared_schemas.events.system import PresentationCueReceived
from shared_schemas.presentation.models import PresentationScript, SlideScript
from shared_schemas.robot.models import MotionCommand


class RobotDriver(Protocol):
    """Minimal robot surface the presenter drives (duck-typed; the brain injects
    its RobotClient). Kept as a Protocol so orchestrator needn't import aura-brain."""

    async def speak(self, text: str) -> object: ...
    async def execute_motion(self, command: MotionCommand) -> object: ...

logger = logging.getLogger(__name__)


class PresentationError(Exception):
    """Base for presentation errors."""


class SlideOutOfRangeError(PresentationError):
    """Raised when the requested slide index does not exist in the script."""

    def __init__(self, index: int) -> None:
        self.index = index
        super().__init__(f"Slide {index} not found in script")


class PresentationManager:
    """Manages the active presentation session.

    Responsibilities:
    - Parse and validate YAML script files.
    - Track the current slide.
    - Emit ``PresentationCueReceived`` on slide activation.
    - Expose motion cue name for the behavior engine.
    - Clear the session on demand.

    SECURITY: Script content is parsed through Pydantic models; arbitrary YAML
    tags are never executed (yaml.safe_load is used throughout).
    """

    def __init__(
        self,
        bus: AsyncEventBus,
        session_id: str = "default",
        robot: "RobotDriver | None" = None,
    ) -> None:
        self._bus = bus
        self._session_id = session_id
        self._robot = robot  # when set, slides drive synchronized speech + gesture
        self._script: PresentationScript | None = None
        self._current_slide: int | None = None

    # ------------------------------------------------------------------
    # Script loading
    # ------------------------------------------------------------------

    def load_from_yaml(self, raw: str) -> PresentationScript:
        """Parse a YAML string and load the presentation.

        Returns the parsed ``PresentationScript``.
        Raises ``ValueError`` on schema validation errors.
        """
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError("YAML root must be a mapping")
        script = PresentationScript.model_validate(data)
        self._script = script
        self._current_slide = None
        logger.info(
            "Presentation loaded: %r (%d slides)",
            script.title,
            len(script.slides),
        )
        return script

    # ------------------------------------------------------------------
    # Session state
    # ------------------------------------------------------------------

    @property
    def script(self) -> PresentationScript | None:
        return self._script

    @property
    def current_slide(self) -> int | None:
        return self._current_slide

    @property
    def is_active(self) -> bool:
        return self._script is not None

    def clear_session(self) -> None:
        """End the presentation session and reset all state."""
        self._script = None
        self._current_slide = None
        logger.info("Presentation session cleared")

    # ------------------------------------------------------------------
    # Slide activation
    # ------------------------------------------------------------------

    async def activate_slide(self, index: int) -> SlideScript:
        """Activate slide *index*.

        - Emits ``PresentationCueReceived`` with the speech cue.
        - Returns the ``SlideScript`` so the caller can pass motion cue to
          the behavior engine.
        - Raises ``PresentationError`` if no session is loaded.
        - Raises ``SlideOutOfRangeError`` if index is not in the script.
        """
        if self._script is None:
            raise PresentationError("No presentation session is active")

        slide = self._script.get_slide(index)
        if slide is None:
            raise SlideOutOfRangeError(index)

        self._current_slide = index
        logger.info(
            "Slide %d activated — cue length=%d motion=%r",
            index,
            len(slide.speech_cue),
            slide.motion_cue,
        )

        await self._bus.publish(
            PresentationCueReceived(
                session_id=self._session_id,
                slide_number=index,
                cue_text=slide.speech_cue,
            )
        )

        # "Present with me": drive speech + gesture concurrently so the robot
        # gestures *while* speaking the cue (synchronized, not sequential).
        if self._robot is not None:
            tasks = [self._robot.speak(slide.speech_cue)]
            if slide.motion_cue:
                tasks.append(self._robot.execute_motion(MotionCommand(motion_id=slide.motion_cue)))
            await asyncio.gather(*tasks)

        return slide

    async def advance(self) -> SlideScript:
        """Co-pilot: activate the next slide (or the first if none active)."""
        if self._script is None:
            raise PresentationError("No presentation session is active")
        nxt = 0 if self._current_slide is None else self._current_slide + 1
        if nxt >= len(self._script.slides):
            raise SlideOutOfRangeError(nxt)
        return await self.activate_slide(nxt)

    async def previous(self) -> SlideScript:
        """Co-pilot: go back one slide."""
        if self._script is None:
            raise PresentationError("No presentation session is active")
        prev = 0 if self._current_slide is None else self._current_slide - 1
        if prev < 0:
            raise SlideOutOfRangeError(prev)
        return await self.activate_slide(prev)
