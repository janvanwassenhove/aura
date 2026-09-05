"""U315: the link checker, and what it is for.

Five paths in `AGENTS.md`'s "Key Interfaces" block pointed at files that had
never existed — including `RobotAdapter`, the contract the constitution names
as non-negotiable. Twenty-four links across the specs resolved to nothing,
because they were written relative to the repository root while Markdown
resolves them relative to the file. None of it failed anything. The reader
finds out by clicking, and mostly nobody clicks.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_doc_links import broken, links_in, markdown_files, resolve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_the_documentation_has_no_broken_links() -> None:
    """The check itself, run over the real tree — this is the point."""
    bad = broken(ROOT)
    assert not bad, "\n".join(f"{p.as_posix()} -> {t}" for p, t in bad)


def test_absolute_urls_are_not_our_problem() -> None:
    """A network call in CI is a flake, not a check."""
    assert links_in("[a](https://example.com) [b](http://x) [c](mailto:a@b)") == []


def test_a_relative_link_is_read() -> None:
    assert links_in("see [the spec](../015/spec.md)") == ["../015/spec.md"]


def test_an_image_counts_too() -> None:
    assert links_in("![alt](../diagrams/one-turn.svg)") == ["../diagrams/one-turn.svg"]


def test_an_anchor_on_a_file_still_checks_the_file() -> None:
    src = ROOT / "docs" / "adr" / "README.md"
    assert resolve(src, "ADR-001-language-choice.md#context", ROOT).exists()


def test_a_bare_anchor_is_in_page_and_ignored() -> None:
    assert links_in("[top](#context)") == []


def test_a_link_with_a_title_is_read() -> None:
    assert links_in('[a](./x.md "the title")') == ["./x.md"]


def test_it_looks_at_the_files_that_matter() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in markdown_files(ROOT)}
    assert "README.md" in names
    assert "CLAUDE.md" in names
    assert "AGENTS.md" in names
    assert ".specify/memory/constitution.md" in names
    assert any(n.startswith("docs/adr/") for n in names)
    # Vendored and generated trees are not ours to keep true.
    assert not any("node_modules" in n or "win-unpacked" in n for n in names)
