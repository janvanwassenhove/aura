"""U297: the README's pictures come from the demo stack, not from a hand.

They were captured by hand in August and had been four months out of date on
the front page of the repository. Nothing could have noticed: a stale image
still renders. The fix is that the same script the release page uses now
produces them, so "retake the screenshots" is a command rather than an
afternoon — and this pins the one rule that connects the two halves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from readme_shots import convert, target_name  # noqa: E402

PIL = pytest.importorskip("PIL")


def test_the_number_is_ordering_not_identity() -> None:
    """The release page wants an order; the README wants a name."""
    assert target_name(Path("shots/03-knowledge-graph.png")) == "knowledge-graph.webp"
    assert target_name(Path("shots/01-console.png")) == "console.webp"


def test_a_name_without_a_number_survives_intact() -> None:
    assert target_name(Path("shots/console.png")) == "console.webp"


def test_only_the_leading_number_is_stripped() -> None:
    """"06-robot-offline" keeps every dash that is part of its name."""
    assert target_name(Path("06-robot-offline.png")) == "robot-offline.webp"


def test_it_writes_one_webp_per_png(tmp_path: Path) -> None:
    from PIL import Image

    shots, out = tmp_path / "shots", tmp_path / "docs"
    shots.mkdir()
    out.mkdir()
    for name in ("01-console.png", "02-brain-person.png"):
        Image.new("RGB", (160, 100), "white").save(shots / name)

    written = convert(shots, out)

    assert [n for n, _ in written] == ["console.webp", "brain-person.webp"]
    assert (out / "console.webp").exists()
    assert all(size > 0 for _, size in written)


def test_every_readme_image_actually_exists() -> None:
    """A renamed shot must not leave the front page with a broken picture."""
    import re

    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    for src in re.findall(r'src="(docs/screenshots/[^"]+)"', readme):
        assert (root / src).is_file(), src
