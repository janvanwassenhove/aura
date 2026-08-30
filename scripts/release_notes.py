#!/usr/bin/env python3
"""U284: the release notes a person actually wants to read.

Asked for as "maak voor release notes meer commerciele en gebruikersvriendelijke
template die gebruikt wordt bij elke release (en pas deze onmiddellijk toe),
behoud hierin ook zeker de screenshots".

Two things were wrong with what came before.

**It was written for a developer.** A bare "## AURA v1.2.3", a bullet list of
unit titles, a file-name table. Nothing said what the release was FOR, and the
only human sentence in it was an apology about notarisation.

**And the list was empty.** The old step scraped the ledger for
``- [x] **Title**`` — the format entries used a hundred units ago. Everything
written since reads ``- 2026-08-30 — U283 TITLE: body``, so the "Nieuw in deze
release" section silently rendered nothing, release after release. A changelog
that quietly degrades to no changelog is worse than none: it looks maintained.

Living in a file rather than inside the workflow YAML so it can be read,
reviewed and unit-tested like the rest of the app. `scripts/test_release_notes.py`
covers it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

LEDGER = Path("docs/implementation-backlog.md")

# Both ledger generations. The current one:
#   - 2026-08-30 — U283 TITLE OF THE UNIT: the story...
# and the one used up to ~U180:
#   - [x] **Title of the unit** — the story...
_CURRENT = re.compile(r"^- \d{4}-\d{2}-\d{2}\s+\S+\s+U\d+[a-z]?\s+(.+)$")
_LEGACY = re.compile(r"^- \[x\] \*\*([^*]{4,120})\*\*")


# Acronyms that must survive the shouting being taken out of a title. An
# allowlist, not a rule about length: "DE" and "OP" are two capitals too, and
# "Ci stond zes uur rood" is how the first version of this read.
_ACRONYMS = {
    "AI", "API", "AURA", "CI", "CPU", "CSS", "DNS", "HTTP", "HTTPS", "JSON",
    "LLM", "MCP", "OS", "PDF", "PNG", "RAM", "SDK", "STT", "SVG", "TTS", "UI",
    "URL", "USB", "UX", "VPN", "WS", "YAML",
}


def _title_of(rest: str) -> str:
    """The shouted title, which may itself contain colons.

    U284: the first version cut at the first ":" and turned
    "PER PERSOON: IN WELKE TAAL, EN ALS WELK KARAKTER" into "Per persoon".
    Titles are SHOUTED and bodies are prose, so the title is however many
    colon-separated segments stay in capitals.
    """
    def _shouted(part: str) -> bool:
        letters = [c for c in part if c.isalpha()]
        return bool(letters) and all(c.isupper() for c in letters)

    parts = rest.split(": ")
    if not parts or not _shouted(parts[0]):
        # A title written as prose ends at its first colon, as before.
        title = parts[0].strip() if parts else ""
    else:
        kept = []
        for part in parts:
            if not _shouted(part):
                break
            kept.append(part)
        title = ": ".join(kept).strip()
    return title if 4 <= len(title) <= 160 else ""


def _sentence(title: str) -> str:
    """A SHOUTED ledger title into something a release page can wear.

    Ledger titles are written in caps as section markers. Lowercasing the tail
    keeps the meaning and drops the shouting; anything already mixed-case was
    written as prose and is left exactly as it is.
    """
    title = title.strip().rstrip(".")
    if not title:
        return ""
    letters = [c for c in title if c.isalpha()]
    if not (letters and all(c.isupper() for c in letters)):
        return title                      # already prose — leave it be
    def _part(part: str) -> str:
        # "MCP-TOOLS" is an acronym glued to a word; treat each side on its
        # own so the acronym survives and the word stops shouting.
        return part if part.strip(".,:;!?\"'()").upper() in _ACRONYMS else part.lower()

    words = ["-".join(_part(p) for p in w.split("-")) for w in title.split(" ")]
    out = " ".join(words)
    return out[:1].upper() + out[1:]


def highlights(diff_text: str) -> list[str]:
    """The units added since the previous release, as one line each."""
    out: list[str] = []
    for raw in diff_text.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        line = raw[1:]
        m = _CURRENT.match(line)
        raw_title = _title_of(m.group(1)) if m else ""
        if not raw_title:
            m = _LEGACY.match(line)
            raw_title = m.group(1) if m else ""
        if not raw_title:
            continue
        text = _sentence(raw_title)
        if text and text not in out:
            out.append(text)
    return out


def _git_diff(prev: str) -> str:
    if not prev:
        return ""
    try:
        return subprocess.run(                      # noqa: S603
            ["git", "diff", f"{prev}..HEAD", "--", str(LEDGER)],  # noqa: S607
            capture_output=True, text=True, check=False, encoding="utf-8",
        ).stdout or ""
    except OSError:
        return ""


def compose(tag: str, repo: str, items: list[str], shots: list[str]) -> str:
    """The page itself. Written for the person installing it, not for us."""
    n = len(items)
    lines: list[str] = []
    add = lines.append

    add(f"# AURA {tag}")
    add("")
    add("_Je eigen robotcollega — hij kent je huis, praat mee en houdt zijn mond "
        "wanneer dat beter uitkomt._")
    add("")
    if n:
        # Say how much changed before listing it: a reader decides in one line
        # whether this update is worth their next five minutes.
        add(f"Deze versie brengt **{n} verbetering{'en' if n != 1 else ''}** "
            "op basis van wat er in de praktijk misging of ontbrak.")
    else:
        add("Een onderhoudsrelease: geen nieuwe functies, wel de laatste "
            "correcties en verbeteringen onder de motorkap.")
    add("")

    if items:
        add("## Wat er nieuw en beter is")
        add("")
        for it in items:
            add(f"- {it}")
        add("")

    if shots:
        add("## Zo ziet het eruit")
        add("")
        for name in shots:
            add(f"![{name}](https://github.com/{repo}/releases/download/{tag}/{name})")
            add("")
        add("_Gemaakt op een verse demo-installatie: alleen het fictieve "
            "demoprofiel, nooit echte persoonsgegevens._")
        add("")
    else:
        # U235's rule, kept: an absence nobody can see is a blind spot, not a
        # degradation. The screenshot job may fail without blocking a release,
        # so when it does, the release page says so.
        add("> _Geen schermafbeeldingen in deze release: het maken ervan is "
            "niet voltooid._")
        add("")

    add("## Aan de slag")
    add("")
    add("| Jouw systeem | Download |")
    add("|---|---|")
    add("| Windows | `AURA-*-windows-setup.exe` |")
    add("| macOS (Apple Silicon, M1–M4) | `AURA-*-mac-arm64.dmg` |")
    add("| macOS (Intel) | `AURA-*-mac-x64.dmg` |")
    add("| Linux | `AURA-*-linux-x86_64.AppImage` of `.deb` |")
    add("")
    add("**Voor het eerst?** Download, installeer en start. Bij de eerste start "
        "zet AURA zichzelf klaar (dat duurt een paar minuten) en loopt een korte "
        "wizard met je door je robot, je stem en je taal.")
    add("")
    add("**Al een vorige versie?** Installeer er gewoon overheen — je mensen, "
        "je herinneringen en je instellingen blijven staan.")
    add("")
    add("<details><summary>macOS en Linux: één keer extra klikken</summary>")
    add("")
    add("De macOS-builds zijn niet genotariseerd: open ze de eerste keer via "
        "rechtermuisknop → Open. Op macOS en Linux installeert de eerste start "
        "zelf de Python-runtime (uv).")
    add("</details>")
    add("")

    add("## Waarom AURA")
    add("")
    add("AURA maakt van een Reachy Mini een huisgenoot in plaats van een "
        "apparaat: hij herkent wie er voor hem staat, onthoudt wat je hem "
        "vertelt, presenteert met je mee en kan meekijken op je scherm — "
        "**en alles blijft op je eigen machine**. Geen abonnement, geen "
        "cloudprofiel: je sleutels en je herinneringen staan versleuteld op "
        "deze computer.")
    add("")
    add("---")
    add("")
    add("De volledige, technische geschiedenis van elke wijziging staat in "
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
    items = highlights(_git_diff(args.prev))
    page = compose(args.tag, args.repo, items, shots)

    if args.out:
        Path(args.out).write_text(page, encoding="utf-8")
        return 0
    # The page is UTF-8 by construction (arrows, em dashes, accented Dutch).
    # A Windows console defaults to cp1252 and raises on the first arrow — the
    # release runs on Linux, but a generator that only works on the runner
    # cannot be checked before it ships.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass
    sys.stdout.write(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
