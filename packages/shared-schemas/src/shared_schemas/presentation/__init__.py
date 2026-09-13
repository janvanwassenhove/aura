"""shared_schemas.presentation sub-package."""

from shared_schemas.presentation.models import (
    Beat,
    PresentationScript,
    Scenario,
    SlideScript,
)
from shared_schemas.presentation.vocals import (
    PERSONA_ID,
    VoiceSegment,
    persona_marker_problem,
    personas_used,
    split_persona_segments,
)

__all__ = [
    "Beat",
    "PresentationScript",
    "Scenario",
    "SlideScript",
    "PERSONA_ID",
    "VoiceSegment",
    "persona_marker_problem",
    "personas_used",
    "split_persona_segments",
]
