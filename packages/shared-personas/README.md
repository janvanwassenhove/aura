# shared-personas

## Purpose

Defines the 5 AURA personas and their associated system prompt templates.

- `Persona` enum: `work`, `home`, `presentation`, `silent_desk`, `demo`
- `PersonaConfig` — Pydantic model: name, system_prompt_template, gesture_profile, voice_style
- `get_persona_config(persona)` — returns the config for a given persona

## Personas

| Persona | Style | Voice | Gestures |
|---------|-------|-------|----------|
| `work` | Concise, formal | Professional, measured | Minimal (≤50% amplitude) |
| `home` | Warm, conversational | Relaxed, friendly | Natural |
| `presentation` | Clear, projected | Confident, paced | Expressive, audience-facing |
| `silent_desk` | Text-only | Silent | None |
| `demo` | Expressive, enthusiastic | Energetic | Full (100% amplitude) |

## Usage

```python
from shared_personas import get_persona_config, Persona

config = get_persona_config(Persona.WORK)
print(config.system_prompt_template)
print(config.gesture_profile)  # GestureProfile with amplitude settings
```

## System Prompt Templates

Templates are Jinja2 strings with `{context}` and `{tool_list}` placeholders. The orchestrator's `ContextBuilder` populates these at runtime.

## Tests

```bash
uv run pytest tests/
```
