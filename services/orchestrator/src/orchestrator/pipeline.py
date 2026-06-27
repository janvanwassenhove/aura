"""Orchestrator pipeline — main turn processing flow."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import httpx

from orchestrator.approval_manager import ApprovalDeniedError, ApprovalManager, ApprovalTimeout
from orchestrator.context_builder import ContextBuilder
from orchestrator.dev_agent import DevAgentTool
from orchestrator.fallback_agent import FallbackAgent
from orchestrator.intent_router import IntentRouter
from orchestrator.llm import openai_chat
from orchestrator.persona_manager import PersonaManager
from orchestrator.tool_schemas import build_tool_specs
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED
from shared_schemas.events.conversation import IntentRecognized, ResponseDrafted
from shared_schemas.events.orchestrator import ToolCallFailed, ToolCallRequested, ToolCallSucceeded
from shared_schemas.events.system import TurnLatencyMeasured
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
        connector_client: httpx.AsyncClient | None = None,
        dev_agent: DevAgentTool | None = None,
    ) -> None:
        self._bus = bus
        self._router = intent_router
        self._approval = approval_mgr
        self._context = context_builder
        self._persona = persona_mgr
        self._fallback = fallback_agent or FallbackAgent()
        self._offline_queue = offline_queue
        self._heartbeat = None  # set later via set_heartbeat_monitor()
        # When set (aura-brain), connector calls go in-process via this client's
        # ASGI transport instead of over the network (Phase 1 seam, U8).
        self._connector_client = connector_client
        # U20: outbound dev-agent tool (None if not configured / DEV_AGENT_ENABLED not set).
        self._dev_agent = dev_agent
        # Offline tier (U21): while DEGRADED/OFFLINE, prefer a LOCAL model
        # (ollama) over the regex FallbackAgent. Unset → regex only.
        self._offline_llm = os.environ.get("OFFLINE_LLM_PROVIDER")  # e.g. "ollama"
        self._offline_llm_model = os.environ.get("OFFLINE_LLM_MODEL", "llama3.1")
        self._connector_url = os.environ.get(
            "CONNECTOR_SERVICE_URL", "http://connector-service:8004"
        )

    def set_heartbeat_monitor(self, monitor) -> None:
        self._heartbeat = monitor

    async def orchestrate(self, text: str, session_id: str) -> str:
        """Process one user turn; times it and emits TurnLatencyMeasured (U23)."""
        timing = {"llm_ms": 0.0, "tool_ms": 0.0}
        t0 = time.perf_counter()
        reply = await self._orchestrate_impl(text, session_id, timing)
        total_ms = (time.perf_counter() - t0) * 1000
        await self._bus.publish(TurnLatencyMeasured(
            session_id=session_id,
            total_ms=round(total_ms, 1),
            llm_ms=round(timing["llm_ms"], 1),
            tool_ms=round(timing["tool_ms"], 1),
        ))
        return reply

    async def _orchestrate_impl(self, text: str, session_id: str, timing: dict) -> str:
        # Offline / DEGRADED mode: try a local model, then the regex FallbackAgent.
        if self._heartbeat and self._heartbeat.mode in (
            RobotMode.DEGRADED, RobotMode.OFFLINE, RobotMode.MAINTENANCE
        ):
            reply = await self._offline_reply(text, session_id)
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
        _t = time.perf_counter()
        llm_response = await openai_chat(messages, tools=tool_specs or None)
        timing["llm_ms"] += (time.perf_counter() - _t) * 1000
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
        # Pass 1 (sequential): build the assistant message, enforce mode + the
        # interactive approval gate, and collect the tools cleared to execute.
        to_execute: list[tuple[str, str, dict]] = []  # (tc_id, tool_name, arguments)
        for tc in tool_calls:
            tool_name = tc["name"]
            tc_id = tc.get("id") or f"call_{tool_name}"
            raw_args = tc.get("arguments", "{}")
            args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args)
            try:
                arguments = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                arguments = {}

            assistant_tool_calls.append({
                "id": tc_id, "type": "function",
                "function": {"name": tool_name, "arguments": args_str},
            })

            if not self._router.is_allowed(tool_name):
                logger.warning("Tool %r blocked by mode %r", tool_name, self._router.mode)
                await self._bus.publish(
                    ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="mode_mismatch")
                )
                tool_messages.append({"role": "tool", "tool_call_id": tc_id,
                                      "content": f"[{tool_name}: not available in current mode]"})
                continue

            await self._bus.publish(ToolCallRequested(session_id=session_id, tool_name=tool_name))

            if tool_name in APPROVAL_REQUIRED:
                try:
                    await self._approval.request_approval(tool_name, arguments)
                except ApprovalTimeout:
                    logger.warning("Approval timed out for %r", tool_name)
                    await self._bus.publish(
                        ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="approval_timeout")
                    )
                    tool_messages.append({"role": "tool", "tool_call_id": tc_id,
                                          "content": f"[{tool_name}: approval timed out]"})
                    continue
                except ApprovalDeniedError:
                    await self._bus.publish(
                        ToolCallFailed(session_id=session_id, tool_name=tool_name, error_code="approval_denied")
                    )
                    tool_messages.append({"role": "tool", "tool_call_id": tc_id,
                                          "content": f"[{tool_name}: denied by user]"})
                    continue

            to_execute.append((tc_id, tool_name, arguments))

        # Pass 2 (concurrent): independent tool executions run in parallel — a
        # turn that touches calendar + mail + tasks no longer pays their sum.
        async def _run(tc_id: str, tool_name: str, arguments: dict) -> dict:
            if tool_name == "run_dev_task" and self._dev_agent is not None:
                result_text = await self._dev_agent.run(
                    task=arguments.get("task", ""),
                    session_id=session_id,
                    working_dir=arguments.get("working_dir"),
                    operation_type=arguments.get("operation_type"),
                )
            else:
                result_text = await self._call_connector(tool_name, arguments)
            await self._bus.publish(ToolCallSucceeded(
                session_id=session_id, tool_name=tool_name, result_summary=result_text[:500],
            ))
            return {"role": "tool", "tool_call_id": tc_id, "content": result_text}

        if to_execute:
            _t = time.perf_counter()
            results = await asyncio.gather(*(_run(*x) for x in to_execute))
            timing["tool_ms"] += (time.perf_counter() - _t) * 1000  # wall-clock (parallel)
            tool_messages.extend(results)

        # Synthesize final response from tool results
        if tool_messages:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": assistant_tool_calls,
            })
            messages.extend(tool_messages)
            _t = time.perf_counter()
            final = await openai_chat(messages)
            timing["llm_ms"] += (time.perf_counter() - _t) * 1000
            reply = final["content"] or "\n".join(m["content"] for m in tool_messages)
        else:
            reply = content or "(no response)"

        await self._bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))
        return reply

    async def _offline_reply(self, text: str, session_id: str) -> str:
        """Degraded/offline turn: a LOCAL model if one is configured and reachable,
        otherwise the regex FallbackAgent. Tools/connectors are skipped (offline)."""
        if self._offline_llm:
            try:
                system = self._persona.render_system_prompt(
                    "(operating offline on a local model — no live tools)", ""
                )
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ]
                resp = await openai_chat(
                    messages, provider=self._offline_llm, model=self._offline_llm_model
                )
                if resp.get("content"):
                    return resp["content"]
            except Exception as exc:
                logger.warning("Offline local LLM unavailable (%s); using regex fallback", exc)
        return await self._fallback.handle(text, session_id)

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
        # Connector routes are served under the /connector prefix.
        endpoint = f"/connector{path}"
        json_body = None if method == "GET" else arguments
        try:
            if self._connector_client is not None:
                # In-process (aura-brain): ASGI transport, no network hop.
                resp = await self._connector_client.request(method, endpoint, json=json_body)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.request(
                        method, f"{self._connector_url}{endpoint}", json=json_body
                    )
            resp.raise_for_status()
            return resp.text[:500]
        except Exception as exc:
            logger.warning("Connector call failed: %s %s — %s", method, endpoint, exc)
            return f"(connector error: {exc})"
