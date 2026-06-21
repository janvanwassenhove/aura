"""Runtime LLM configuration — mutable singleton initialised from env vars.

Use ``get_config()`` to read the current config on every LLM call.
Use ``update_config()`` to change provider/model at runtime without a restart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

LLMProvider = Literal["openai", "openrouter", "gemini", "echo"]

_VALID_PROVIDERS: frozenset[str] = frozenset({"openai", "openrouter", "gemini", "echo"})


def _default_model(provider: str) -> str:
    if provider == "openrouter":
        return os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b:free")
    if provider == "gemini":
        return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _initial_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "openai")


def _initial_model() -> str:
    provider = _initial_provider()
    return _default_model(provider)


@dataclass
class LLMConfig:
    provider: str = field(default_factory=_initial_provider)
    model: str = field(default_factory=_initial_model)


_config = LLMConfig()


def get_config() -> LLMConfig:
    """Return the current runtime LLM config."""
    return _config


def update_config(provider: str, model: str) -> LLMConfig:
    """Update the runtime LLM config in-place. Returns the updated config."""
    if provider not in _VALID_PROVIDERS:
        raise ValueError(f"Invalid provider {provider!r}. Must be one of: {sorted(_VALID_PROVIDERS)}")
    _config.provider = provider
    _config.model = model
    return _config
