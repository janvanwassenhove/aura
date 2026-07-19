"""U107: self-optimizing skills — usage observations + LLM rewrite proposal."""

from __future__ import annotations

import json
import os

os.environ.setdefault("LLM_PROVIDER", "echo")

import pytest

from orchestrator.skill_optimizer import propose_optimization, summarize_observations
from orchestrator.skills import Skill, SkillStore

SKILL_MD = """---
name: start-spotify
description: Open Spotify and start a playlist
enabled: true
---
1. Open Spotify.
2. Play music.
"""


@pytest.fixture()
def store(tmp_path):
    s = SkillStore(str(tmp_path))
    s.save(_skill())
    return s


def _skill() -> Skill:
    from orchestrator.skills import _parse
    return _parse(SKILL_MD, "start-spotify")


# ------------------------------------------------------------------
# Observation recording + metrics
# ------------------------------------------------------------------

def test_observations_recorded_and_capped(store) -> None:
    for i in range(5):
        store.record_observation("start-spotify", {"request": f"play set {i}", "persona": "personal"})
    obs = store.observations("start-spotify")
    assert len(obs) == 5
    assert obs[0]["request"] == "play set 0"
    assert all("ts" in o for o in obs)


def test_metrics_track_new_since_optimized(store) -> None:
    for i in range(3):
        store.record_observation("start-spotify", {"request": f"r{i}"})
    m = store.metrics("start-spotify")
    assert m["uses"] == 3 and m["new_since_optimized"] == 3

    store.mark_optimized("start-spotify")
    assert store.metrics("start-spotify")["new_since_optimized"] == 0

    store.record_observation("start-spotify", {"request": "another"})
    m2 = store.metrics("start-spotify")
    assert m2["uses"] == 4 and m2["new_since_optimized"] == 1


def test_metrics_survive_the_observation_cap(store, monkeypatch) -> None:
    """U159: the marker used to be a raw observation count, which froze once a
    skill hit the _MAX_OBS ring-buffer cap — len(obs) stopped growing so
    new_since_optimized was stuck at 0 and suggestions died forever."""
    from orchestrator import skills as _skills

    monkeypatch.setattr(_skills, "_MAX_OBS", 5)
    for i in range(5):
        store.record_observation("start-spotify", {"request": f"r{i}"})
    store.mark_optimized("start-spotify")
    assert store.metrics("start-spotify")["new_since_optimized"] == 0

    # More uses: the buffer stays capped at 5, but new signals must still show.
    for i in range(3):
        store.record_observation("start-spotify", {"request": f"n{i}"})
    m = store.metrics("start-spotify")
    assert m["uses"] == 5                      # ring buffer capped
    assert m["new_since_optimized"] == 3       # …yet new signals are counted


def test_legacy_count_marker_still_read(store) -> None:
    """Markers written before U159 are a bare count — keep honouring them."""
    for i in range(4):
        store.record_observation("start-spotify", {"request": f"r{i}"})
    (store._metrics_dir / "start-spotify.optimized").write_text("3", encoding="utf-8")
    assert store.metrics("start-spotify")["new_since_optimized"] == 1


def test_delete_removes_metrics(store) -> None:
    store.record_observation("start-spotify", {"request": "x"})
    assert store.delete("start-spotify")
    assert store.observations("start-spotify") == []


def test_summary_digests_requests() -> None:
    obs = [{"request": "play the champions", "persona": "personal", "person": "jan"}]
    text = summarize_observations(obs)
    assert "champions" in text and "personal" in text


# ------------------------------------------------------------------
# Proposal (fake chat_fn — no network)
# ------------------------------------------------------------------

async def _fake_chat(messages, model=None):
    # The optimizer must feed the current body + evidence into the prompt.
    prompt = messages[0]["content"]
    assert "start-spotify" in prompt and "play set" in prompt
    return {"content": json.dumps({
        "changed": True,
        "rationale": "Merged steps and added a guardrail.",
        "body": "1. Launch Spotify via API (fall back to the app).\n2. Start the requested playlist; confirm it is playing.",
    })}


async def test_propose_returns_diff_without_saving(store) -> None:
    for i in range(3):
        store.record_observation("start-spotify", {"request": f"play set {i}"})
    result = await propose_optimization(store, "start-spotify", _fake_chat)
    assert result["changed"] is True
    assert "guardrail" in result["rationale"]
    assert "Launch Spotify" in result["proposed_body"]
    assert result["based_on"] == 3
    # Nothing was written — the stored body is unchanged until the owner applies.
    assert store.get("start-spotify").body.startswith("1. Open Spotify.")


async def test_propose_unknown_skill_errors(store) -> None:
    result = await propose_optimization(store, "nope", _fake_chat)
    assert "error" in result


async def test_propose_handles_garbage_model_output(store) -> None:
    async def _garbage(messages, model=None):
        return {"content": "sorry I can't do that"}

    result = await propose_optimization(store, "start-spotify", _garbage)
    assert "error" in result


# ------------------------------------------------------------------
# U118: creation-time polish (no store, no usage evidence)
# ------------------------------------------------------------------

async def test_polish_draft_rewrites_body() -> None:
    from orchestrator.skill_optimizer import polish_draft

    async def _chat(messages, model=None):
        assert "vrt max" in messages[0]["content"]
        return {"content": json.dumps({"changed": True, "rationale": "Numbered the steps.",
                                       "body": "1. Open vrtmax.\n2. Cast to the living-room TV."})}

    result = await polish_draft("vrtmax", "cast vrt", "ga naar vrt max en cast", _chat)
    assert result["changed"] is True
    assert result["body"].startswith("1. Open vrtmax.")


async def test_polish_draft_survives_llm_failure() -> None:
    from orchestrator.skill_optimizer import polish_draft

    async def _boom(messages, model=None):
        raise RuntimeError("no key")

    result = await polish_draft("x", "", "do the thing", _boom)
    assert "error" in result


# ------------------------------------------------------------------
# SEC (U121): a malicious skill name must never escape the skills dir.
# ------------------------------------------------------------------

def test_traversal_name_cannot_delete_outside_dir(tmp_path) -> None:
    secret = tmp_path.parent / "secret.md"
    secret.write_text("keep me", encoding="utf-8")
    s = SkillStore(str(tmp_path))
    assert s.delete("../secret") is False          # rejected, not deleted
    assert s.delete("..\\secret") is False
    assert secret.exists()


def test_traversal_name_has_no_metrics_path(store) -> None:
    assert store._obs_path("../../etc/passwd") is None
    assert store._opt_path("../evil") is None
    # And the public methods degrade safely rather than touching disk.
    store.record_observation("../../evil", {"request": "x"})
    assert store.observations("../../evil") == []
    assert store.metrics("../../evil")["uses"] == 0
