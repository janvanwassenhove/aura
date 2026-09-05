#!/usr/bin/env python3
"""U299: which shipped units no specification accounts for.

The constitution's first principle is "Spec-First, Always", ending with the
line that actually matters here:

    Specs are living artifacts — update them when reality diverges.

Between U238 and U298 reality diverged sixty-nine times and no spec moved. The
ledger in `docs/implementation-backlog.md` absorbed everything instead — 420 kB
of prose that is a diary, not a contract. Nothing could notice, because nothing
was looking.

This looks. Every unit lands as exactly one commit subject `auto(UNNN): …`, and
every spec declares the units that built it in its own frontmatter:

    ---
    units: [U263, U264, U265]
    ---

A unit that no spec claims is drift, and drift is what this reports. That makes
the traceability the constitution asks for ("no code merged without traceability
to a spec acceptance criterion") a thing a machine can check rather than a habit
one has to remember at midnight.

`.specify/coverage.json` holds the baseline: units up to it are the debt this
check found on the day it was written, reported every run so the number stays
in front of us, but not yet blocking. Everything after it must be claimed or CI
fails. The baseline may only move backwards.

    python scripts/spec_drift.py              # report; exit 1 on NEW drift
    python scripts/spec_drift.py --all        # exit 1 on the historical debt too
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

#: The unit(s) a commit subject claims to have landed. One unit per commit is
#: the rule today, but the early history batched them — `auto(U2,U3):`,
#: `auto(U19c+U20):`, `auto(U112-U115):` — and a checker that skips those
#: under-reports its own debt, which is the one thing it must not do.
_UNITS_IN_SUBJECT = re.compile(r"^auto\(([^)]*)\)\s*:", re.M)

#: A unit id: `U284`, `U242b`. `U168-ledger` is bookkeeping, not a unit.
_UNIT_TOKEN_STRICT = re.compile(r"\bU\d+[a-z]?\b")

#: `U112-U115` means four units, not two — the range was shorthand for a run.
_RANGE = re.compile(r"\bU(\d+)\s*-\s*U(\d+)\b")

#: A unit id anywhere inside a spec's `units:` frontmatter block.
_UNIT_TOKEN = re.compile(r"\bU\d+[a-z]?\b")

_SPEC_GLOB = ".specify/specs/*/spec.md"
_COVERAGE = ".specify/coverage.json"


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def units_in(subject_body: str) -> list[str]:
    """The units named inside an `auto(...)` subject, expanding any range."""
    out: list[str] = []

    def add(unit: str) -> None:
        if unit not in out:
            out.append(unit)

    def expand(m: re.Match[str]) -> str:
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi or hi - lo >= 100:
            # Backwards, or absurdly wide: not a range anybody meant. Leave the
            # text alone so the two endpoints are still read as plain units.
            return m.group(0)
        for n in range(lo, hi + 1):
            add(f"U{n}")
        return " "

    for unit in _UNIT_TOKEN_STRICT.findall(_RANGE.sub(expand, subject_body)):
        add(unit)
    return out


def shipped_units(log_text: str) -> list[str]:
    """Every unit in a git log, oldest first, without duplicates."""
    out: list[str] = []
    for body in reversed(_UNITS_IN_SUBJECT.findall(log_text)):
        for unit in units_in(body):
            if unit not in out:
                out.append(unit)
    return out


def claimed_units(spec_text: str) -> set[str]:
    """The units a spec says it accounts for.

    Read from the `units:` key of the leading frontmatter, in either YAML
    shape — an inline list or an indented block. Anything outside that block
    is ignored on purpose: a spec that merely MENTIONS U263 in its prose has
    not thereby taken responsibility for it.
    """
    if not spec_text.startswith("---"):
        return set()
    end = spec_text.find("\n---", 3)
    front = spec_text[3:end if end > 0 else len(spec_text)]

    lines = front.splitlines()
    for i, line in enumerate(lines):
        if not re.match(r"^units\s*:", line):
            continue
        block = [line]
        for nxt in lines[i + 1:]:
            # The block ends at the next top-level key.
            if nxt.strip() and not nxt.startswith((" ", "\t", "-")):
                break
            block.append(nxt)
        return set(_UNIT_TOKEN.findall("\n".join(block)))
    return set()


def specs(root: Path) -> dict[str, set[str]]:
    """Every spec, and the units it claims."""
    return {
        str(p.parent.name): claimed_units(p.read_text(encoding="utf-8"))
        for p in sorted(root.glob(_SPEC_GLOB))
    }


def _git_log(root: Path, since: str = "") -> str:
    args = ["git", "log", "--no-merges", "--format=%s"]
    if since:
        # The commit that landed `since`, exclusive.
        rev = subprocess.run(                                     # noqa: S603
            ["git", "log", "--format=%H", "-1", f"--grep=auto({since}):"],  # noqa: S607
            cwd=root, capture_output=True, text=True, check=False,
        ).stdout.strip()
        if rev:
            args.append(f"{rev}..HEAD")
    return subprocess.run(                                        # noqa: S603
        args, cwd=root, capture_output=True, text=True, check=False,
        encoding="utf-8", errors="replace",
    ).stdout or ""


def drift(shipped: list[str], by_spec: dict[str, set[str]]) -> list[str]:
    """Shipped units that no spec has taken responsibility for."""
    claimed = set().union(*by_spec.values()) if by_spec else set()
    return [u for u in shipped if u not in claimed]


def report(units: list[str], by_spec: dict[str, set[str]]) -> str:
    if not units:
        total = sum(len(v) for v in by_spec.values())
        return f"spec coverage complete — {total} units claimed across {len(by_spec)} specs"
    lines = [
        f"{len(units)} shipped unit(s) that no specification accounts for:",
        "",
        "  " + ", ".join(units),
        "",
        "The constitution's first principle ends with: \"Specs are living",
        "artifacts — update them when reality diverges.\" Each of these changed",
        "what the product does and left no trace in .specify/specs/.",
        "",
        "To fix: add the unit to the `units:` frontmatter of the spec whose",
        "behaviour it changed, and update that spec's text to match what the",
        "code now does. If no spec covers it, the feature needs one.",
    ]
    return "\n".join(lines)


def baseline(root: Path) -> str:
    """The unit up to which missing specs are known debt rather than a failure."""
    try:
        return str(json.loads((root / _COVERAGE).read_text(encoding="utf-8"))
                   .get("baseline", ""))
    except (OSError, ValueError):
        return ""


def split_at(units: list[str], marker: str) -> tuple[list[str], list[str]]:
    """(debt, new) — everything up to and including `marker`, then the rest.

    No baseline at all means nothing is forgiven. A baseline naming a unit
    that has not landed yet — the normal case while writing the very unit that
    sets it — means nothing is newer than it either, so there is no new drift
    to fail on: exactly the same answer, one commit later.
    """
    if not marker:
        return [], units
    if marker not in units:
        return units, []
    cut = units.index(marker) + 1
    return units[:cut], units[cut:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="fail on the historical debt too, not just new drift")
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing when there is no new drift")
    args = ap.parse_args(argv)

    root = _root()
    by_spec = specs(root)
    shipped = shipped_units(_git_log(root))
    missing = drift(shipped, by_spec)
    debt, fresh = split_at(missing, baseline(root))

    failing = missing if args.all else fresh
    if failing:
        print(report(failing, by_spec))
    elif debt:
        # Never "complete" while the debt stands, and never silent about it:
        # a debt nobody is reminded of is a debt nobody pays.
        claimed = sum(len(v) for v in by_spec.values())
        print(f"no new drift — but {len(debt)} unit(s) of documentation debt "
              f"remain from before the {baseline(root)} baseline "
              f"({claimed} claimed across {len(by_spec)} specs).")
        print("Paying one off: write or update the spec, list the unit in its "
              "`units:` frontmatter, and move the baseline back in "
              ".specify/coverage.json.")
    elif not args.quiet:
        print(report([], by_spec))
    return 1 if failing else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
