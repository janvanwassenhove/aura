"""D2: modes become a first-class capability boundary.

MODE_TOOL_MAP has governed what the robot may do since U58, and nothing in the
console could see or change it — mode surfaced as a 9px tinted dot. This layer
derives the eight human-facing capability groups from the REAL policy (never a
hand-written table), lets the owner override a row, and makes the override
change actual enforcement: the allowed tool set and the approval gate.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("LLM_PROVIDER", "echo")

from orchestrator import mode_policy
from orchestrator.intent_router import IntentRouter
from shared_policies import APPROVAL_REQUIRED, MODE_TOOL_MAP


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "mode-policy.json"))
    mode_policy.reset_cache_for_tests()
    yield
    mode_policy.reset_cache_for_tests()


# ── Derivation: the chip row comes from the data ───────────────────────────


def test_states_use_the_three_words_and_no_others() -> None:
    """One word per concept: allows / asks / blocked — in the UI, the config
    keys and the docs, identically."""
    assert mode_policy.STATES == ("allows", "asks", "blocked")


def test_every_group_state_is_derived_from_the_real_policy() -> None:
    for mode in mode_policy.UI_MODES:
        for gid, _label, _detail, tools in mode_policy.TOOL_GROUPS:
            state = mode_policy.default_state(mode, gid)
            if not tools:
                assert state == "allows", "conversation is the turn itself"
                continue
            in_mode = tools & MODE_TOOL_MAP[mode]
            if not in_mode:
                assert state == "blocked", (mode, gid)
            elif in_mode & APPROVAL_REQUIRED:
                assert state == "asks", (mode, gid)
            else:
                assert state == "allows", (mode, gid)


def test_presentation_blocks_mail_and_dev_tools() -> None:
    """The stage promise: Present cannot touch mail or the desktop."""
    assert mode_policy.default_state("presentation", "mail") == "blocked"
    assert mode_policy.default_state("presentation", "dev tools") == "blocked"
    assert mode_policy.default_state("presentation", "slides") == "allows"


def test_home_has_no_mail_at_all() -> None:
    """The real home mode carries no mail tools — the chip must say blocked,
    whatever a design mock-up wished it said."""
    assert mode_policy.default_state("home", "mail") == "blocked"


# ── Overrides: the Modes editor changes enforcement ────────────────────────


def test_an_override_takes_effect_in_the_allowed_tool_set() -> None:
    router = IntentRouter(mode="home")
    assert "send_mail" not in router.allowed_tools()

    mode_policy.set_group_state("home", "mail", "asks")

    assert "send_mail" in router.allowed_tools(), "the row change is live"
    assert mode_policy.requires_approval("send_mail", "home") is True


def test_blocking_a_group_removes_its_tools() -> None:
    router = IntentRouter(mode="work")
    assert "send_mail" in router.allowed_tools()

    mode_policy.set_group_state("work", "mail", "blocked")

    assert "send_mail" not in router.allowed_tools()
    assert "get_unread_mail" not in router.allowed_tools()


def test_allows_drops_the_gate_for_that_mode_only() -> None:
    """Setting a group to `allows` is an explicit owner decision to run it
    without asking — in that mode. Other modes keep their gate."""
    mode_policy.set_group_state("work", "mail", "allows")

    assert mode_policy.requires_approval("send_mail", "work") is False
    assert mode_policy.requires_approval("send_mail", "demo") is True, \
        "demo mode still uses the baseline APPROVAL_REQUIRED"


def test_a_derived_asks_summary_changes_nothing() -> None:
    """The default chip is a SUMMARY of the baseline, not a new rule: a group
    reading `asks` because send_mail asks must not suddenly gate its reads.
    (The whole shipping test-suite hangs on approval timeouts otherwise —
    which is how this rule earned its own test.)"""
    assert mode_policy.group_state("work", "mail") == ("asks", "default")
    assert mode_policy.requires_approval("get_unread_mail", "work") is False
    assert mode_policy.requires_approval("send_mail", "work") is True


def test_an_override_to_asks_gates_the_whole_group() -> None:
    """An explicit owner decision has teeth: every tool in the group stops."""
    mode_policy.set_group_state("work", "mail", "asks")
    assert mode_policy.requires_approval("get_unread_mail", "work") is True


def test_reset_to_default_removes_the_override(tmp_path) -> None:
    mode_policy.set_group_state("work", "mail", "blocked")
    assert mode_policy.group_state("work", "mail") == ("blocked", "override")

    mode_policy.set_group_state("work", "mail", "default")

    default = mode_policy.default_state("work", "mail")
    assert mode_policy.group_state("work", "mail") == (default, "default")
    stored = json.loads((tmp_path / "mode-policy.json").read_text())
    assert stored["overrides"] == {}, "reset leaves no residue"


def test_an_explicit_choice_sticks_even_when_it_matches_the_summary() -> None:
    """A derived `asks` means "part of this group asks"; an owner-set `asks`
    gates the whole group. The click is not a no-op."""
    assert mode_policy.group_state("work", "mail") == ("asks", "default")
    mode_policy.set_group_state("work", "mail", "asks")
    assert mode_policy.group_state("work", "mail") == ("asks", "override")


def test_ungrouped_tools_can_never_be_loosened() -> None:
    """save_skill / request_capability belong to no group — the Modes view
    must not be a path around their baseline gate."""
    assert mode_policy.requires_approval("save_skill", "work") is True
    assert mode_policy.requires_approval("request_capability", "home") is True


def test_conversation_cannot_be_bounded() -> None:
    with pytest.raises(ValueError):
        mode_policy.set_group_state("home", "conversation", "blocked")


def test_unknown_mode_group_and_state_are_refused() -> None:
    for bad in (("hotel", "mail", "asks"), ("home", "magic", "asks"), ("home", "mail", "maybe")):
        with pytest.raises(ValueError):
            mode_policy.set_group_state(*bad)


def test_overrides_survive_a_reload(tmp_path) -> None:
    mode_policy.set_group_state("home", "mail", "asks")
    mode_policy.reset_cache_for_tests()
    assert mode_policy.group_state("home", "mail") == ("asks", "override")


# ── The approval card names its rule ───────────────────────────────────────


def test_the_rule_sentence_names_mode_and_group() -> None:
    sentence = mode_policy.rule_for("send_mail", "work")
    assert "Work mode" in sentence
    assert "mail" in sentence.lower()


def test_an_owner_override_reads_as_their_decision() -> None:
    mode_policy.set_group_state("home", "mail", "asks")
    assert mode_policy.rule_for("send_mail", "home").startswith("You set")


def test_present_mode_uses_its_ui_name() -> None:
    assert "Present mode" in mode_policy.rule_for("send_mail", "presentation")


# ── Per-mode behaviour (was env-only) ──────────────────────────────────────


def test_behaviour_defaults_are_complete() -> None:
    for mode in mode_policy.UI_MODES:
        b = mode_policy.behaviour(mode)
        assert set(b) == {"persona", "voice", "speaks_first", "memory_writing"}


def test_setting_a_voice_is_stored_and_live(monkeypatch) -> None:
    monkeypatch.delenv("TTS_VOICE_WORK", raising=False)
    mode_policy.set_behaviour("work", {"voice": "onyx"})
    assert mode_policy.behaviour("work")["voice"] == "onyx"
    assert os.environ["TTS_VOICE_WORK"] == "onyx", "the TTS layer reads env — keep it true"


def test_stored_voices_reapply_on_boot(monkeypatch) -> None:
    mode_policy.set_behaviour("home", {"voice": "nova"})
    monkeypatch.delenv("TTS_VOICE_HOME", raising=False)
    mode_policy.reset_cache_for_tests()
    mode_policy.apply_stored_voices()
    assert os.environ["TTS_VOICE_HOME"] == "nova"


def test_legacy_env_voice_still_honoured(monkeypatch) -> None:
    """Nothing regresses: an install that set TTS_VOICE_WORK by hand keeps
    its voice until the editor writes one."""
    monkeypatch.setenv("TTS_VOICE_WORK", "fable")
    assert mode_policy.behaviour("work")["voice"] == "fable"


# ── The full description the console renders ───────────────────────────────


def test_describe_covers_the_three_ui_modes_with_sources() -> None:
    d = mode_policy.describe("home")
    assert d["active_mode"] == "home"
    assert set(d["modes"]) == {"home", "work", "presentation"}
    groups = d["modes"]["home"]["groups"]
    assert [g["id"] for g in groups] == [g[0] for g in mode_policy.TOOL_GROUPS]
    assert all(g["state"] in mode_policy.STATES for g in groups)
    assert all(g["source"] in ("default", "override") for g in groups)


# ---------------------------------------------------------------------------
# U254: a connection that is live changes what he may do
# ---------------------------------------------------------------------------


def test_without_a_mail_connector_he_is_not_offered_mail_tools() -> None:
    """"deze kunnen nog niet door robot gebruikt worden" — the other half of
    that sentence. A mode may allow mail, but with no mail account behind it
    there is nothing to allow, and offering the tool means promising to read
    mail and then explaining a 503 (U248, one layer down)."""
    mode_policy.set_live_domains({"calendar"})          # calendar only
    tools = mode_policy.allowed_tools("work")
    assert "get_unread_mail" not in tools
    assert "send_mail" not in tools
    assert "list_calendar_events_today" in tools


def test_switching_the_account_on_gives_the_tools_back() -> None:
    """The point of the whole unit: connecting an account has to change what
    he can do, not just what a badge says."""
    mode_policy.set_live_domains({"calendar"})
    assert "get_unread_mail" not in mode_policy.allowed_tools("work")

    mode_policy.set_live_domains({"calendar", "mail"})
    assert "get_unread_mail" in mode_policy.allowed_tools("work")


def test_local_things_never_depend_on_an_account() -> None:
    """Todos and reminders are memory-service, on this laptop. Gating those on
    a Microsoft account would break the part that works with no account at all.
    """
    mode_policy.set_live_domains(set())                 # nothing connected
    tools = mode_policy.allowed_tools("home")
    assert "create_reminder" in tools
    assert "list_todos" in tools


def test_not_knowing_takes_nothing_away() -> None:
    """Same rule as the derived mode states (U252): a layer that is unsure must
    not remove capabilities. Only the brain can say, and until it does the
    behaviour is exactly what it was before connections were modelled."""
    mode_policy.set_live_domains(None)
    assert "get_unread_mail" in mode_policy.allowed_tools("work")


def test_an_owner_override_cannot_conjure_an_account() -> None:
    """Allowing the mail group in a mode does not create a mailbox; the
    subtraction is deliberately last."""
    mode_policy.set_group_state("home", "mail", "allows")
    mode_policy.set_live_domains(set())
    assert "get_unread_mail" not in mode_policy.allowed_tools("home")
