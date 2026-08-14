"""U247: the skill ledger recorded intentions, never outcomes.

Reported as three broken things in one evening — Spotify would not search,
the Claude app would not open, Chrome would not be typed in — all of them the
same dead step (`use_computer`, backend pruned; see U246). The self-optimizing
loop had been running through every one of those failures and could not have
learned from them: an observation was written BEFORE the turn ran and carried
only the request text.

On the owner's machine the evidence was worse than empty. Of the seven recorded
"uses" of the Spotify skill, four were the robot greeting somebody — greetings
run through the same pipeline, so they matched the triggers and were logged as
uses of a skill they have nothing to do with.
"""

from __future__ import annotations

import json
import time

from orchestrator.skill_optimizer import summarize_observations
from orchestrator.skills import SkillStore
from shared_schemas.tool_outcome import (
    mark_unavailable,
    unavailable_capabilities,
    unavailable_capability,
)

# ---------------------------------------------------------------------------
# The marker: "the tool answered, and the thing did not happen".
# ---------------------------------------------------------------------------

REAL_MOCK_REPLY = (
    "NOT_PLAYED_VIA_API. There is no Spotify account token, so I cannot start "
    "playback through Spotify's API or pick the Sonos."
)


def test_a_marked_result_names_its_capability() -> None:
    marked = mark_unavailable("music", REAL_MOCK_REPLY)
    assert unavailable_capability(marked) == "music"


def test_the_prose_survives_untouched() -> None:
    """The wording is what makes the assistant's REPLY honest. The marker is
    for the machinery; it must not cost the sentence."""
    marked = mark_unavailable("music", REAL_MOCK_REPLY)
    assert REAL_MOCK_REPLY in marked


def test_an_ordinary_result_is_not_a_failure() -> None:
    assert unavailable_capability("Playing Creep by Radiohead on Sonos.") is None
    assert unavailable_capability("") is None


def test_a_result_that_merely_mentions_trouble_is_not_marked() -> None:
    """Substring-sniffing prose is exactly what this replaces — reword the
    sentence and the classifier silently stops working."""
    assert unavailable_capability(
        "I could not find that track and nothing is unavailable right now") is None


def test_a_round_of_tool_messages_reports_every_failure() -> None:
    round_messages = [
        {"role": "tool", "content": "Opened Spotify."},
        {"role": "tool", "content": mark_unavailable("music", REAL_MOCK_REPLY)},
        {"role": "tool", "content": mark_unavailable("use_computer", "[not available]")},
    ]
    assert unavailable_capabilities(round_messages) == ["music", "use_computer"]


def test_no_failures_is_an_empty_list_not_a_crash() -> None:
    assert unavailable_capabilities([]) == []
    assert unavailable_capabilities(None) == []


# ---------------------------------------------------------------------------
# The digest the optimizer actually reads.
# ---------------------------------------------------------------------------


def _use(request: str, **extra) -> dict:
    return {"ts": time.time(), "request": request, "persona": "work", **extra}


def test_the_digest_leads_with_what_kept_failing() -> None:
    obs = [
        _use("speel radiohead op spotify", tools=["play_music", "launch_app"],
             unavailable=["music"]),
        _use("speel nofx in spotify", tools=["play_music"], unavailable=["music"]),
        _use("zet de muziek uit", tools=["media_control"], unavailable=[]),
    ]
    digest = summarize_observations(obs)
    assert "UNAVAILABLE" in digest
    assert "music: 2 of 3" in digest
    assert digest.index("UNAVAILABLE") < digest.index("recent requests"), \
        "the failures must lead — that is what a rewrite should act on"


def test_the_digest_says_what_to_do_with_it() -> None:
    """A count alone is a fact. The optimizer needs to know it is allowed to
    route around the missing capability, or to refuse plainly."""
    digest = summarize_observations([_use("x", unavailable=["use_computer"])])
    assert "does not need it" in digest
    assert "instead of half-executing" in digest


def test_a_healthy_skill_gets_no_failure_section() -> None:
    digest = summarize_observations([
        _use("open vscode in de repo", tools=["open_in_vscode"], unavailable=[]),
    ])
    assert "UNAVAILABLE" not in digest
    assert "tools used: open_in_vscode×1" in digest


def test_old_style_observations_still_summarize() -> None:
    """Lines written before this unit have no tools/unavailable keys at all."""
    digest = summarize_observations([
        {"ts": 1, "request": "kan je nummer nofx afspelen in spotify", "persona": "work"},
    ])
    assert "nofx" in digest
    assert "UNAVAILABLE" not in digest


