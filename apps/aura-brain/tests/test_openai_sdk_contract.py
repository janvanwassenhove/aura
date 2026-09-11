"""U322: the OpenAI SDK surface AURA depends on, pinned as a contract.

GPT-Live (ADR-011) exists only on the Live API, and the SDK AURA ran — 2.33 —
had no client for it: `AsyncOpenAI().live` did not exist. The upgrade to 3.13
is a MAJOR version, so this test states both halves of the bargain: the new
resource the Live engine needs is there, and every resource the other three
speech paths and the orchestrator already use is still there.

Verified before the upgrade: 3.13 passes all seven package suites and a real
chat, TTS, transcription and realtime round-trip on the owner's key.
"""

from __future__ import annotations

import openai
from openai import AsyncOpenAI, OpenAI


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key="x")                     # no network is used


def test_the_sdk_is_the_major_version_the_lock_promises() -> None:
    assert int(openai.__version__.split(".")[0]) >= 3, openai.__version__


def test_the_live_api_has_a_client() -> None:
    """The one thing U324 cannot be built without."""
    c = _client()
    assert hasattr(c, "live"), "no Live API client — GPT-Live cannot connect"
    assert callable(c.live.connect)


def test_the_live_connection_speaks_the_documented_verbs() -> None:
    """send / recv / iterate / close — what live_session.py calls."""
    from openai.resources.live.live import AsyncLiveConnection

    for verb in ("send", "recv", "__aiter__", "close"):
        assert hasattr(AsyncLiveConnection, verb), verb


def test_everything_the_other_paths_use_is_still_there() -> None:
    """A major bump must not quietly take a resource from under the pipeline,
    the realtime paths or the orchestrator."""
    c = _client()
    assert callable(c.realtime.connect)                 # realtime_voice, realtime_session
    assert callable(c.audio.transcriptions.create)      # voice.transcribe
    assert callable(c.audio.speech.create)              # voice.synthesize
    assert callable(c.chat.completions.create)          # orchestrator.llm
    assert callable(OpenAI(api_key="x").chat.completions.create)
