"""Tests for shared-policies rules."""

from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP


def test_approval_required_is_frozenset():
    assert isinstance(APPROVAL_REQUIRED, frozenset)


def test_send_mail_requires_approval():
    assert "send_mail" in APPROVAL_REQUIRED


def test_post_teams_message_requires_approval():
    assert "post_teams_message" in APPROVAL_REQUIRED


def test_mode_tool_map_has_all_modes():
    assert "work" in MODE_TOOL_MAP
    assert "home" in MODE_TOOL_MAP
    assert "presentation" in MODE_TOOL_MAP
    assert "silent_desk" in MODE_TOOL_MAP
    assert "demo" in MODE_TOOL_MAP


def test_work_mode_includes_m365_tools():
    work_tools = MODE_TOOL_MAP["work"]
    assert "list_calendar_events_today" in work_tools
    assert "get_unread_mail" in work_tools
    assert "send_mail" in work_tools


def test_silent_desk_has_minimal_tools():
    silent_tools = MODE_TOOL_MAP["silent_desk"]
    assert "send_mail" not in silent_tools
    assert "post_teams_message" not in silent_tools
