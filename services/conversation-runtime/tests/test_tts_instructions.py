"""U409: a direction reaches the TTS model — when the model can take one.

`gpt-4o-mini-tts` performs a line as instructed ("powerful, short"); `tts-1`
and `tts-1-hd` have no such parameter and reject the call if it is sent. The
provider used to send text only, whatever the scenario asked for.
"""

from __future__ import annotations

import types

import pytest
from conversation_runtime.providers.openai_provider import (
    OpenAITTSProvider,
    supports_instructions,
)


class _Speech:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(content=b"\x00\x01")


def _provider(model: str) -> tuple[OpenAITTSProvider, _Speech]:
    provider = OpenAITTSProvider(api_key="test", model=model, voice="ash")
    speech = _Speech()
    provider._client = types.SimpleNamespace(audio=types.SimpleNamespace(speech=speech))
    return provider, speech


async def test_the_direction_is_sent_to_a_model_that_performs_it() -> None:
    provider, speech = _provider("gpt-4o-mini-tts")
    await provider.synthesize("Oh, I know this one.", instructions="powerful, short")
    assert speech.calls[0]["instructions"] == "powerful, short"


@pytest.mark.parametrize("model", ["tts-1", "tts-1-hd"])
async def test_never_to_one_that_cannot(model: str) -> None:
    provider, speech = _provider(model)
    await provider.synthesize("Oh, I know this one.", instructions="powerful, short")
    assert "instructions" not in speech.calls[0], "the line is still spoken, undirected"


async def test_no_direction_sends_nothing_extra() -> None:
    provider, speech = _provider("gpt-4o-mini-tts")
    await provider.synthesize("Hallo.")
    assert "instructions" not in speech.calls[0]


def test_which_models_take_a_direction() -> None:
    assert supports_instructions("gpt-4o-mini-tts")
    assert not supports_instructions("tts-1")
    assert not supports_instructions("tts-1-hd")
