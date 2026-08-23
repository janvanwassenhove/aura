"""U259: he can look things up now — and says so when he cannot.

Reported after AURA answered a question about match dates with "check the
hockey federation's website". That was not evasion: there was no search tool,
no way to read a page, and the research subagent's toolset was entirely local.

The owner asked for it to work "zoals claude chat" — always available — with
the provider's own search first, an MCP search server second, and their own
browser as the last resort.
"""

from __future__ import annotations

import pytest
from orchestrator import mode_policy, web_search


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MODE_POLICY_PATH", str(tmp_path / "policy.json"))
    monkeypatch.setenv("MCP_SERVERS_PATH", str(tmp_path / "mcp.json"))
    monkeypatch.delenv("WEB_SEARCH_BACKENDS", raising=False)
    mode_policy.reset_cache_for_tests()
    yield
    mode_policy.reset_cache_for_tests()


def _backends(monkeypatch, **impls) -> list[str]:
    """Replace the backend chain with fakes; record the order they are tried."""
    called: list[str] = []

    def wrap(name, fn):
        async def _inner(query):
            called.append(name)
            return await fn(query)
        return _inner

    for name, fn in impls.items():
        monkeypatch.setattr(web_search, f"_via_{name}", wrap(name, fn))
    return called


async def _ok(text):
    async def _f(_q):
        return text
    return _f


async def _dead(message):
    async def _f(_q):
        raise RuntimeError(message)
    return _f


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


async def test_the_provider_is_asked_first(monkeypatch) -> None:
    """Search follows LLM_PROVIDER so there is no second provider setting to
    drift out of sync with the first."""
    called = _backends(
        monkeypatch,
        provider=await _ok("Red Panthers play on 14 September."),
        mcp=await _dead("should not be reached"),
        browser=await _dead("should not be reached"),
    )
    result = await web_search.search("when do the red panthers play")
    assert result.backend == "provider"
    assert called == ["provider"]
    assert "14 September" in result.text


async def test_it_falls_through_to_the_next_backend(monkeypatch) -> None:
    """The whole point of a chain: one dead backend must not mean no answer."""
    called = _backends(
        monkeypatch,
        provider=await _dead("no OpenAI key"),
        mcp=await _ok("from the search server"),
        browser=await _dead("should not be reached"),
    )
    result = await web_search.search("hockey")
    assert result.backend == "mcp"
    assert called == ["provider", "mcp"]


async def test_the_browser_is_the_last_resort(monkeypatch) -> None:
    called = _backends(
        monkeypatch,
        provider=await _dead("offline"),
        mcp=await _dead("no MCP search tool"),
        browser=await _ok("I opened the results in your browser: https://…"),
    )
    result = await web_search.search("hockey")
    assert result.backend == "browser"
    assert called == ["provider", "mcp", "browser"]


async def test_an_empty_answer_is_not_treated_as_an_answer(monkeypatch) -> None:
    """A backend that returns "" has not answered; the chain must continue."""
    _backends(
        monkeypatch,
        provider=await _ok("   "),
        mcp=await _ok("the real answer"),
        browser=await _dead("unused"),
    )
    result = await web_search.search("hockey")
    assert result.backend == "mcp"


# ---------------------------------------------------------------------------
# Saying which kind of nothing it was
# ---------------------------------------------------------------------------


async def test_a_failed_lookup_never_reads_as_found_nothing(monkeypatch) -> None:
    """These need very different reactions, and only one of them is honest
    about the assistant's own limits. "I found nothing" when the network was
    down is the same class of lie as U248's "I'll open Chrome now"."""
    _backends(
        monkeypatch,
        provider=await _dead("no OpenAI key"),
        mcp=await _dead("no enabled MCP server offers a search tool"),
        browser=await _dead("Chrome is not running"),
    )
    result = await web_search.search("hockey")

    assert result.ok is False
    text = result.for_model()
    assert "NOT the same as finding nothing" in text
    assert "no OpenAI key" in text          # every reason travels with it
    assert "Chrome is not running" in text


async def test_a_good_answer_says_where_it_came_from(monkeypatch) -> None:
    _backends(monkeypatch, provider=await _ok("42"))
    result = await web_search.search("x")
    assert "searched the web via provider" in result.for_model()


async def test_an_empty_query_is_refused_without_a_round_trip(monkeypatch) -> None:
    called = _backends(monkeypatch, provider=await _ok("should not run"))
    result = await web_search.search("   ")
    assert result.ok is False
    assert called == []


# ---------------------------------------------------------------------------
# Reading a page
# ---------------------------------------------------------------------------


async def test_reading_refuses_anything_but_http() -> None:
    assert "only http(s)" in await web_search.read_url("file:///etc/passwd")


async def test_reading_refuses_the_local_network() -> None:
    """A tool the model can aim is a tool that can be aimed at the router's
    admin page — or a cloud metadata endpoint — by anything that manages to put
    a URL in front of it."""
    out = await web_search.read_url("http://127.0.0.1:8020/setup/prefs")
    assert "local network" in out


def test_html_becomes_readable_text() -> None:
    html = """<html><head><style>p{color:red}</style></head>
    <body><nav>menu</nav><h1>Red Panthers</h1>
    <p>Next match &amp; venue: 14 Sept</p><script>evil()</script></body></html>"""
    text = web_search._to_text(html)
    assert "Red Panthers" in text
    assert "Next match & venue: 14 Sept" in text
    assert "evil()" not in text and "color:red" not in text


