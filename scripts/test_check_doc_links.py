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


# U411: the README's hero and every screenshot are <img src="…"> tags — HTML,
# so the Markdown pattern never saw them. Renaming an image broke the front
# page of a public repository with every check green.

def test_an_html_image_counts_too() -> None:
    html = '<p align="center">\n  <img src="docs/talks/media/richie.webp" alt="x" width="560">\n</p>'
    assert links_in(html) == ["docs/talks/media/richie.webp"]


def test_an_html_image_with_single_quotes_and_attributes_first() -> None:
    assert links_in("<img alt='a robot' src='media/one-turn.gif'>") == ["media/one-turn.gif"]


def test_a_remote_html_image_is_not_our_problem() -> None:
    assert links_in('<img src="https://example.com/x.png">') == []


def test_a_broken_html_image_is_reported(tmp_path) -> None:
    (tmp_path / "README.md").write_text('<img src="docs/gone.webp" alt="gone">', encoding="utf-8")
    assert [t for _, t in broken(tmp_path)] == ["docs/gone.webp"]


# U411b: U411's own spec quoted the syntax — `<img src="...">` — and the checker
# read "..." as a link. Windows trims trailing dots from a path, so "..." was
# the folder and the check passed here; on the Linux runner it is nothing, and
# CI went red. Code is not a link: it never renders as one.

def test_an_image_quoted_in_inline_code_is_not_a_link() -> None:
    assert links_in('reads `<img src="...">` as well') == []


def test_a_markdown_link_quoted_in_inline_code_is_not_a_link() -> None:
    assert links_in("write it as `[text](target)`") == []


def test_links_in_a_fenced_block_are_not_links() -> None:
    text = "before\n```html\n<img src=\"nowhere.png\">\n[a](gone.md)\n```\nafter [b](here.md)"
    assert links_in(text) == ["here.md"]


def test_a_link_next_to_code_still_counts() -> None:
    assert links_in("run `x` and see [the spec](spec.md)") == ["spec.md"]


def test_a_name_windows_would_trim_is_broken_on_every_platform(tmp_path) -> None:
    """Windows drops trailing dots from a path, so "..." resolved to the folder
    and the check passed on the machine that wrote it — and failed on the
    runner. A link must break the same way everywhere."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("[x](...) [y](docs./) [z](docs/)", encoding="utf-8")
    assert sorted(t for _, t in broken(tmp_path)) == ["...", "docs./"]
