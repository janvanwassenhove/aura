"""U249: the assistant can ask to be unblocked, and guidance stops evaporating.

Everything that went wrong this week was one switch away from working — screen
control pruned out of the environment, Chrome without its debug port, music
without a token. The assistant hit each of them and could say nothing useful,
because the approval gate only answers "may I do this thing I can already do".

Three parts here: what it may ask for (and the bound on that), the trigger that
notices a skill keeps failing, and the owner's mid-run corrections finally
leaving a trace.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import unblocks
from orchestrator.approval_manager import ApprovalManager
from orchestrator.context_builder import ContextBuilder
from orchestrator.intent_router import IntentRouter
from orchestrator.persona_manager import PersonaManager
from orchestrator.pipeline import OrchestratorPipeline
from orchestrator.skill_optimizer import summarize_observations
from shared_events.bus import AsyncEventBus
from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP

# ---------------------------------------------------------------------------
# The bound. This is the part that matters most.
# ---------------------------------------------------------------------------


def test_asking_always_needs_approval() -> None:
    assert "request_capability" in APPROVAL_REQUIRED


def test_every_mode_can_ask() -> None:
    """A mode that cannot ask goes quiet when it hits a wall — the behaviour
    this was built to end."""
    for mode, tools in MODE_TOOL_MAP.items():
        assert "request_capability" in tools, mode


def test_the_model_never_supplies_a_value() -> None:
    """U215 was exactly this shape: a settings value carrying a newline wrote
    an EXTRA env line and became a persistent RCE. Values live in the
    catalogue, never in the tool call."""
    from orchestrator.tool_schemas import TOOL_SCHEMAS

    params = TOOL_SCHEMAS["request_capability"]["function"]["parameters"]
    assert set(params["properties"]) == {"capability", "reason"}
    assert params["additionalProperties"] is False


def test_an_unknown_capability_is_refused(tmp_path) -> None:
    p = _pipeline_for_grant()
    out = p._grant_capability({"capability": "sudo", "reason": "trust me"})
    assert "not something you can ask for" in out
    assert "computer_use" in out, "and it is told what it CAN ask for"


def test_a_made_up_key_cannot_reach_the_env(monkeypatch) -> None:
    """The catalogue is the allowlist. A model naming a raw env key — the
    obvious thing to try — writes nothing and gets told so."""
    monkeypatch.delenv("AURA_TEST_INJECTED", raising=False)
    monkeypatch.delenv("COMPUTER_USE_ENABLED", raising=False)
    writes: list[dict] = []
    import aura_brain.setup_api as setup_api

    monkeypatch.setattr(setup_api, "_write_env",
                        lambda u: writes.append(u) or True, raising=False)

    injected = "computer_use\nAURA_TEST_INJECTED=1"   # the U215 shape
    p = _pipeline_for_grant()
    for attempt in ("COMPUTER_USE_ENABLED", "AURA_TEST_INJECTED=1", injected, ""):
        out = p._grant_capability({"capability": attempt, "reason": "x"})
        assert "not something you can ask for" in out, attempt

    assert writes == [], "nothing outside the catalogue may write a setting"
    assert "AURA_TEST_INJECTED" not in os.environ
    assert "COMPUTER_USE_ENABLED" not in os.environ


# ---------------------------------------------------------------------------
# What granting actually does
# ---------------------------------------------------------------------------


def _pipeline_for_grant() -> OrchestratorPipeline:
    bus = AsyncEventBus()
    return OrchestratorPipeline(bus, IntentRouter(mode="work"),
                                ApprovalManager(bus, session_id="t"),
                                ContextBuilder(), PersonaManager())


def test_an_automatic_grant_takes_effect_now(monkeypatch) -> None:
    monkeypatch.delenv("COMPUTER_USE_ENABLED", raising=False)
    out = _pipeline_for_grant()._grant_capability(
        {"capability": "computer_use", "reason": "I need to search inside Spotify"})
    assert os.environ["COMPUTER_USE_ENABLED"] == "true", "not after a restart — now"
    assert "Granted" in out
    assert "To undo" in out, "the owner is told how to take it back"


def test_a_manual_one_says_what_the_owner_must_do() -> None:
    out = _pipeline_for_grant()._grant_capability(
        {"capability": "music_account", "reason": "to play a specific track"})
    assert "needs their hands" in out
    assert "Settings" in out, "and exactly where to go"


def test_every_catalogue_entry_is_either_automatic_or_explains_itself() -> None:
    for entry in unblocks.CATALOGUE.values():
        assert entry.automatic or entry.manual, entry.key
        assert entry.why, entry.key


def test_the_capability_names_map_to_entries() -> None:
    """The marker a tool returns has to lead somewhere the model can name."""
    for cap, key in unblocks.FOR_CAPABILITY.items():
        assert key in unblocks.CATALOGUE, f"{cap} → {key}"


def test_the_catalogue_the_model_sees_lists_keys_only() -> None:
    described = unblocks.describe_for_model()
    for key in unblocks.CATALOGUE:
        assert key in described
    assert "COMPUTER_USE_ENABLED" not in described, "env keys are not the model's business"


# ---------------------------------------------------------------------------
# The trigger: failing beats popular
# ---------------------------------------------------------------------------


def _obs(n: int, *, blocked: int = 0, cap: str = "browser") -> list[dict]:
    # No "ts": record_observation stamps it, and an explicit one here would
    # override it — at ts=1 every line is instantly older than the retention
    # window and vanishes before the test can look.
    out = [{"request": f"r{i}", "unavailable": []} for i in range(n)]
    for o in out[:blocked]:
        o["unavailable"] = [cap]
    return out


def test_metrics_count_recent_failures(tmp_path) -> None:
    from orchestrator.skills import SkillStore

    (tmp_path / "chrome.md").write_text(
        "---\nname: chrome\ndescription: browse\ntriggers: chrome\n---\nbody\n",
        encoding="utf-8")
    store = SkillStore(str(tmp_path))
    for o in _obs(3, blocked=2):
        store.record_observation("chrome", o)

    m = store.metrics("chrome")
    assert m["blocked"] == 2
    assert m["missing"] == {"browser": 2}
    assert m["uses"] == 3


def test_a_working_skill_reports_no_blockage(tmp_path) -> None:
    from orchestrator.skills import SkillStore

    (tmp_path / "spotify.md").write_text(
        "---\nname: spotify\ndescription: music\ntriggers: spotify\n---\nbody\n",
        encoding="utf-8")
    store = SkillStore(str(tmp_path))
    for o in _obs(9):
        store.record_observation("spotify", o)
    m = store.metrics("spotify")
    assert m["blocked"] == 0
    assert m["missing"] == {}


# ---------------------------------------------------------------------------
# Owner guidance survives the turn
# ---------------------------------------------------------------------------


@pytest.fixture()
async def bus() -> AsyncEventBus:
    b = AsyncEventBus()
    await b.start()
    yield b
    await b.stop()


def _store(tmp_path):
    from orchestrator.skills import SkillStore

    (tmp_path / "chrome.md").write_text(
        "---\nname: chrome\ndescription: browse\ntriggers: chrome\n---\nbody\n",
        encoding="utf-8")
    return SkillStore(str(tmp_path))


async def test_a_correction_lands_in_the_ledger(bus, tmp_path) -> None:
    p = OrchestratorPipeline(bus, IntentRouter(mode="work"),
                             ApprovalManager(bus, session_id="t"),
                             ContextBuilder(), PersonaManager())
    p.set_skill_store(_store(tmp_path))
    p.steer("s1", "gebruik open_browser_url, niet het scherm")

    await p.orchestrate("zoek iets op in chrome", "s1")

    obs = p._skills.observations("chrome")
    assert obs, "the turn was recorded"
    assert obs[-1]["steering"] == ["gebruik open_browser_url, niet het scherm"]


def test_the_optimizer_is_told_to_take_corrections_literally() -> None:
    digest = summarize_observations([{
        "ts": 1, "request": "zoek iets", "persona": "work",
        "steering": ["gebruik open_browser_url, niet het scherm"],
    }])
    assert "CORRECTED YOU MID-RUN" in digest
    assert "open_browser_url" in digest
    assert digest.index("CORRECTED") < digest.index("recent requests"), \
        "the owner's own words outrank everything else in the evidence"


def test_no_corrections_adds_nothing() -> None:
    digest = summarize_observations([{"ts": 1, "request": "x", "persona": "work"}])
    assert "CORRECTED" not in digest