# ---------------------------------------------------------------------------
# The boundary the owner asked for
# ---------------------------------------------------------------------------


def test_he_can_always_look_things_up() -> None:
    """"opzoeken zou hij steeds moeten kunnen" — in every mode, including a
    presentation, where being unable to check a fact is most embarrassing."""
    for mode in mode_policy.UI_MODES:
        assert "web_search" in mode_policy.allowed_tools(mode), mode
        assert "read_url" in mode_policy.allowed_tools(mode), mode


def test_only_work_stops_to_ask() -> None:
    """A work query can carry something confidential out of the house."""
    assert mode_policy.requires_approval("web_search", "work") is True
    assert mode_policy.requires_approval("web_search", "home") is False
    assert mode_policy.requires_approval("web_search", "presentation") is False


def test_the_owner_can_still_overrule_that() -> None:
    """The per-mode rule is a default, not a decision taken away from them."""
    mode_policy.set_group_state("work", "web", "allows")
    assert mode_policy.requires_approval("web_search", "work") is False


def test_blocking_the_group_really_blocks_it() -> None:
    mode_policy.set_group_state("home", "web", "blocked")
    assert "web_search" not in mode_policy.allowed_tools("home")


# ---------------------------------------------------------------------------
# U259b: model names move, including their version
# ---------------------------------------------------------------------------


def test_a_newer_generation_wins_without_anyone_editing_this_file() -> None:
    """The owner's point: "modellen veranderen, ook in versie".

    A hand-kept list rots. Ranking by what the NAME says means a model nobody
    has written down yet is preferred the day it appears.
    """
    today = ["gpt-4o-search-preview", "gpt-4o-mini-search-preview",
             "gpt-5-search-api"]
    assert web_search.rank_search_models(today)[0] == "gpt-5-search-api"

    tomorrow = [*today, "gpt-6-search-api"]
    assert web_search.rank_search_models(tomorrow)[0] == "gpt-6-search-api"


def test_a_dated_snapshot_never_outranks_its_own_alias() -> None:
    """First attempt got this backwards: the date was read as the version, so
    "gpt-5-search-api-2025-10-14" looked like version 2025 and every snapshot
    beat every alias. The alias is what tracks the current model."""
    ranked = web_search.rank_search_models(
        ["gpt-5-search-api-2025-10-14", "gpt-5-search-api"])
    assert ranked == ["gpt-5-search-api", "gpt-5-search-api-2025-10-14"]


def test_the_full_model_is_preferred_over_its_mini() -> None:
    ranked = web_search.rank_search_models(
        ["gpt-5-mini-search-api", "gpt-5-search-api"])
    assert ranked[0] == "gpt-5-search-api"


def test_deep_research_is_never_chosen_by_itself() -> None:
    """It can search, but it costs minutes and euros. Reaching for one to
    answer "when do the Red Panthers play" is out of all proportion."""
    ranked = web_search.rank_search_models(
        ["o3-deep-research", "gpt-4o-search-preview"])
    assert ranked == ["gpt-4o-search-preview"]


async def test_what_worked_is_tried_first_next_time(monkeypatch) -> None:
    """Otherwise every search pays a listing call and two failures."""
    monkeypatch.setattr(web_search, "_working", {"openai": "the-good-one"})
    monkeypatch.setattr(web_search, "_discovered", {})

    async def _fake_discover(_p):
        return ["something-else"]
    monkeypatch.setattr(web_search, "_discover", _fake_discover)

    assert (await web_search._candidates("openai"))[0] == "the-good-one"


async def test_a_retired_model_is_forgotten_so_the_next_one_is_found(monkeypatch) -> None:
    """The scenario the owner described: what worked yesterday 404s today.
    Forgetting it also drops the cached listing — a model disappearing IS the
    signal that the provider moved."""
    monkeypatch.setattr(web_search, "_working", {"openai": "retired-model"})
    monkeypatch.setattr(web_search, "_discovered", {"openai": (["x"], 0.0)})

    web_search._forget("retired-model", "openai")

    assert "openai" not in web_search._working
    assert "openai" not in web_search._discovered   # re-list, do not wait an hour


async def test_the_owners_explicit_choice_still_comes_first(monkeypatch) -> None:
    monkeypatch.setattr(web_search, "_working", {})
    monkeypatch.setenv("WEB_SEARCH_MODEL_OPENAI", "my-model")

    async def _fake_discover(_p):
        return ["discovered-one"]
    monkeypatch.setattr(web_search, "_discover", _fake_discover)

    assert (await web_search._candidates("openai"))[0] == "my-model"


async def test_discovery_failing_falls_back_to_the_seeds(monkeypatch) -> None:
    """No network, no listing — search must still have something to try."""
    monkeypatch.setattr(web_search, "_working", {})
    monkeypatch.delenv("WEB_SEARCH_MODEL_OPENAI", raising=False)

    async def _no_discovery(_p):
        return []
    monkeypatch.setattr(web_search, "_discover", _no_discovery)

    assert "gpt-5-search-api" in await web_search._candidates("openai")
