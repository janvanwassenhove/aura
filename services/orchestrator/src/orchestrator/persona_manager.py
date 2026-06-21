"""PersonaManager — switches active persona and rebuilds context."""

from __future__ import annotations

import logging

from shared_personas import PERSONA_CONFIGS, Persona, PersonaConfig, get_persona_config
from shared_prompts import render_system_prompt

logger = logging.getLogger(__name__)


class PersonaManager:
    def __init__(self, initial_persona: Persona = Persona.WORK) -> None:
        self._persona = initial_persona

    @property
    def current_persona(self) -> Persona:
        return self._persona

    @property
    def config(self) -> PersonaConfig:
        return get_persona_config(self._persona)

    def switch(self, persona: Persona | str) -> PersonaConfig:
        if isinstance(persona, str):
            persona = Persona(persona)
        old = self._persona
        self._persona = persona
        logger.info("Persona: %s → %s", old, persona)
        return self.config

    def render_system_prompt(self, context: str, tool_list: str) -> str:
        cfg = self.config
        return render_system_prompt(
            persona_name=cfg.name,
            context=context,
            tool_list=tool_list,
        )
