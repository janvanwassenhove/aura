"""U285: the release page is English, and built from the commit log.

"release notes altijd in engels". U284's template was Dutch, and worse, its
bullets came from the ledger — which is Dutch prose no build step can
translate. Every unit already lands as exactly one commit with an English
subject, so the commit log IS the changelog: right language, right
granularity, nothing extra to keep in sync.

These tests also pin the shape a reader depends on: what changed, the
screenshots (explicitly asked to keep), and how to install it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_notes import compose, highlights  # noqa: E402

LOG = (
    "auto(U284): release notes a person wants to read\n"
    "auto(U283): CI was red for six hours while I reported green\n"
    "auto(U282): the scenario-save error was a raw Pydantic dump\n"
)


def test_the_bullets_come_from_the_commit_subjects() -> None:
    assert highlights(LOG) == [
        "Release notes a person wants to read",
        "CI was red for six hours while I reported green",
        "The scenario-save error was a raw Pydantic dump",
    ]


def test_the_unit_number_is_dropped() -> None:
    """"U284" means everything to us and nothing to somebody installing it."""
    assert "U284" not in " ".join(highlights(LOG))


def test_plumbing_commits_stay_off_the_page() -> None:
    noisy = ("chore: bump version\n"
             "Merge branch 'master'\n"
             "docs: fix a typo\n"
             "auto(U9): the thing that matters\n")
    assert highlights(noisy) == ["The thing that matters"]


def test_duplicates_are_folded() -> None:
    assert len(highlights(LOG + LOG)) == 3


def test_a_shouted_subject_stops_shouting_but_keeps_its_acronyms() -> None:
    """"CI" must not become "Ci" — an allowlist, not a length rule."""
    assert highlights("auto(U1): THE MCP-TOOLS AND THE TTS KEY\n") == [
        "The MCP-tools and the TTS key"]
    assert highlights("auto(U2): CI STOOD RED\n") == ["CI stood red"]


def test_a_very_long_release_is_capped() -> None:
    log = "".join(f"auto(U{i}): change number {i}\n" for i in range(60))
    assert len(highlights(log)) == 25


def test_the_page_is_english() -> None:
    page = compose("v1.2.3", "o/r", ["He hears you now"], ["home.png"])
    assert "What's new and better" in page
    assert "Getting started" in page
    # The Dutch template this replaces, gone for good.
    for dutch in ("Wat er nieuw", "Aan de slag", "Zo ziet het eruit", "Jouw systeem"):
        assert dutch not in page


def test_the_page_leads_with_how_much_changed() -> None:
    page = compose("v1.2.3", "o/r", ["He hears you now"], [])
    assert page.startswith("# AURA v1.2.3")
    assert "1 improvement" in page and "1 improvements" not in page
    assert "- He hears you now" in page


def test_screenshots_are_kept_and_credited() -> None:
    """Explicitly asked for in U284: "behoud hierin ook zeker de screenshots"."""
    page = compose("v1.2.3", "o/r", [], ["home.png", "people.png"])
    assert "![home.png](https://github.com/o/r/releases/download/v1.2.3/home.png)" in page
    assert "![people.png](" in page
    assert "demo profile" in page, "and say no real person is in them"


def test_a_release_without_screenshots_says_so() -> None:
    """U235's rule: the capture job may fail without blocking a release, so
    when it does the page admits it rather than just looking thinner."""
    assert "No screenshots" in compose("v1.2.3", "o/r", ["x"], [])


def test_a_release_with_no_units_is_still_honest() -> None:
    page = compose("v1.2.3", "o/r", [], ["a.png"])
    assert "maintenance release" in page
    assert "What's new and better" not in page, "no empty section"


def test_every_platform_can_find_its_download() -> None:
    page = compose("v1.2.3", "o/r", [], [])
    for token in ("windows-setup.exe", "mac-arm64.dmg", "mac-x64.dmg", "AppImage"):
        assert token in page
    assert "stay exactly as they are" in page, "an upgrader needs to know their data survives"
