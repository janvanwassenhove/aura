#!/usr/bin/env python3
"""U297: turn captured PNGs into the .webp files the README points at.

The README's pictures were taken by hand in August and had gone stale — the
app in them is four months older than the one you install. A screenshot that
can only be retaken by hand is a screenshot that rots quietly, so it now comes
from the same demo stack the release page uses: booted with the fake robot,
the echo LLM and one fictional persona, which is what makes these safe to
publish at all.

    python scripts/readme_shots.py --shots shots

`shots/03-knowledge-graph.png` becomes `docs/screenshots/knowledge-graph.webp`:
the number is only there to order the release page.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

#: Everything before the first dash is ordering, not identity.
_ORDER = re.compile(r"^\d+[-_]")

#: WebP quality. 82 is where these flat UI screenshots stop losing anything
#: visible — text edges stay crisp — while staying comfortably under the size
#: the hand-made files had.
_QUALITY = 82


def target_name(png: Path) -> str:
    return _ORDER.sub("", png.stem) + ".webp"


def convert(shots: Path, out: Path) -> list[tuple[str, int]]:
    """Write one .webp per PNG. Returns (name, bytes) for what was written."""
    written: list[tuple[str, int]] = []
    for png in sorted(shots.glob("*.png")):
        dest = out / target_name(png)
        with Image.open(png) as im:
            im.convert("RGB").save(dest, "WEBP", quality=_QUALITY, method=6)
        written.append((dest.name, dest.stat().st_size))
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="shots", help="directory of captured PNGs")
    ap.add_argument("--out", default="docs/screenshots")
    args = ap.parse_args(argv)

    shots, out = Path(args.shots), Path(args.out)
    if not shots.is_dir():
        print(f"no such directory: {shots}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)

    written = convert(shots, out)
    if not written:
        print(f"no PNGs in {shots} — nothing to update", file=sys.stderr)
        return 1
    for name, size in written:
        print(f"{out / name}  ({size // 1024} kB)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
