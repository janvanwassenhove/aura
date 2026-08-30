"""U284: the release notes must survive the ledger changing shape.

The old workflow scraped `- [x] **Title**`. Ledger entries have read
`- 2026-08-30 — U283 TITLE: body` for about a hundred units, so the "Nieuw in
deze release" section silently rendered nothing, release after release. A
changelog that quietly degrades to no changelog is worse than none: it still
looks maintained.

So the extraction is tested against BOTH generations, and the page is tested
for the things a reader needs: what changed, the screenshots, and how to
install it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_notes import compose, highlights  # noqa: E402

CURRENT = (
    "+- 2026-08-30 — U283 CI STOND ZES UUR ROOD: gemeld als iets.\n"
    "+- 2026-08-30 — U282 DE FOUT BIJ HET BEWAREN WAS EEN DUMP: gemeld met.\n"
)
LEGACY = "+- [x] **Quiet hours are real now** — the toggle lived in localStorage.\n"


def test_it_reads_the_ledger_format_actually_in_use() -> None:
    got = highlights(CURRENT)
    assert got == [
        "CI stond zes uur rood",
        "De fout bij het bewaren was een dump",
    ], "the current format is what every recent unit is written in"


def test_it_still_reads_the_old_format() -> None:
    """A release spanning the changeover must not lose half its history."""
    assert highlights(LEGACY) == ["Quiet hours are real now"]


def test_diff_noise_is_ignored() -> None:
    noise = "+++ b/docs/implementation-backlog.md\n-- 2026-01-01 — U1 REMOVED: x\n context\n"
    assert highlights(noise) == []


def test_a_title_written_as_prose_is_left_alone() -> None:
    """Only SHOUTED titles get lowercased; mixed case was deliberate."""
    line = "+- 2026-08-30 — U9 Quiet hours, and what they mean: body.\n"
    assert highlights(line) == ["Quiet hours, and what they mean"]


def test_duplicates_are_folded() -> None:
    assert len(highlights(CURRENT + CURRENT)) == 2


def test_the_page_leads_with_what_changed() -> None:
    page = compose("v1.2.3", "o/r", ["Hij hoort je nu"], ["home.png"])
    assert page.startswith("# AURA v1.2.3")
    assert "1 verbetering" in page, "say how much changed before listing it"
    assert "- Hij hoort je nu" in page


def test_screenshots_are_kept_and_credited() -> None:
    """Explicitly asked for: "behoud hierin ook zeker de screenshots"."""
    page = compose("v1.2.3", "o/r", [], ["home.png", "people.png"])
    assert "![home.png](https://github.com/o/r/releases/download/v1.2.3/home.png)" in page
    assert "![people.png](" in page
    assert "demoprofiel" in page, "and say no real person is in them"


def test_a_release_without_screenshots_says_so() -> None:
    """U235's rule: the capture job may fail without blocking a release, so
    when it does the page admits it rather than just looking thinner."""
    page = compose("v1.2.3", "o/r", ["iets"], [])
    assert "Geen schermafbeeldingen" in page


def test_a_release_with_no_units_is_still_honest() -> None:
    page = compose("v1.2.3", "o/r", [], ["a.png"])
    assert "onderhoudsrelease" in page
    assert "Wat er nieuw en beter is" not in page, "no empty section"


def test_every_platform_can_find_its_download() -> None:
    page = compose("v1.2.3", "o/r", [], [])
    for token in ("windows-setup.exe", "mac-arm64.dmg", "mac-x64.dmg", "AppImage"):
        assert token in page
    assert "blijven staan" in page, "an upgrader needs to know their data survives"


def test_acronyms_survive_the_shouting_being_removed() -> None:
    """The first version of this rendered "CI" as "Ci". An allowlist, not a
    length rule — "DE" and "OP" are two capitals too."""
    line = ("+- 2026-08-30 — U1 DE MCP-TOOLS EN DE TTS-SLEUTEL: body.\n"
            "+- 2026-08-30 — U2 CI STOND ROOD: body.\n")
    assert highlights(line) == [
        "De MCP-tools en de TTS-sleutel",
        "CI stond rood",
    ]


def test_a_title_containing_a_colon_is_not_cut_in_half() -> None:
    """U274's title is "PER PERSOON: IN WELKE TAAL, EN ALS WELK KARAKTER".
    The first version rendered it as "Per persoon", which says nothing."""
    line = ("+- 2026-08-30 — U274 PER PERSOON: IN WELKE TAAL, EN ALS WELK KARAKTER: "
            "gevraagd als iets.\n")
    assert highlights(line) == ["Per persoon: in welke taal, en als welk karakter"]
