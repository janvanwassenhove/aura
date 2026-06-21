"""shared-personas — AURA persona definitions and gesture profiles."""

__version__ = "0.1.0"

from shared_personas.configs import PERSONA_CONFIGS
from shared_personas.models import GestureProfile, Persona, PersonaConfig


def get_persona_config(persona: Persona | str) -> PersonaConfig:
    """Return the PersonaConfig for the given persona name."""
    if isinstance(persona, str):
        persona = Persona(persona)
    return PERSONA_CONFIGS[persona]


__all__ = [
    "Persona",
    "GestureProfile",
    "PersonaConfig",
    "PERSONA_CONFIGS",
    "get_persona_config",
]