def test_no_uses_yet() -> None:
    assert summarize_observations([]) == "(no recorded uses yet)"


# ---------------------------------------------------------------------------
# Retention: these lines quote the owner verbatim.
# ---------------------------------------------------------------------------


def _store(tmp_path) -> SkillStore:
    (tmp_path / "spotify.md").write_text(
        "---\nname: spotify\ndescription: play music\ntriggers: spotify\n---\nbody\n",
        encoding="utf-8")
    return SkillStore(str(tmp_path))


def test_observations_are_capped_by_count(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.skills._MAX_OBS", 5)
    store = _store(tmp_path)
    for i in range(12):
        store.record_observation("spotify", {"request": f"r{i}"})
    obs = store.observations("spotify")
    assert len(obs) == 5
    assert obs[-1]["request"] == "r11", "the most recent survive"


def test_observations_expire(tmp_path, monkeypatch) -> None:
    """The count cap never bites on a skill used seven times in a year, so the
    owner's words sat there indefinitely."""
    monkeypatch.setattr("orchestrator.skills._MAX_OBS_AGE_DAYS", 30)
    store = _store(tmp_path)
    path = tmp_path / ".metrics" / "spotify.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    ancient = time.time() - 400 * 86_400
    path.write_text(
        json.dumps({"ts": ancient, "seq": 1, "request": "something from last year"})
        + "\n", encoding="utf-8")

    store.record_observation("spotify", {"request": "today"})

    requests = [o["request"] for o in store.observations("spotify")]
    assert requests == ["today"], f"the old line should be gone, got {requests}"


def test_expiry_can_be_switched_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.skills._MAX_OBS_AGE_DAYS", 0)
    store = _store(tmp_path)
    path = tmp_path / ".metrics" / "spotify.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"ts": time.time() - 900 * 86_400, "seq": 1, "request": "ancient"})
        + "\n", encoding="utf-8")
    store.record_observation("spotify", {"request": "today"})
    assert len(store.observations("spotify")) == 2


# ---------------------------------------------------------------------------
# The pipeline end: what actually lands in the ledger, and when.
# ---------------------------------------------------------------------------

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from shared_events.bus import AsyncEventBus


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture()
def pipeline(bus, tmp_path) -> OrchestratorPipeline:
    p = OrchestratorPipeline(bus, IntentRouter(mode="work"),
                             ApprovalManager(bus, session_id="t"),
                             ContextBuilder(), PersonaManager())
    p.set_skill_store(_store(tmp_path))
    return p


async def test_a_real_request_writes_one_ledger_line(pipeline) -> None:
    await pipeline.orchestrate("speel iets op spotify", "s1")
    obs = pipeline._skills.observations("spotify")
    assert len(obs) == 1
    assert obs[0]["request"] == "speel iets op spotify"


async def test_a_greeting_writes_nothing(pipeline) -> None:
    """Four of the seven recorded uses of the Spotify skill on the owner's
    machine were this: the robot saying hello, through the same pipeline."""
    await pipeline.orchestrate(
        "(system note: Jan just walked up...) Greet Jan by name. spotify",
        "s1", from_user=False)
    assert pipeline._skills.observations("spotify") == []


async def test_the_line_carries_the_outcome(pipeline, monkeypatch) -> None:
    """The whole point: a use that died on a missing capability must LOOK
    different in the ledger from one that worked."""
    async def fake_round(tool_calls, session_id, timing, restrict=None):
        return ([], [{"role": "tool", "content":
                      mark_unavailable("use_computer", "[not available]")}],
                ["use_computer"])
    monkeypatch.setattr(pipeline, "_run_tool_round", fake_round)
    monkeypatch.setattr(pipeline, "_llm", _one_tool_call_then_done())

    await pipeline.orchestrate("zoek radiohead in spotify", "s1")

    obs = pipeline._skills.observations("spotify")
    assert obs and obs[-1]["unavailable"] == ["use_computer"]
    assert obs[-1]["tools"] == ["use_computer"]


def _one_tool_call_then_done():
    """Round 1 asks for a tool, round 2 answers — the shortest real shape."""
    calls = {"n": 0}

    async def _llm(messages, tools, timing, session_id, model=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "cancelled": False,
                    "tool_calls": [{"id": "c1", "name": "use_computer",
                                    "arguments": '{"goal": "search radiohead"}'}]}
        return {"content": "done", "tool_calls": None, "cancelled": False}
    return _llm
