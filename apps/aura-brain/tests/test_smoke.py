"""U12: full-stack smoke through the collapsed brain (echo / mock — no network,
no real LLM key). The 🔒 SECRET part (a live LLM + real Realtime voice) is run
manually with OPENAI_API_KEY; here we drive the same path with a stubbed LLM so
the write-tool → approval-gate → connector → synthesis chain is exercised
end-to-end in-process.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("STT_PROVIDER", "null")
os.environ.setdefault("TTS_PROVIDER", "null")
os.environ.setdefault("M365_CONNECTOR", "mock")

from aura_brain.main import create_app, ctx
from orchestrator import pipeline as pipeline_mod
from shared_schemas.events.orchestrator import ApprovalRequested, ToolCallSucceeded


async def test_write_tool_passes_through_approval_gate(monkeypatch) -> None:
    """send_mail (a sensitive write tool) must hit the approval gate, and once
    granted, execute via the mock connector — all through the mounted brain."""
    # Stub the LLM: first call asks to send mail; second call (post-tool) replies.
    calls: list = []

    async def fake_llm(messages, tools=None):
        calls.append(messages)
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{
                "id": "c1", "name": "send_mail",
                "arguments": '{"to": "a@b.com", "subject": "hi", "body": "yo"}',
            }]}
        return {"content": "Sent the mail.", "tool_calls": None}

    monkeypatch.setattr(pipeline_mod, "openai_chat", fake_llm)

    app = create_app()
    async with app.router.lifespan_context(app):
        approvals: list[ApprovalRequested] = []
        succeeded: list[ToolCallSucceeded] = []

        async def auto_grant(e: ApprovalRequested) -> None:
            approvals.append(e)
            await ctx.pipeline._approval.grant(str(e.approval_id))

        async def on_success(e: ToolCallSucceeded) -> None:
            succeeded.append(e)

        ctx.bus.subscribe(ApprovalRequested, auto_grant)
        ctx.bus.subscribe(ToolCallSucceeded, on_success)

        reply = await ctx.pipeline.orchestrate("email a@b.com saying yo", "smoke")
        await asyncio.sleep(0)

        assert approvals, "approval gate did not fire for send_mail"
        assert any(e.tool_name == "send_mail" for e in succeeded), "tool did not execute after grant"
        assert reply == "Sent the mail."
