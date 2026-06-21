# shared-prompts

## Purpose

Stores reusable LLM prompt templates used by the orchestrator and conversation runtime.

- `SYSTEM_PROMPT_BASE` — base instructions for all personas
- `TOOL_CALL_RESULT_TEMPLATE` — wraps tool results for the LLM
- `MEMORY_DIGEST_TEMPLATE` — formats todos and reminders for context injection
- `FALLBACK_OFFLINE_TEMPLATE` — response template when LLM is unavailable

## Usage

```python
from shared_prompts import render_system_prompt, render_memory_digest

system = render_system_prompt(
    persona_instructions=config.system_prompt_template,
    tool_list=tool_schemas,
    memory_digest=digest
)

digest = render_memory_digest(todos=todos, reminders=reminders)
```

## Template Rendering

Templates are Jinja2 strings. `render_*` functions accept keyword arguments and return rendered strings.

No templates in this package contain user-specific data. All user data is injected at runtime by the orchestrator.

## Tests

```bash
uv run pytest tests/
```
