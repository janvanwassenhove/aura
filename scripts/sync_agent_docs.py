#!/usr/bin/env python3
"""U316: one working agreement, three files, no drift.

Three coding agents read three different filenames, and a rule in a file the
tool does not open is not a rule:

  * Claude Code           -> `CLAUDE.md`
  * GitHub Copilot        -> `.github/copilot-instructions.md`
  * the cross-tool default -> `AGENTS.md`

Both halves of that have already failed here. `CLAUDE.md` did not exist for 292
units, so every unit in the autobuild stream was written by an agent that had
never read the constitution's first principle (U299). And
`.github/copilot-instructions.md` described a *different repository* — a
"Cognitive Hub" with `.apm/`, `knowledge/`, `providers/` and `specs/`, none of
which exist here — so Copilot was reading instructions for a project that is not
this one (U316).

Keeping three files in step by hand is the same bet that lost twice already.
`docs/agent-working-agreement.md` is the source; everything between its
`BEGIN SHARED` / `END SHARED` markers is injected into each target between
`BEGIN GENERATED` / `END GENERATED` markers. Each file keeps its own
tool-specific framing around that block.

    python scripts/sync_agent_docs.py           # write the copies
    python scripts/sync_agent_docs.py --check   # fail if they have drifted
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SOURCE = "docs/agent-working-agreement.md"
TARGETS = ("CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md")

_SHARED = re.compile(r"<!-- BEGIN SHARED -->\n(.*?)\n<!-- END SHARED -->", re.S)
_BLOCK = re.compile(
    r"(<!-- BEGIN GENERATED: working-agreement[^>]*-->\n).*?(\n<!-- END GENERATED -->)",
    re.S)

_HEADER = ("<!-- BEGIN GENERATED: working-agreement — edit "
           "docs/agent-working-agreement.md, then run "
           "scripts/sync_agent_docs.py -->\n")
_FOOTER = "\n<!-- END GENERATED -->"


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def shared_text(root: Path) -> str:
    """The block every agent file must carry, from the one source."""
    m = _SHARED.search((root / SOURCE).read_text(encoding="utf-8"))
    if not m:
        raise SystemExit(f"{SOURCE}: no <!-- BEGIN SHARED --> block")
    return m.group(1).strip()


def rewrite(text: str, shared: str) -> str:
    """Replace the generated block in one target. Returns the new text."""
    if not _BLOCK.search(text):
        raise SystemExit(
            "target has no <!-- BEGIN GENERATED: working-agreement --> block")
    return _BLOCK.sub(lambda m: m.group(1) + shared + m.group(2), text, count=1)


def sync(root: Path, check: bool = False) -> list[str]:
    """Write (or verify) every target. Returns the ones that were out of date."""
    shared = shared_text(root)
    stale: list[str] = []
    for name in TARGETS:
        p = root / name
        text = p.read_text(encoding="utf-8")
        new = rewrite(text, shared)
        if new != text:
            stale.append(name)
            if not check:
                p.write_text(new, encoding="utf-8", newline="")
    return stale


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="fail instead of writing, for CI")
    args = ap.parse_args(argv)

    root = _root()
    stale = sync(root, check=args.check)
    if args.check and stale:
        print("the working agreement has drifted in: " + ", ".join(stale))
        print(f"\nEdit {SOURCE} and run: python scripts/sync_agent_docs.py")
        print("Three agents read three filenames; a rule only one of them can "
              "see is not a rule.")
        return 1
    if stale:
        print("updated: " + ", ".join(stale))
    else:
        print(f"the working agreement is in step across "
              f"{len(TARGETS)} agent files")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
