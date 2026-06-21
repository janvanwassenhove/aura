"""Jinja2 prompt templates for AURA."""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, select_autoescape

_env = Environment(
    loader=PackageLoader("shared_prompts", "templates"),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_system_prompt(
    *,
    persona_name: str,
    context: str,
    tool_list: str,
) -> str:
    """Render the system prompt for a given persona."""
    template = _env.get_template("system_prompt.j2")
    return template.render(
        persona_name=persona_name,
        context=context,
        tool_list=tool_list,
    )


def render_approval_request(
    *,
    tool_name: str,
    arguments: str,
    requester: str,
) -> str:
    """Render a user-facing approval request message."""
    template = _env.get_template("approval_request.j2")
    return template.render(
        tool_name=tool_name,
        arguments=arguments,
        requester=requester,
    )


def render_context_summary(
    *,
    calendar_items: str,
    unread_mail_count: int,
    pending_tasks: str,
) -> str:
    """Render the daily context summary injected into system prompts."""
    template = _env.get_template("context_summary.j2")
    return template.render(
        calendar_items=calendar_items,
        unread_mail_count=unread_mail_count,
        pending_tasks=pending_tasks,
    )
