"""LLM wrapper — wraps OpenAI chat completions with a pluggable echo mode.

Supported providers (set via ``LLMConfig`` in ``orchestrator.config``):
  - ``openai``     — OpenAI API (default). Uses ``OPENAI_API_KEY`` env var.
  - ``openrouter`` — OpenRouter API. Uses ``OPENROUTER_API_KEY`` env var.
  - ``gemini``     — Google Gemini API. Uses ``GEMINI_API_KEY`` env var.
  - ``echo``       — Echo mode for testing. No API key required.

Provider and model can be changed at runtime via ``update_config()`` without
restarting the container.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from orchestrator.config import get_config

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


async def openai_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call the LLM and return the raw choice dict.

    Returns a dict with at least:
      - ``content``: str | None — the assistant text reply
      - ``tool_calls``: list | None — OpenAI tool call objects

    When provider is ``echo`` the last user message is echoed back — no
    API key required.
    """
    cfg = get_config()
    provider = cfg.provider

    if provider == "echo":
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        logger.debug("LLM echo mode: echoing user message (%d chars)", len(last_user))
        return {"content": f"[echo] {last_user}", "tool_calls": None}

    # --- Gemini ---
    if provider == "gemini":
        from google import genai as google_genai
        from google.genai import types as genai_types

        gclient = google_genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        model = cfg.model

        # Convert OpenAI messages format → Gemini contents format
        contents = []
        system_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content") or ""
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                contents.append(genai_types.Content(role="model", parts=[genai_types.Part(text=content)]))
            else:
                contents.append(genai_types.Content(role="user", parts=[genai_types.Part(text=content)]))

        generate_kwargs: dict[str, Any] = {}
        if system_parts:
            generate_kwargs["system_instruction"] = " ".join(system_parts)
        if tools:
            # Map OpenAI tool schema to Gemini function declarations
            func_decls = [
                genai_types.FunctionDeclaration(
                    name=t["function"]["name"],
                    description=t["function"].get("description", ""),
                    parameters=t["function"].get("parameters"),
                )
                for t in tools
                if t.get("type") == "function" and "function" in t
            ]
            if func_decls:
                generate_kwargs["tools"] = [genai_types.Tool(function_declarations=func_decls)]

        logger.debug("LLM request (gemini): model=%s messages=%d", model, len(messages))
        response = await gclient.aio.models.generate_content(
            model=model,
            contents=contents,
            config=genai_types.GenerateContentConfig(**generate_kwargs) if generate_kwargs else None,
        )

        text_content: str | None = None
        tool_calls = None
        candidate = response.candidates[0] if response.candidates else None
        if candidate:
            for part in (candidate.content.parts or []):
                if part.function_call:
                    if tool_calls is None:
                        tool_calls = []
                    import json
                    tool_calls.append({
                        "id": f"gemini_{part.function_call.name}",
                        "name": part.function_call.name,
                        "arguments": json.dumps(dict(part.function_call.args or {})),
                    })
                elif part.text:
                    text_content = (text_content or "") + part.text

        logger.debug("LLM response (gemini): finish=%s", candidate.finish_reason if candidate else "none")
        return {"content": text_content, "tool_calls": tool_calls}

    # --- OpenRouter ---
    if provider == "openrouter":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            base_url=_OPENROUTER_BASE_URL,
        )
        model = cfg.model

    # --- OpenAI ---
    else:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        model = cfg.model

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    logger.debug("LLM request: model=%s messages=%d", model, len(messages))
    response = await client.chat.completions.create(**kwargs)
    choice = response.choices[0].message
    logger.debug("LLM response: finish_reason=%s", response.choices[0].finish_reason)

    tool_calls = None
    if choice.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in choice.tool_calls
        ]

    return {"content": choice.content, "tool_calls": tool_calls}
