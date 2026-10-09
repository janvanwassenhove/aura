#!/usr/bin/env python3
"""U315: every relative link in the documentation points at something.

The specs, the ADRs and the constitution now cross-reference each other heavily
— that is what makes them navigable, and it is also what makes them rot. A
renamed spec folder or a moved ADR leaves a link that still *looks* like a
link, and the reader finds out by clicking. A stale reference is worse than no
reference, for the same reason constitution IX gives about diagrams: it is
believed.

Checked: relative Markdown links and images, and HTML `<img src>`, in the
documentation tree. Not
checked: `http(s)` URLs (a network call in CI is a flake, not a check) and
anchors within a file.

    python scripts/check_doc_links.py            # report, exit 1 on a break
    python scripts/check_doc_links.py --quiet    # silent when clean
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

#: `[text](target)` and `![alt](target)`. Targets with spaces are wrapped in
#: <>, which Markdown allows and which several diagram links use.
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")

#: `<img src="...">` — the README's hero and screenshots are HTML, which the
#: Markdown pattern never saw (U411). Either quote, any attribute order.
_IMG = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

#: Code is not a link — it never renders as one. Fenced blocks first, then
#: inline spans (double backticks before single). U411b: a spec quoting
#: `<img src="...">` was read as a link to "...".
_FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
_INLINE_CODE = re.compile(r"``[^`]*?``|`[^`\n]*`")


def _without_code(text: str) -> str:
    return _INLINE_CODE.sub(" ", _FENCE.sub(" ", text))

#: Where documentation lives. `.github/` is included because the instruction
#: files link into docs, and those are the ones an agent follows.
_ROOTS = (".specify", "docs", ".github")
_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md")

_SKIP_PREFIX = ("http://", "https://", "mailto:", "#", "tel:")

#: Generated or vendored trees that are not ours to keep true.
_EXCLUDE = ("node_modules", "dist", "win-unpacked", "docs/method",
            ".github/apm", "design_handoff")


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def markdown_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for name in _FILES:
        if (root / name).is_file():
            out.append(root / name)
    for d in _ROOTS:
        for p in sorted((root / d).rglob("*.md")):
            rel = p.relative_to(root).as_posix()
            if not any(x in rel for x in _EXCLUDE):
                out.append(p)
    return out


def links_in(text: str) -> list[str]:
    """Relative link targets, in order. Absolute URLs and anchors dropped."""
    text = _without_code(text)
    found = sorted([(m.start(), m.group(1)) for m in _LINK.finditer(text)]
                   + [(m.start(), m.group(1)) for m in _IMG.finditer(text)])
    return [target for _, target in found if not target.startswith(_SKIP_PREFIX)]


def resolve(source: Path, target: str, root: Path) -> Path:
    """Where a link in `source` points. Anchors and queries stripped."""
    clean = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if clean.startswith("/"):
        return root / clean.lstrip("/")
    return (source.parent / clean).resolve()


def broken(root: Path) -> list[tuple[Path, str]]:
    """Every (file, target) whose target does not exist."""
    out: list[tuple[Path, str]] = []
    for md in markdown_files(root):
        text = md.read_text(encoding="utf-8", errors="replace")
        for target in links_in(text):
            if not target.split("#", 1)[0]:
                continue          # a bare anchor, in-page
            if _trimmed_by_windows(target) or not resolve(md, target, root).exists():
                out.append((md.relative_to(root), target))
    return out


def _trimmed_by_windows(target: str) -> bool:
    """A segment ending in a dot or a space (other than . and ..) exists on
    Windows — which trims it — and nowhere else. U411b: "..." passed here and
    failed on the runner; a link has to break the same way everywhere."""
    path = unquote(target.split("#", 1)[0].split("?", 1)[0])
    return any(seg not in (".", "..") and seg.endswith((".", " "))
               for seg in path.split("/") if seg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = _root()
    bad = broken(root)
    if bad:
        print(f"{len(bad)} broken documentation link(s):\n")
        for md, target in bad:
            print(f"  {md.as_posix()}  ->  {target}")
        print("\nA link that looks like a link and goes nowhere is worse than "
              "no link: the reader finds out by clicking.")
        return 1
    if not args.quiet:
        n = sum(len(links_in(p.read_text(encoding='utf-8', errors='replace')))
                for p in markdown_files(root))
        print(f"documentation links OK — {n} relative links across "
              f"{len(markdown_files(root))} files")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
