"""Tests for StepUpGate (U19c — ADR-008 §9 step-up approval)."""

from __future__ import annotations

import asyncio

import pytest
from aura_brain.stepup_gate import StepUpDeniedError, StepUpGate, StepUpTimeout

# ---------------------------------------------------------------------------
# No-webhook tests (safe defaults)
# ---------------------------------------------------------------------------

async def test_denied_when_no_webhook_url() -> None:
    gate = StepUpGate(webhook_url=None)
    with pytest.raises(StepUpDeniedError, match="not configured"):
        await gate.request("delete_person", {"person_id": "jan"})


async def test_resolve_unknown_token_returns_false() -> None:
    gate = StepUpGate(webhook_url="http://example.com/hook")
    assert gate.resolve("nonexistent-token", granted=True) is False


async def test_resolve_already_done_returns_false() -> None:
    gate = StepUpGate(webhook_url="http://example.com/hook")
    token = "tok-123"
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    gate._pending[token] = future
    future.set_result(True)  # already resolved
    assert gate.resolve(token, granted=True) is False


# ---------------------------------------------------------------------------
# Resolve via future (no real HTTP — inject the future directly)
# ---------------------------------------------------------------------------

async def test_grant_resolves_to_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a phone grant callback arriving before the timeout."""

    async def _fake_post(self, url, *, json=None):  # noqa: ARG001
        class _Resp:
            def raise_for_status(self) -> None:
                pass
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    gate = StepUpGate(webhook_url="http://fake-webhook.local/hook", timeout=5.0)

    async def _grant_after() -> None:
        await asyncio.sleep(0.05)
        token = next(iter(gate._pending))
        gate.resolve(token, granted=True)

    task = asyncio.create_task(_grant_after())
    result = await gate.request("delete_person", {"person_id": "jan"})
    await task
    assert result is True


async def test_deny_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_post(self, url, *, json=None):  # noqa: ARG001
        class _Resp:
            def raise_for_status(self) -> None:
                pass
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    gate = StepUpGate(webhook_url="http://fake-webhook.local/hook", timeout=5.0)

    async def _deny_after() -> None:
        await asyncio.sleep(0.05)
        token = next(iter(gate._pending))
        gate.resolve(token, granted=False)

    task = asyncio.create_task(_deny_after())
    with pytest.raises(StepUpDeniedError):
        await gate.request("delete_person", {"person_id": "jan"})
    await task


async def test_timeout_raises_stepup_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_post(self, url, *, json=None):  # noqa: ARG001
        class _Resp:
            def raise_for_status(self) -> None:
                pass
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    gate = StepUpGate(webhook_url="http://fake-webhook.local/hook", timeout=0.05)
    with pytest.raises(StepUpTimeout):
        await gate.request("delete_person", {"person_id": "jan"})


# ---------------------------------------------------------------------------
# Knowledge API integration — tier gating
# ---------------------------------------------------------------------------

def test_knowledge_lock_drops_to_benign() -> None:
    """POST /knowledge/lock should drop the tier; ops still work in dev mode."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("STT_PROVIDER", "null")
    os.environ.setdefault("TTS_PROVIDER", "null")

    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        # Without KNOWLEDGE_PASSPHRASE (dev mode), lock still works.
        resp = client.post("/knowledge/lock")
        assert resp.status_code == 200
        assert resp.json()["locked"] is True

        # In dev mode (omk_loaded=False) all endpoints remain accessible after lock.
        resp = client.put("/knowledge/people/alice", json={"display_name": "Alice", "role": "owner"})
        assert resp.status_code == 200


def test_stepup_callbacks_resolve_pending() -> None:
    """Grant/deny callbacks return 200 for valid tokens, 404 for unknowns."""
    import os

    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("STT_PROVIDER", "null")
    os.environ.setdefault("TTS_PROVIDER", "null")

    from aura_brain import knowledge_api
    from aura_brain.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()
    with TestClient(app) as client:
        # Inject a fake pending future directly.
        import asyncio

        loop = asyncio.new_event_loop()
        future: asyncio.Future[bool] = loop.create_future()
        knowledge_api._stepup_gate._pending["test-token-abc"] = future  # type: ignore[union-attr]

        resp = client.post("/knowledge/stepup/callback/test-token-abc/grant")
        assert resp.status_code == 200
        assert resp.json()["granted"] is True

        # Unknown token → 404.
        resp = client.post("/knowledge/stepup/callback/bad-token/deny")
        assert resp.status_code == 404
