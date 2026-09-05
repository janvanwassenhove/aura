"""U316: three agent files, one working agreement, no drift.

Both halves of this have already failed. `CLAUDE.md` did not exist for 292
units, so Claude Code never saw the constitution's first principle. And
`.github/copilot-instructions.md` described a "Cognitive Hub" with five
directories that do not exist here and never mentioned AURA — so Copilot was
reading instructions for a different project.

Keeping three files in step by hand is the same bet that lost twice. These
tests make the copies checkable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_agent_docs import SOURCE, TARGETS, rewrite, shared_text, sync  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_the_three_agent_files_are_in_step() -> None:
    """The check itself, over the real tree — this is the point."""
    stale = sync(ROOT, check=True)
    assert not stale, (
        f"out of date: {stale}. Edit {SOURCE} and run "
        "python scripts/sync_agent_docs.py")


def test_every_tool_gets_a_file_under_the_name_it_reads() -> None:
    assert "CLAUDE.md" in TARGETS, "Claude Code reads this one"
    assert ".github/copilot-instructions.md" in TARGETS, "Copilot reads this one"
    assert "AGENTS.md" in TARGETS, "the cross-tool default"
    for name in TARGETS:
        assert (ROOT / name).is_file(), name


def test_the_shared_block_carries_the_rule_that_was_missed() -> None:
    shared = shared_text(ROOT)
    assert "Specs are living artifacts" in shared
    assert "units:" in shared, "how a unit claims a spec"
    assert "spec_drift.py" in shared, "and how that is checked"


def test_copilot_instructions_describe_this_repository() -> None:
    """The regression this unit exists for: the file described another project
    entirely — a "Cognitive Hub" whose five directory trees do not exist here.

    Asserting a phrase is *absent* would be the wrong test, because the file now
    explains that history on purpose. What must hold is that the map it gives
    Copilot is real: every path in the project-map table exists."""
    import re

    text = (ROOT / ".github/copilot-instructions.md").read_text(encoding="utf-8")
    assert "AURA" in text

    # The project map only — the Spec Kit table above it holds slash commands,
    # which are not paths.
    start = text.index("## Project map")
    table = text[start:text.index("\n## ", start + 1)]
    rows = re.findall(r"^\| `([^`]+)` \|", table, re.M)
    assert len(rows) >= 10, "the project map should not have shrunk to nothing"
    missing = [r for r in rows if not (ROOT / r.rstrip("/")).exists()]
    assert not missing, f"the map points at paths that do not exist: {missing}"


def test_path_scoped_instructions_point_at_paths_that_exist() -> None:
    import re
    for p in (ROOT / ".github/instructions").glob("*.instructions.md"):
        m = re.search(r"^applyTo:\s*[\"']?(.+?)[\"']?\s*$",
                      p.read_text(encoding="utf-8"), re.M)
        assert m, f"{p.name}: no applyTo"
        for glob in m.group(1).split(","):
            root_dir = glob.strip().strip("\"'").split("/")[0].split("*")[0]
            if root_dir:
                assert (ROOT / root_dir).exists(), (
                    f"{p.name} applies to {glob.strip()}, which does not exist")


def test_rewrite_replaces_only_the_generated_block() -> None:
    text = ("keep me\n"
            "<!-- BEGIN GENERATED: working-agreement -->\nold\n"
            "<!-- END GENERATED -->\nkeep me too\n")
    out = rewrite(text, "new")
    assert "keep me" in out and "keep me too" in out
    assert "old" not in out
    assert "new" in out


def test_a_target_without_the_markers_is_an_error() -> None:
    import pytest
    with pytest.raises(SystemExit):
        rewrite("no markers here", "new")
