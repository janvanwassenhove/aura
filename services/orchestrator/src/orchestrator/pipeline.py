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
from orchestrator.llm import local_chat, openai_chat
from orchestrator.persona_manager import PersonaManager
from orchestrator import laptop_tools
from orchestrator.tool_schemas import LADDER_NOTE, build_tool_specs
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED
from shared_schemas.events.conversation import IntentRecognized, ResponseDrafted
from shared_schemas.events.orchestrator import (
    AgentRoundCompleted,
    AgentRoundStarted,
    ToolCallFailed,
    ToolCallRequested,
    ToolCallSucceeded,
)
from shared_schemas.events.system import TurnLatencyMeasured
from shared_schemas.robot.models import RobotMode

logger = logging.getLogger(__name__)

# Tool name → connector-service path (method, path)
_LANGUAGE_NAMES = {"en": "English", "nl": "Dutch", "fr": "French"}


def _identity_prefix() -> str:
    """Assistant name + reply language, read per turn so the Settings panel
    changes take effect immediately (U36h)."""
    name = os.environ.get("ASSISTANT_NAME", "AURA")
    lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").lower()
    if lang in _LANGUAGE_NAMES:
        lang_line = f"Always reply in {_LANGUAGE_NAMES[lang]}."
    else:
        lang_line = "Always reply in the language the user is using."
    return (
        f"Your name is {name}, a warm, curious desk-robot companion. You respond "
        f"when addressed as {name}. Hold a natural, flowing conversation on ANY "
        f"topic — chat, banter, opinions, and open questions are welcome, not just "
        f"tasks. Keep replies concise and spoken-friendly (1-3 sentences unless "
        f"asked for detail); no markdown or lists when simply chatting. Use the "
        f"conversation so far to stay coherent and personal. {lang_line}\n\n"
    )


# Windows virtual-key codes for the media / volume keys. These control the
# app that currently owns media playback (Spotify, browser, …) — exactly like
# pressing the keys on a keyboard.
_MEDIA_KEYS = {
    "play_pause": 0xB3,
    "play": 0xB3,
    "pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "prev": 0xB1,
    "stop": 0xB2,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}


def _send_media_key(vk: int) -> None:
    """Press+release a virtual key in the current Windows session (ctypes)."""
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    _KEYUP = 0x0002
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, _KEYUP, 0)


async def _media_control(action: str) -> str:
    """Control the laptop's media playback (real desktop apps like Spotify)."""
    key = (action or "").strip().lower()
    vk = _MEDIA_KEYS.get(key)
    if vk is None:
        return (f"[media_control: unknown action {action!r}. Use one of: "
                f"{', '.join(sorted(_MEDIA_KEYS))}.]")
    if os.name != "nt":
        return "[media_control: media keys are only supported on Windows here.]"
    try:
        await asyncio.to_thread(_send_media_key, vk)
        return f"Sent {key.replace('_', ' ')} to the desktop media player."
    except Exception as exc:  # noqa: BLE001
        return f"[media_control: error — {exc}]"


def _allowed_apps() -> dict[str, str]:
    """Parse ALLOWED_APPS='name=command;name2=command2' into a dict.

    Only apps the owner registered here can ever be launched — AURA can never
    run an arbitrary executable as an "app".
    """
    apps: dict[str, str] = {}
    for pair in os.environ.get("ALLOWED_APPS", "").split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, cmd = pair.split("=", 1)
            apps[name.strip().lower()] = cmd.strip()
    return apps


async def _launch_app(name: str) -> str:
    """Launch a pre-registered desktop app (U40). Approval-gated upstream."""
    if os.environ.get("APP_LAUNCH_ENABLED", "true").lower() != "true":
        return "[launch_app: app launching is disabled in Capabilities]"
    key = (name or "").strip().lower()
    if not key:
        return "[launch_app: name is required]"
    apps = _allowed_apps()
    cmd = apps.get(key)
    if cmd is None:
        available = ", ".join(sorted(apps)) or "(none registered)"
        return (f"[launch_app: {name!r} is not in your allow-list. "
                f"Registered apps: {available}. Add it in Capabilities.]")
    import shlex

    argv = shlex.split(cmd, posix=(os.name != "nt"))
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Don't wait for GUI apps to exit; just confirm it started.
        await asyncio.sleep(0.3)
        if proc.returncode not in (None, 0):
            return f"[launch_app: {name} exited with code {proc.returncode}]"
        return f"Launched {name}."
    except FileNotFoundError:
        return f"[launch_app: command for {name!r} not found — check its path in Capabilities]"
    except Exception as exc:  # noqa: BLE001
        return f"[launch_app: error — {exc}]"


