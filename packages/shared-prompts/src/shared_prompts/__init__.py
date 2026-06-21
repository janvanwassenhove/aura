"""shared-prompts — AURA Jinja2 prompt templates."""

__version__ = "0.1.0"

from shared_prompts.renderer import (
    render_approval_request,
    render_context_summary,
    render_system_prompt,
)

__all__ = [
    "render_system_prompt",
    "render_approval_request",
    "render_context_summary",
]
