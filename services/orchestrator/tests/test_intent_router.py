"""Tests for IntentRouter mode filtering."""

from __future__ import annotations

import pytest
from orchestrator.intent_router import IntentRouter


def test_allowed_tools_work_mode() -> None:
    router = IntentRouter(mode="work")
    tools = router.allowed_tools()
    assert "list_calendar_events_today" in tools
    assert "send_mail" in tools


def test_allowed_tools_home_mode() -> None:
    router = IntentRouter(mode="home")
    tools = router.allowed_tools()
    assert "list_todos" in tools
    assert "send_mail" not in tools


def test_is_allowed_returns_true_for_valid_tool() -> None:
    router = IntentRouter(mode="work")
    assert router.is_allowed("get_unread_mail") is True


def test_is_allowed_returns_false_for_wrong_mode() -> None:
    router = IntentRouter(mode="home")
    assert router.is_allowed("send_mail") is False


def test_set_mode_updates_allowed_tools() -> None:
    router = IntentRouter(mode="home")
    assert not router.is_allowed("send_mail")
    router.set_mode("work")
    assert router.is_allowed("send_mail")


def test_set_mode_invalid_raises() -> None:
    router = IntentRouter(mode="work")
    with pytest.raises(ValueError, match="Unknown mode"):
        router.set_mode("unknown_mode")


async def test_route_raises_permission_error_for_blocked_tool() -> None:
    router = IntentRouter(mode="home")
    with pytest.raises(PermissionError):
        await router.route("send_mail", {})


async def test_route_raises_lookup_error_for_unregistered_handler() -> None:
    router = IntentRouter(mode="work")
    with pytest.raises(LookupError):
        await router.route("list_calendar_events_today", {})


async def test_route_calls_registered_handler() -> None:
    router = IntentRouter(mode="work")
    results: list[dict] = []

    async def handler(**kwargs: object) -> str:
        results.append(kwargs)
        return "ok"

    router.register("list_calendar_events_today", handler)
    result = await router.route("list_calendar_events_today", {"date": "today"})
    assert result == "ok"
    assert results[0] == {"date": "today"}
