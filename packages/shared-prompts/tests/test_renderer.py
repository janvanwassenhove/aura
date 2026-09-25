"""U373 (audit T11): the test directory that had held only `__init__.py` since April.

`shared_prompts` renders the system prompt every persona speaks from
(`orchestrator/persona_manager.py`), the approval request the owner reads
before a tool runs, and the daily context block. It had a `tests/` directory,
a `dev` extra with pytest in it, and no test — so the gate could not even run
it (pytest exits 5 on an empty directory), and the walk in
`scripts/test_release_gate.py` had to be taught to skip it.

These are the tests the directory was made for. They assert on rendered text,
not on the template engine: what a persona is told, what an approval says, and
that nothing the owner typed gets HTML-escaped on its way into a prompt.
"""

from __future__ import annotations

from shared_prompts import (
    render_approval_request,
    render_context_summary,
    render_system_prompt,
)


def test_the_system_prompt_names_the_persona_and_carries_the_context() -> None:
    out = render_system_prompt(persona_name="Scout", context="Jan is presenting at 11:00.",
                               tool_list="- calendar.today\n- mail.unread")
    assert "You are AURA (Scout)" in out
    assert "Jan is presenting at 11:00." in out
    assert "- calendar.today" in out and "- mail.unread" in out


def test_the_guardrails_are_in_every_system_prompt() -> None:
    """These lines are the reason the template exists. A persona without them
    is a persona that may read a token back to the room."""
    out = render_system_prompt(persona_name="x", context="", tool_list="")
    assert "Never reveal bearer tokens, secrets, or internal tool call details." in out
    assert "Always request approval before executing tools listed as requiring it." in out


def test_nothing_is_html_escaped_on_its_way_into_a_prompt() -> None:
    """Prompts are not web pages. An owner-typed `<` or `&` must reach the
    model as typed, not as `&lt;` — autoescape is disabled for a reason."""
    out = render_system_prompt(persona_name="A & B", context="if a < b then say so",
                               tool_list="")
    assert "A & B" in out and "a < b" in out
    assert "&lt;" not in out and "&amp;" not in out


def test_the_approval_request_says_what_will_run_and_for_whom() -> None:
    out = render_approval_request(tool_name="send_mail", arguments='{"to": "team"}',
                                  requester="Jan")
    assert "**send_mail**" in out
    assert "on behalf of Jan" in out
    assert '{"to": "team"}' in out
    assert "YES" in out and "NO" in out, "the reply the owner is asked for must be spelled out"


def test_the_context_summary_carries_the_count_as_a_number() -> None:
    out = render_context_summary(calendar_items="11:00 standup", unread_mail_count=3,
                                 pending_tasks="none")
    assert "11:00 standup" in out
    assert "3 message(s)" in out
    assert "none" in out


def test_blank_lines_are_trimmed_so_prompts_stay_tight() -> None:
    """trim_blocks/lstrip_blocks are set; a template edit that loses them
    doubles every newline the model has to read past."""
    out = render_context_summary(calendar_items="a", unread_mail_count=0, pending_tasks="b")
    assert "\n\n\n" not in out
