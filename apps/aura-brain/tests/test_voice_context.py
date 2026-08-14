"""U245: the Realtime speech path did not know who was in the room.

Reported: Richie greeted the owner by name at 19:58 and told him at 20:07 that
he had no memory of who anyone is. Both were honest. The greeting runs through
the turn pipeline, which injects the judgment layer's person note; the spoken
turns ran through a Realtime session, whose instructions were the character
prompt and nothing else.
"""

from __future__ import annotations

import asyncio

import pytest
from aura_brain.voice_context import build_instructions

CHARACTER = "You are Richie, a warm companion for children. Keep it playful."
NOTE = "Talking to: Jan (owner).\n  tone: concise\n  works on: AURA"


def test_the_person_reaches_the_instructions() -> None:
    """The whole bug in one assertion."""
    out = build_instructions(CHARACTER, NOTE)
    assert "Jan (owner)" in out
    assert "concise" in out, "the facts travel with the name"


def test_the_character_survives() -> None:
    out = build_instructions(CHARACTER, NOTE)
    assert CHARACTER in out, "personal context must not displace the voice"
    assert out.index(CHARACTER) < out.index("Jan (owner)"), "who it IS comes first"


def test_nobody_recognized_changes_nothing() -> None:
    """Most of the time there is no note. That must not add an empty heading or
    tell the model anything about a person who is not there."""
    out = build_instructions(CHARACTER, "")
    assert out == CHARACTER
    assert "Who you are talking to" not in out


def test_a_session_never_opens_without_instructions() -> None:
    """No character configured and nobody recognized still has to say something
    sensible — an empty instructions field makes the model invent a persona."""
    out = build_instructions("", "")
    assert "friendly robot assistant" in out
    assert "Dutch" in out, "language guidance is part of the floor"


def test_the_note_is_framed_as_knowledge_not_as_a_claim() -> None:
    """Without framing the model reads a bare block as something the user just
    asserted, and hedges — which is how it ends up saying it cannot remember
    anything while the memory sits in its own prompt."""
    out = build_instructions(CHARACTER, NOTE)
    assert "not something they just told you" in out
    assert "never claim you cannot remember" in out


def test_whitespace_does_not_leak_in() -> None:
    out = build_instructions("  " + CHARACTER + "\n\n", "\n  " + NOTE + "  \n")
    assert not out.startswith(" ")
    assert "\n\n\n" not in out


# --------------------------------------------------------------------------
# The session re-asks while it is open (people arrive mid-conversation).
# --------------------------------------------------------------------------


class FakeSessionAPI:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    async def update(self, session: dict) -> None:
        self.updates.append(session)


class FakeConn:
    def __init__(self) -> None:
        self.session = FakeSessionAPI()


def _session(provider):
    from aura_brain.realtime_session import RealtimeSession

    return RealtimeSession(
        robot=None, bus=None, session_id="t",
        instructions=build_instructions(CHARACTER, ""),
        instructions_provider=provider,
    )


@pytest.mark.asyncio
async def test_someone_walking_up_mid_session_updates_the_model(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "0.01")
    current = {"note": ""}

    async def provider() -> str:
        return build_instructions(CHARACTER, current["note"])

    sess = _session(provider)
    conn = FakeConn()

    assert await sess._refresh_instructions(conn) is False, "nothing changed yet"

    current["note"] = NOTE
    await asyncio.sleep(0.02)
    assert await sess._refresh_instructions(conn) is True
    assert "Jan (owner)" in conn.session.updates[-1]["instructions"]


@pytest.mark.asyncio
async def test_an_unchanged_room_sends_nothing(monkeypatch) -> None:
    """A session ticks about once a second. Re-sending identical instructions
    every tick is pure noise on the socket."""
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "0.01")

    async def provider() -> str:
        return build_instructions(CHARACTER, NOTE)

    sess = _session(provider)
    conn = FakeConn()
    await sess._refresh_instructions(conn)          # first: adopts the note
    for _ in range(5):
        await asyncio.sleep(0.02)
        await sess._refresh_instructions(conn)
    assert len(conn.session.updates) == 1


@pytest.mark.asyncio
async def test_the_refresh_is_throttled(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "60")
    calls = {"n": 0}

    async def provider() -> str:
        calls["n"] += 1
        return build_instructions(CHARACTER, NOTE)

    sess = _session(provider)
    conn = FakeConn()
    for _ in range(10):
        await sess._refresh_instructions(conn)
    assert calls["n"] == 1, "the profile is decrypted to build this; not every tick"


@pytest.mark.asyncio
async def test_a_failing_provider_never_kills_the_session(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "0.01")

    async def provider() -> str:
        raise RuntimeError("knowledge store locked")

    sess = _session(provider)
    conn = FakeConn()
    assert await sess._refresh_instructions(conn) is False
    assert conn.session.updates == []


@pytest.mark.asyncio
async def test_the_refresh_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("REALTIME_CONTEXT_REFRESH_S", "0")

    async def provider() -> str:
        return build_instructions(CHARACTER, NOTE)

    sess = _session(provider)
    conn = FakeConn()
    assert await sess._refresh_instructions(conn) is False
    assert conn.session.updates == []


# --------------------------------------------------------------------------
# The seam: the voice loop must ask the PIPELINE, not rebuild the note itself.
# That is what keeps the spoken and the typed path from drifting apart again.
# --------------------------------------------------------------------------


class FakeCharacter:
    character_prompt = CHARACTER
    voice_id = "alloy"


class FakePipeline:
    def __init__(self, note: str) -> None:
        self._note = note
        self.asked = 0

    async def person_note(self) -> str:
        self.asked += 1
        return self._note


def _loop(pipeline):
    from aura_brain.voice_loop import VoiceLoop

    return VoiceLoop(robot=None, pipeline=pipeline, bus=None)


@pytest.mark.asyncio
async def test_the_voice_loop_asks_the_pipeline_who_is_there() -> None:
    pipeline = FakePipeline(NOTE)
    out = await _loop(pipeline)._instructions(FakeCharacter())
    assert pipeline.asked == 1, "the note is asked of the pipeline, not rebuilt"
    assert "Jan (owner)" in out
    assert CHARACTER in out


@pytest.mark.asyncio
async def test_a_broken_pipeline_costs_the_note_not_the_turn() -> None:
    class Exploding:
        async def person_note(self) -> str:
            raise RuntimeError("no judgment layer")

    out = await _loop(Exploding())._instructions(FakeCharacter())
    assert CHARACTER in out, "the robot still speaks, just impersonally"


@pytest.mark.asyncio
async def test_no_character_configured_still_carries_the_person() -> None:
    out = await _loop(FakePipeline(NOTE))._instructions(None)
    assert "Jan (owner)" in out
