"""Orchestrator pipeline — main turn processing flow."""

from __future__ import annotations

import json
import logging
import os

import httpx

from orchestrator.approval_manager import ApprovalDeniedError, ApprovalManager, ApprovalTimeout
from orchestrator.context_builder import ContextBuilder
from orchestrator.fallback_agent import FallbackAgent
from orchestrator.intent_router import IntentRouter
from orchestrator.llm import openai_chat
from orchestrator.persona_manager import PersonaManager
from orchestrator.tool_schemas import build_tool_specs
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED
from shared_schemas.events.conversation import IntentRecognized, ResponseDrafted
from shared_schemas.events.orchestrator import ToolCallFailed, ToolCallRequested, ToolCallSucceeded
from shared_schemas.robot.models import RobotMode

logger = logging.getLogger(__name__)

# Tool name → connector-service path (method, path)
_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "list_calendar_events_today": ("GET", "/calendar/today"),
    "create_calendar_event":      ("POST", "/calendar/events"),
    "delete_calendar_event":      ("DELETE", "/calendar/events/{id}"),
    "get_unread_mail":            ("GET", "/mail/unread"),
    "send_mail":                  ("POST", "/mail/send"),
    "post_teams_message":         ("POST", "/teams/message"),
    "list_tasks":                 ("GET", "/tasks"),
    "create_task":                ("POST", "/tasks"),
    "delete_task":                ("DELETE", "/tasks/{id}"),
    "list_todos":                 ("GET", "/todos"),
    "create_todo":                ("POST", "/todos"),
    "complete_todo":              ("POST", "/todos/{id}/complete"),
    "list_reminders":             ("GET", "/reminders"),
    "create_reminder":            ("POST", "/reminders"),
}


class OrchestratorPipeline:
    def __init__(
        self,
        bus: AsyncEventBus,
        intent_router: IntentRouter,
        approval_mgr: ApprovalManager,
        context_builder: ContextBuilder,
        persona_mgr: PersonaManager,
        fallback_agent: FallbackAgent | None = None,
        offline_queue=None,  # OfflineQueue | None — avoid circular import
    ) -> None:
        self._bus = bus
        self._router = intent_router
        self._approval = approval_mgr
        self._context = context_builder
        self._persona = persona_mgr
        self._fallback = fallback_agent or FallbackAgent()
        self._offline_queue = offline_queue
        self._heartbeat = None  # set later via set_heartbeat_monitor()
        self._connector_url = os.environ.get(
            "CONNECTOR_SERVICE_URL", "http://connector-service:8004"
        )

    def set_heartbeat_monitor(self, monitor) -> None:
        self._heartbeat = monitor

    async def orchestrate(self, text: str, session_id: str) -> str:
        """Process one user turn; returns the assistant reply text."""
        # Offline / DEGRADED mode: delegate to FallbackAgent
        if self._heartbeat and self._heartbeat.mode in (
            RobotMode.DEGRADED, RobotMode.OFFLINE, RobotMode.MAINTENANCE
        ):
            reply = await self._fallback.handle(text, session_id)
            await self._bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))
            return reply

        persona = self._persona.current_persona
        allowed = self._router.allowed_tools()

        # Build system prompt + context string
        ctx_str = await self._context.build_context()
        tool_list_str = await self._context.build_tool_list(allowed)
        system_prompt = self._persona.render_system_prompt(ctx_str, tool_list_str)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        # Call LLM — advertise the allowed tools so it can emit real tool_calls.
        tool_specs = build_tool_specs(allowed)
        llm_response = await openai_chat(messages, tools=tool_specs or None)
        content: str | None = llm_response["content"]
        tool_calls: list | None = llm_response["tool_calls"]

        await self._bus.publish(
            IntentRecognized(
                session_id=session_id,
                intent="tool_call" if tool_calls else "direct_response",
                tool_name=tool_calls[0]["name"] if tool_calls else None,
            )
        )

        if not tool_calls:
            reply = content or "(no response)"
            await self._bus.publish(
                ResponseDrafted(session_id=session_id, response_text=reply)
            )
            return reply

        # Handle tool calls sequentially. The OpenAI API requires that EVERY
        # advertised tool_call gets a matching `tool` message on the follow-up
        # turn — including blocked/denied ones — keyed by tool_call_id.
        assistant_tool_calls: list[dict] = []  # OpenAI-shaped, for the follow-up message
        tool_messages: list[dict] = []         # one per tool_call, with tool_call_id
        for tc in tool_calls:
            tool_name: str = tc["name"]
            tc_id: str = tc.get("id") or f"call_{tool_name}"
            raw_args = tc.get("arguments", "{}")
            args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args)
            try:
                arguments: dict = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                arguments = {}

            assistant_tool_calls.append({
                "id": tc_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": args_str},
            })

            def _record(result: str) -> None:
                tool_messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})

            # Mode check
            if not self._router.is_allowed(tool_name):
                logger.warning("Tool %r blocked by mode %r", tool_name, self._router.mode)
                await self._bus.publish(
                    ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="mode_mismatch")
                )
                _record(f"[{tool_name}: not available in current mode]")
                continue

            await self._bus.publish(
                ToolCallRequested(session_id=session_id, tool_name=tool_name)
            )

            # Approval check
            if tool_name in APPROVAL_REQUIRED:
                try:
                    await self._approval.request_approval(tool_name, arguments)
                except ApprovalTimeout:
                    logger.warning("Approval timed out for %r", tool_name)
                    await self._bus.publish(
                        ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="approval_timeout")
                    )
                    _record(f"[{tool_name}: approval timed out]")
                    continue
                except ApprovalDeniedError:
                    await self._bus.publish(
                        ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="approval_denied")
                    )
                    _record(f"[{tool_name}: denied by user]")
                    continue

            # Execute via connector-service
            result_text = await self._call_connector(tool_name, arguments)
            await self._bus.publish(
                ToolCallSucceeded(
                    session_id=session_id,
                    tool_name=tool_name,
                    result_summary=result_text[:500],
                )
            )
            _record(result_text)

        # Synthesize final response from tool results
        if tool_messages:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": assistant_tool_calls,
            })
            messages.extend(tool_messages)
            final = await openai_chat(messages)
            reply = final["content"] or "\n".join(m["content"] for m in tool_messages)
        else:
            reply = content or "(no response)"

        await self._bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))
        return reply

    async def _call_connector(self, tool_name: str, arguments: dict) -> str:
        route = _TOOL_ROUTES.get(tool_name)
        if route is None:
            return f"(no connector route for {tool_name!r})"
        method, path = route
        # Substitute path params (e.g. /calendar/events/{id}) from arguments.
        if "{" in path:
            try:
                path = path.format(**arguments)
            except KeyError as exc:
                return f"(missing path argument {exc} for {tool_name!r})"
        url = f"{self._connector_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if method == "GET":
                    resp = await client.get(url)
                else:
                    resp = await client.request(method, url, json=arguments)
            resp.raise_for_status()
            return resp.text[:500]
        except Exception as exc:
            logger.warning("Connector call failed: %s %s — %s", method, url, exc)
            return f"(connector error: {exc})"
