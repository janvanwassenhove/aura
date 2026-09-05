"""U299: the check that would have caught sixty-nine units of silent drift.

Asked as "waarom zie ik in specify en docs folder geen wijzigingen?" — a fair
question with an uncomfortable answer: nothing anywhere connected a shipped
unit to the specification it changed, so the connection was only ever a habit,
and habits do not survive sixty-nine units at speed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_drift import claimed_units, drift, report, shipped_units  # noqa: E402

LOG = (
    "auto(U298): no, an app ID is not the only way\n"
    "auto(U297): the README screenshots were of the previous app\n"
    "docs: a drawing\n"
    "auto(U296): the teach button did nothing\n"
)


def test_units_are_read_from_the_commit_log_oldest_first() -> None:
    assert shipped_units(LOG) == ["U296", "U297", "U298"]


def test_a_letter_suffix_is_its_own_unit() -> None:
    """U242b was a real change with real consequences; folding it into U242
    would hide one of them."""
    assert shipped_units("auto(U242b): pin line endings\n") == ["U242b"]


def test_commits_that_are_not_units_are_ignored() -> None:
    assert shipped_units("chore: bump\nMerge branch 'master'\n") == []


def test_a_spec_claims_units_from_an_inline_list() -> None:
    assert claimed_units('---\nunits: [U263, U264]\nstatus: "done"\n---\n# Spec\n') == {
        "U263", "U264"}


def test_a_spec_claims_units_from_a_block_list() -> None:
    spec = "---\nfeature: x\nunits:\n  - U263\n  - U264\nowner: me\n---\n"
    assert claimed_units(spec) == {"U263", "U264"}


def test_the_next_key_ends_the_block() -> None:
    """`owner` is not a unit, and neither is anything after it."""
    spec = "---\nunits:\n  - U263\nowner: U999-not-a-unit\n---\n"
    assert claimed_units(spec) == {"U263"}


def test_merely_mentioning_a_unit_in_the_prose_claims_nothing() -> None:
    """A spec that name-drops U263 in a paragraph has not taken responsibility
    for it — that is exactly the kind of "documented" this check exists to
    stop counting."""
    spec = '---\nfeature: x\n---\n\nThis replaces the behaviour from U263.\n'
    assert claimed_units(spec) == set()


def test_a_spec_without_frontmatter_claims_nothing() -> None:
    assert claimed_units("# Feature Specification\n\nunits: U263\n") == set()


def test_drift_is_what_nobody_claimed() -> None:
    assert drift(["U296", "U297", "U298"], {"a": {"U297"}, "b": {"U296"}}) == ["U298"]


def test_no_specs_at_all_means_everything_is_drift() -> None:
    assert drift(["U1", "U2"], {}) == ["U1", "U2"]


def test_the_report_names_the_units_and_the_fix() -> None:
    text = " ".join(report(["U298"], {"a": {"U297"}}).split())
    assert "U298" in text
    assert "units:" in text, "it has to say HOW to fix it, not just that it is broken"
    assert "living artifacts" in text, "and WHY, in the constitution's own words"


def test_a_clean_report_counts_what_is_covered() -> None:
    text = report([], {"a": {"U1", "U2"}, "b": {"U3"}})
    assert "complete" in text
    assert "3 units" in text


# ── The baseline: an honest boundary, and a one-way one ────────────────────

def test_the_baseline_separates_old_debt_from_new_drift() -> None:
    from spec_drift import split_at
    debt, fresh = split_at(["U1", "U2", "U3", "U4"], "U2")
    assert debt == ["U1", "U2"]
    assert fresh == ["U3", "U4"]


def test_no_baseline_forgives_nothing() -> None:
    from spec_drift import split_at
    assert split_at(["U1", "U2"], "") == ([], ["U1", "U2"])


def test_a_baseline_that_has_not_landed_yet_fails_nothing() -> None:
    """The unit that SETS the baseline is not in the log while it is being
    written. Nothing can be newer than it, so there is no new drift — and one
    commit later the answer is identical."""
    from spec_drift import split_at
    assert split_at(["U1", "U2"], "U299") == (["U1", "U2"], [])


def test_the_baseline_only_ever_moves_backwards() -> None:
    """The whole point. Moving it forward would "fix" drift by declaring it
    forgiven, which is the failure this check exists to make impossible."""
    import json
    import subprocess

    root = Path(__file__).resolve().parent.parent
    path = root / ".specify" / "coverage.json"
    now = int(json.loads(path.read_text(encoding="utf-8"))["baseline"].lstrip("U")
              .rstrip("abcdefghijklmnopqrstuvwxyz"))

    was = subprocess.run(                                          # noqa: S603
        ["git", "show", "HEAD:.specify/coverage.json"],           # noqa: S607
        cwd=root, capture_output=True, text=True, check=False,
    ).stdout
    if not was.strip():
        return  # first commit of the file — nothing to compare against
    before = int(json.loads(was)["baseline"].lstrip("U")
                 .rstrip("abcdefghijklmnopqrstuvwxyz"))
    assert now <= before, (
        f"the baseline moved forward (U{before} → U{now}): that forgives drift "
        "instead of documenting it")


# ── U300: the early history batched units into one commit ──────────────────

def test_a_batched_subject_names_every_unit_in_it() -> None:
    """`auto(U2,U3):` and `auto(U19c+U20):` are two units each. A checker that
    counted one would under-report its OWN debt, which is the single thing it
    must never do."""
    from spec_drift import units_in
    assert units_in("U2,U3") == ["U2", "U3"]
    assert units_in("U19c+U20") == ["U19c", "U20"]
    assert units_in("U252e+U253b") == ["U252e", "U253b"]


def test_a_range_means_every_unit_in_it() -> None:
    """`auto(U112-U115):` was shorthand for a run of four."""
    from spec_drift import units_in
    assert units_in("U112-U115") == ["U112", "U113", "U114", "U115"]


def test_bookkeeping_suffixes_are_not_units() -> None:
    from spec_drift import units_in
    assert units_in("U168-ledger") == ["U168"]


def test_a_nonsense_range_does_not_explode() -> None:
    from spec_drift import units_in
    assert units_in("U300-U1") == ["U300", "U1"]     # backwards: taken literally
    assert units_in("U1-U9999") == ["U1", "U9999"]   # absurd: not expanded
