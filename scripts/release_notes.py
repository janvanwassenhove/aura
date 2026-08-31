#!/usr/bin/env python3
"""U285: the release page, in English, built from the commit log.

Asked for as "release notes altijd in engels" — the first version of this
template (U284) was written in Dutch, and its bullets came from the ledger,
which is Dutch prose. Translating those is not something a build step can do.

But every unit already lands as exactly one commit with an English subject:

    auto(U284): release notes a person wants to read — and that were not empty

So the commit log IS the changelog, in the right language, at the right
granularity, and without a second thing to keep in sync. Scraping the ledger —
which is what U284 did, and what the version before it did wrongly — was
always the roundabout route to the same list.

The page itself lives here rather than inside the workflow YAML so it can be
read, reviewed and unit-tested like the rest of the app;
`scripts/test_release_notes.py` covers it, and CI runs that.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# One unit, one commit: `auto(U284): the title`. The unit number is dropped —
# it means everything to us and nothing to somebody installing the app.
_UNIT = re.compile(r"^auto\(U\d+[a-z]?\):\s*(.+?)\s*$")

# Subjects that describe the plumbing rather than the product. A release page
# is not the place for "bump the version" — the full history is linked instead.
_SKIP = re.compile(
    r"^(chore|ci|build|docs|merge|revert|bump|wip)\b|^merge (branch|pull)", re.I)

# Acronyms that must survive a title being sentence-cased.
_ACRONYMS = {
    "AI", "API", "AURA", "CI", "CPU", "CSS", "DNS", "HTTP", "HTTPS", "JSON",
    "LLM", "MCP", "OS", "PDF", "PNG", "RAM", "SDK", "STT", "SVG", "TTS", "UI",
    "URL", "USB", "UX", "VPN", "WS", "YAML",
}


def _sentence(title: str) -> str:
    """Tidy a commit subject into a line that can sit on a release page."""
    title = title.strip().rstrip(".")
    if not title:
        return ""
    letters = [c for c in title if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        # A shouted subject: take the shouting out, but not out of "CI".
        def _part(part: str) -> str:
            return (part if part.strip(".,:;!?\"'()").upper() in _ACRONYMS
                    else part.lower())

        title = " ".join(
            "-".join(_part(p) for p in w.split("-")) for w in title.split(" "))
    return title[:1].upper() + title[1:]


def highlights(log_text: str, limit: int = 25) -> list[str]:
    """One line per unit released, newest first, in the order they landed."""
    out: list[str] = []
    for raw in log_text.splitlines():
        subject = raw.strip()
        if not subject or _SKIP.match(subject):
            continue
        m = _UNIT.match(subject)
        if not m:
            continue
        text = _sentence(m.group(1))
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _git_log(prev: str) -> str:
    span = f"{prev}..HEAD" if prev else "HEAD"
    try:
        return subprocess.run(                                   # noqa: S603
            ["git", "log", "--no-merges", "--format=%s", span],  # noqa: S607
            capture_output=True, text=True, check=False, encoding="utf-8",
        ).stdout or ""
    except OSError:
        return ""


def compose(tag: str, repo: str, items: list[str], shots: list[str]) -> str:
    """The page itself — written for the person installing it, not for us."""
    n = len(items)
    lines: list[str] = []
    add = lines.append

    add(f"# AURA {tag}")
    add("")
    add("_Your own robot colleague — he knows your household, joins the "
        "conversation, and keeps quiet when that serves you better._")
    add("")
    if n:
        # How much changed, before what changed: a reader decides in one line
        # whether this update is worth the next five minutes.
        if n == 1:
            add("This release brings **one improvement**, from something that "
                "went wrong or was missing in real use.")
        else:
            add(f"This release brings **{n} improvements**, each one from "
                "something that went wrong or was missing in real use.")
    else:
        add("A maintenance release: no new features, just the latest fixes and "
            "improvements under the hood.")
    add("")

    if items:
        add("## What's new and better")
        add("")
        for it in items:
            add(f"- {it}")
        add("")

    if shots:
        add("## What it looks like")
        add("")
        for name in shots:
            add(f"![{name}](https://github.com/{repo}/releases/download/{tag}/{name})")
            add("")
        add("_Captured on a fresh demo install: the fictional demo profile only, "
            "never real personal data._")
        add("")
    else:
        # U235's rule, kept: the screenshot job may fail without blocking a
        # release, so when it does the page admits it. An absence nobody can
        # see is a blind spot, not a degradation.
        add("> _No screenshots in this release: capturing them did not "
            "complete._")
        add("")

    add("## Getting started")
    add("")
    add("| Your system | Download |")
    add("|---|---|")
    add("| Windows | `AURA-*-windows-setup.exe` |")
    add("| macOS (Apple Silicon, M1–M4) | `AURA-*-mac-arm64.dmg` |")
    add("| macOS (Intel) | `AURA-*-mac-x64.dmg` |")
    add("| Linux | `AURA-*-linux-x86_64.AppImage` or `.deb` |")
    add("")
    add("**First time?** Download, install, and start it. On first launch AURA "
        "sets itself up (a few minutes) and a short wizard walks you through "
        "your robot, your voice and your language.")
    add("")
    add("**Already on an older version?** Install straight over it — your "
        "people, your memories and your settings stay exactly as they are.")
    add("")
    add("<details><summary>macOS and Linux: one extra click the first time</summary>")
    add("")
    add("The macOS builds are not notarised: open them the first time via "
        "right-click → Open. On macOS and Linux the first launch installs the "
        "Python runtime (uv) by itself.")
    add("</details>")
    add("")

    add("## Why AURA")
    add("")
    add("AURA turns a Reachy Mini into a housemate rather than a device: he "
        "recognises who is in front of him, remembers what you tell him, "
        "co-presents with you and can watch your screen — **and all of it "
        "stays on your own machine**. No subscription, no cloud profile: your "
        "keys and your memories are encrypted on this computer.")
    add("")
    add("---")
    add("")
    add("The full technical history of every change is in "
        f"[docs/implementation-backlog.md](https://github.com/{repo}/blob/master/docs/implementation-backlog.md).")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--prev", default="")
    ap.add_argument("--shots-dir", default="shots")
    ap.add_argument("--out", default="", help="write here instead of stdout")
    args = ap.parse_args(argv)

    shots = sorted(p.name for p in Path(args.shots_dir).glob("*.png")) \
        if Path(args.shots_dir).is_dir() else []
    page = compose(args.tag, args.repo, highlights(_git_log(args.prev)), shots)

    if args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        return 0
    # The page is UTF-8 by construction (arrows, em dashes). A Windows console
    # defaults to cp1252 and raises on the first arrow — the release runs on
    # Linux, but a generator that only works on the runner cannot be checked
    # before it ships.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass
    sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