async def _open_in_vscode(path: str, line: int | None = None) -> str:
    """Open a file/folder in VS Code on the owner's machine (U35 slice).

    Read-class desktop integration: shows code, changes nothing. Arguments go
    as an argv list — no shell interpolation.
    """
    if not path:
        return "[open_in_vscode: path is required]"
    import shutil

    code_bin = shutil.which("code")  # resolves code.cmd on Windows
    if code_bin is None:
        return "[open_in_vscode: 'code' CLI not found — install VS Code and enable the shell command]"
    target = f"{path}:{line}" if line else path
    argv = [code_bin, "-g", target] if line else [code_bin, target]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
        return f"Opened {target} in VS Code."
    except FileNotFoundError:
        return "[open_in_vscode: 'code' CLI not found — install VS Code and enable the shell command]"
    except Exception as exc:  # noqa: BLE001
        return f"[open_in_vscode: error — {exc}]"


_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "list_calendar_events_today": ("GET", "/calendar/today"),
    "create_calendar_event":      ("POST", "/calendar/events"),
    "delete_calendar_event":      ("DELETE", "/calendar/events/{id}"),
    "get_unread_mail":            ("GET", "/mail/unread"),
    "send_mail":                  ("POST", "/mail/send"),
    "list_onedrive_files":        ("GET", "/onedrive/files"),
    "play_music":                 ("POST", "/music/play"),
    "pause_music":                ("POST", "/music/pause"),
    "next_track":                 ("POST", "/music/next"),
    "list_music_playlists":       ("GET", "/music/playlists"),
    "list_speakers":              ("GET", "/music/devices"),
    "post_teams_message":         ("POST", "/teams/message"),
    "list_tasks":                 ("GET", "/tasks"),
    "create_task":                ("POST", "/tasks"),
    "delete_task":                ("DELETE", "/tasks/{id}"),
    "list_todos":                 ("GET", "/todos"),
    "create_todo":                ("POST", "/todos"),
    "complete_todo":              ("POST", "/todos/{id}/complete"),
    "list_reminders":             ("GET", "/reminders"),
    "create_reminder":            ("POST", "/reminders"),
    "list_browser_tabs":          ("GET", "/browser/tabs"),
    "open_browser_url":           ("POST", "/browser/open"),
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
        computer_use=None,  # ComputerUseAgent | None — gated, default off (U50)
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
        # U50: gated Computer Use agent (None unless COMPUTER_USE_ENABLED + key).
        self._computer_use = computer_use
        # U19e: judgment/anticipation layer + active-person tracking.
        self._judgment = None  # JudgmentLayer | None — set via set_judgment_layer()
        self._active_person_id: str | None = None
        # Offline tier (U21): while DEGRADED/OFFLINE, prefer a LOCAL model over
        # the regex FallbackAgent. Points at any OpenAI-compatible local server
        # (ollama/llama.cpp `/v1`). Unset → regex only.
        self._offline_llm_base = os.environ.get("OFFLINE_LLM_BASE_URL")
        self._offline_llm_model = os.environ.get("OFFLINE_LLM_MODEL", "llama3.1")
        self._connector_url = os.environ.get(
            "CONNECTOR_SERVICE_URL", "http://connector-service:8004"
        )
        # U42: per-session conversation memory so the robot can hold a real
        # dialogue (previously each turn was stateless). Rolling window of the
        # last MAX_CONTEXT_TURNS exchanges; user+assistant text only.
        self._history: dict[str, list[dict]] = {}
        self._max_history = int(os.environ.get("MAX_CONTEXT_TURNS", "10")) * 2
        # U57: agentic loop — owner steering (injected next round) + stop flags.
        self._steering: dict[str, list[str]] = {}
        self._stop_flags: set[str] = set()
        # U59: owner-taught skills, injected into the system prompt when relevant.
        self._skills = None  # SkillStore | None — set via set_skill_store()

    def set_skill_store(self, store) -> None:
        self._skills = store

    # -- U57: owner steering of a running loop --------------------------

    def steer(self, session_id: str, text: str) -> None:
        """Queue owner guidance; it's injected at the start of the next round."""
        self._steering.setdefault(session_id, []).append(text)

    def request_stop(self, session_id: str) -> None:
        """Ask the loop to wrap up after the current round."""
        self._stop_flags.add(session_id)

    def _drain_steering(self, session_id: str) -> list[str]:
        return self._steering.pop(session_id, [])

    @property
    def persona_config(self):
        """Active persona's config (U51: embodiment reads the gesture profile)."""
        return self._persona.config

    def _recall(self, session_id: str) -> list[dict]:
        return self._history.get(session_id, [])

    def _remember(self, session_id: str, role: str, content: str) -> None:
        if not content:
            return
        hist = self._history.setdefault(session_id, [])
        hist.append({"role": role, "content": content})
        if len(hist) > self._max_history:
            del hist[: len(hist) - self._max_history]

    def set_heartbeat_monitor(self, monitor) -> None:
        self._heartbeat = monitor

    def set_judgment_layer(self, judgment) -> None:
        """Inject the U19e JudgmentLayer. Called from aura_brain.main at startup."""
        self._judgment = judgment

    def set_active_person(self, person_id: str | None) -> None:
        """Update the currently-recognized person (called on PersonRecognized events)."""
        self._active_person_id = person_id

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

        # U19e: prepend a minimal personal-context note when a person is active.
        if self._judgment is not None and self._active_person_id:
            person_ctx = await self._judgment.build_context(self._active_person_id)
            if person_ctx is not None:
                ctx_str = person_ctx.to_system_note() + "\n\n" + ctx_str

        tool_list_str = await self._context.build_tool_list(allowed)
        system_prompt = self._persona.render_system_prompt(ctx_str, tool_list_str)
        system_prompt = _identity_prefix() + system_prompt
        if allowed:  # U58: the automation ladder governs every tool choice
            system_prompt += "\n\n" + LADDER_NOTE

        # U59: owner-taught skills (relevant ones in full, the rest by name).
        if self._skills is not None:
            try:
                block = self._skills.prompt_block(
                    text, str(persona), self._active_person_id,
                )
                if block:
                    system_prompt += "\n\n" + block
            except Exception as exc:  # noqa: BLE001 — skills must never break a turn
                logger.debug("skill injection failed: %s", exc)

        # U42: include recent turns so the robot holds a coherent dialogue.
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            *self._recall(session_id),
            {"role": "user", "content": text},
        ]
        self._remember(session_id, "user", text)

        # U57: AGENTIC LOOP — reason → tools → observe results → next round,
        # until the model gives a final answer (no more tool calls), the round
        # budget runs out, or the owner asks to stop. A simple question
        # converges in round 1, identical to the old single-shot behavior.
        # The approval gate fires per tool call, every round — never bypassed.
        tool_specs = build_tool_specs(allowed)
        max_rounds = max(1, int(os.environ.get("AGENT_MAX_ROUNDS", "8")))
        self._stop_flags.discard(session_id)
        reply: str | None = None

        for round_no in range(1, max_rounds + 1):
            # Owner steering: guidance sent while the loop runs lands here.
            for note in self._drain_steering(session_id):
                messages.append({"role": "system",
                                 "content": f"[Owner guidance — follow this now] {note}"})

            await self._bus.publish(AgentRoundStarted(
                session_id=session_id, round_no=round_no, max_rounds=max_rounds))

            _t = time.perf_counter()
            llm_response = await openai_chat(messages, tools=tool_specs or None)
            timing["llm_ms"] += (time.perf_counter() - _t) * 1000
            content: str | None = llm_response["content"]
            tool_calls: list | None = llm_response["tool_calls"]

            if round_no == 1:
                await self._bus.publish(IntentRecognized(
                    session_id=session_id,
                    intent="tool_call" if tool_calls else "direct_response",
                    tool_name=tool_calls[0]["name"] if tool_calls else None,
                ))

            if not tool_calls:
                reply = content or "(no response)"
                await self._bus.publish(AgentRoundCompleted(
                    session_id=session_id, round_no=round_no, tool_names=[], done=True))
                break

            assistant_tool_calls, tool_messages, executed = await self._run_tool_round(
                tool_calls, session_id, timing)
            messages.append({"role": "assistant", "content": content or None,
                             "tool_calls": assistant_tool_calls})
            messages.extend(tool_messages)
            await self._bus.publish(AgentRoundCompleted(
                session_id=session_id, round_no=round_no, tool_names=executed, done=False))

            if session_id in self._stop_flags:
                self._stop_flags.discard(session_id)
                messages.append({"role": "system", "content":
                    "The owner asked you to wrap up. Give your final answer now, "
                    "based on what you have so far."})
                reply = await self._final_answer(messages, timing, tool_messages)
                break

        if reply is None:  # round budget exhausted — force a final answer
            messages.append({"role": "system", "content":
                "Your round budget is exhausted. Give your final answer now, "
                "including what remains unfinished."})
            reply = await self._final_answer(messages, timing, None)

        self._remember(session_id, "assistant", reply)
        await self._bus.publish(ResponseDrafted(session_id=session_id, response_text=reply))
        return reply

    # U61: subagents — a scoped, read-only sub-loop with its own round budget.
    _SUBAGENT_TOOLS: frozenset[str] = frozenset({
        "read_file", "git_prepare", "list_browser_tabs",
        "list_calendar_events_today", "get_unread_mail", "list_onedrive_files",
        "list_tasks", "list_todos", "list_reminders",
        "list_music_playlists", "list_speakers",
    })

    async def _delegate_subtask(self, arguments: dict, session_id: str, timing: dict) -> str:
        goal = str(arguments.get("goal", "")).strip()
        if not goal:
            return "[delegate_subtask: goal is required]"
        max_rounds = min(6, max(1, int(arguments.get("max_rounds", 4) or 4)))
        allowed = self._SUBAGENT_TOOLS & self._router.allowed_tools()
        specs = build_tool_specs(allowed)
        sub_id = f"{session_id}::sub"
        messages: list[dict] = [
            {"role": "system", "content": (
                "You are a focused SUBAGENT of the main assistant. Complete "
                "exactly this subtask and nothing else, using only your "
                "read-only tools. You cannot write, launch apps, or delegate. "
                "Return a concise, factual result the main agent can use.")},
            {"role": "user", "content": goal},
        ]
        logger.info("subagent started: %r (max_rounds=%d)", goal[:80], max_rounds)
        for _round in range(max_rounds):
            _t = time.perf_counter()
            resp = await openai_chat(messages, tools=specs or None)
            timing["llm_ms"] += (time.perf_counter() - _t) * 1000
            if not resp["tool_calls"]:
                return resp["content"] or "(subagent returned no result)"
            atc, tool_msgs, _names = await self._run_tool_round(
                resp["tool_calls"], sub_id, timing, restrict=allowed)
            messages.append({"role": "assistant", "content": resp["content"] or None,
                             "tool_calls": atc})
            messages.extend(tool_msgs)
        messages.append({"role": "system", "content":
                         "Round budget exhausted — give your final concise result now."})
        final = await openai_chat(messages)
        return final["content"] or "(subagent: budget exhausted without a result)"

    async def _save_skill(self, arguments: dict) -> str:
        """U60 self-training: persist an owner-approved skill (gate fired upstream)."""
        if self._skills is None:
            return "[save_skill: skills are not configured on this install]"
        from orchestrator.skills import Skill

        name = str(arguments.get("name", "")).strip().lower()
        existing = self._skills.get(name)
        try:
            skill = Skill(
                name=name,
                description=str(arguments.get("description", "")).strip(),
                triggers=[str(t).strip().lower() for t in arguments.get("triggers", []) if str(t).strip()],
                personas=[str(p).strip().lower() for p in arguments.get("personas", []) if str(p).strip()],
                person=str(arguments.get("person", "")).strip(),
                body=str(arguments.get("body", "")),
            )
            self._skills.save(skill)
        except ValueError as exc:
            return f"[save_skill: {exc}]"
        verb = "Updated" if existing else "Learned new"
        scope = f" for {skill.person}" if skill.person else ""
        return f"{verb} skill '{skill.name}'{scope} — I'll follow it from now on."

    async def _final_answer(self, messages: list[dict], timing: dict,
                            tool_messages: list[dict] | None) -> str:
        """One tool-less synthesis call (stop / budget-exhausted paths)."""
        _t = time.perf_counter()
        final = await openai_chat(messages)
        timing["llm_ms"] += (time.perf_counter() - _t) * 1000
        fallback = "\n".join(m["content"] for m in (tool_messages or [])) or "(no response)"
        return final["content"] or fallback

    async def _run_tool_round(
        self, tool_calls: list, session_id: str, timing: dict,
        restrict: frozenset[str] | None = None,
    ) -> tuple[list[dict], list[dict], list[str]]:
        """Gate + execute one round of tool calls; returns (assistant_tool_calls,
        tool_messages, executed_tool_names).

        The OpenAI API requires that EVERY advertised tool_call gets a matching
        `tool` message on the follow-up turn — including blocked/denied ones —
        keyed by tool_call_id.
        """
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

            # U61: subagents run with a hard tool allowlist — anything outside
            # it is refused even if the mode would allow it.
            if restrict is not None and tool_name not in restrict:
                tool_messages.append({"role": "tool", "tool_call_id": tc_id,
                                      "content": f"[{tool_name}: not available to this subagent]"})
                continue

            # U61: deterministic pre-hooks (e.g. "tests before git push") —
            # a blocking hook replaces execution with its message so the
            # model reads why and adapts next round.
            from orchestrator.hooks import pre_hook_block

            blocked = pre_hook_block(tool_name, args_str)
            if blocked is not None:
                logger.info("hook blocked %r: %s", tool_name, blocked)
                tool_messages.append({"role": "tool", "tool_call_id": tc_id,
                                      "content": blocked})
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
            elif tool_name == "use_computer":
                if self._computer_use is None:
                    result_text = ("[use_computer: not available — enable Computer "
                                   "Use in the capabilities panel (works with your "
                                   "OpenAI or Anthropic key)]")
                else:
                    from shared_schemas.events.orchestrator import (
                        ComputerControlEnded, ComputerControlStarted,
                    )

                    goal = arguments.get("goal", "")
                    await self._bus.publish(ComputerControlStarted(
                        session_id=session_id, goal=goal[:200]))
                    try:
                        result_text = await self._computer_use.run(goal, session_id)
                    finally:
                        await self._bus.publish(ComputerControlEnded(
                            session_id=session_id, summary=str(result_text)[:200] if 'result_text' in dir() else ""))
            elif tool_name == "save_skill":
                result_text = await self._save_skill(arguments)
            elif tool_name == "delegate_subtask":
                result_text = await self._delegate_subtask(arguments, session_id, timing)
            elif tool_name == "run_powershell":
                result_text = await laptop_tools.run_powershell(
                    arguments.get("command", ""), arguments.get("working_dir"),
                )
            elif tool_name == "read_file":
                result_text = await laptop_tools.read_file(arguments.get("path", ""))
            elif tool_name == "write_file":
                result_text = await laptop_tools.write_file(
                    arguments.get("path", ""), arguments.get("content", ""),
                )
            elif tool_name == "git_prepare":
                result_text = await laptop_tools.git_prepare(
                    arguments.get("action", ""), arguments.get("working_dir"),
                )
            elif tool_name == "open_in_vscode":
                result_text = await _open_in_vscode(
                    arguments.get("path", ""), arguments.get("line"),
                )
            elif tool_name == "launch_app":
                result_text = await _launch_app(arguments.get("name", ""))
            elif tool_name == "media_control":
                result_text = await _media_control(arguments.get("action", ""))
            else:
                result_text = await self._call_connector(tool_name, arguments)
            # U61: post-hooks append deterministic follow-up notes.
            from orchestrator.hooks import post_hook_notes

            for note in post_hook_notes(tool_name, json.dumps(arguments)):
                result_text += f"\n[hook] {note}"
            await self._bus.publish(ToolCallSucceeded(
                session_id=session_id, tool_name=tool_name, result_summary=result_text[:500],
            ))
            return {"role": "tool", "tool_call_id": tc_id, "content": result_text}

        if to_execute:
            _t = time.perf_counter()
            results = await asyncio.gather(*(_run(*x) for x in to_execute))
            timing["tool_ms"] += (time.perf_counter() - _t) * 1000  # wall-clock (parallel)
            tool_messages.extend(results)

        executed = [name for _tc, name, _args in to_execute]
        return assistant_tool_calls, tool_messages, executed

    async def _offline_reply(self, text: str, session_id: str) -> str:
        """Degraded/offline turn: a LOCAL model if one is configured and reachable,
        otherwise the regex FallbackAgent. Tools/connectors are skipped (offline)."""
        if self._offline_llm_base:
            try:
                system = self._persona.render_system_prompt(
                    "(operating offline on a local model — no live tools)", ""
                )
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ]
                resp = await local_chat(
                    messages, base_url=self._offline_llm_base, model=self._offline_llm_model
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
