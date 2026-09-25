#!/usr/bin/env python3
"""U369 (audit T2): which units a spec claims that no test names.

`spec_drift.py` (U299) checks one direction — every shipped unit is claimed by
a spec — and that closed sixty-nine units of silent drift. It says nothing
about the other direction. A spec may claim a unit whose behaviour no test
protects, and the constitution's line, "no code merged without traceability to
a spec acceptance criterion", was never checkable past the claim.

The testing audit of September 2026 measured it: of 394 claimed units, 122 are
named by no test file at all. The twelve repeat-reports since U300 are what
that number looks like from the owner's chair — a fix with nothing standing
behind it is a fix the next refactor removes without noticing.

This closes the loop the same way `spec_drift.py` did:

* A unit is **named by a test** when its id (`U339`, `U242b`) appears anywhere
  in a `test_*.py`, `*.test.ts` or desktop `test-*.cjs` file. That is this repository's convention —
  every test says in its docstring which fix it guards — so a mention is the
  link, and its absence means no test knows the fix exists.
* `.specify/coverage.json` holds a second baseline, `tests_baseline`: units up
  to it are known debt, reported on every run; everything after it must be
  named by a test or the gate fails. The baseline may only move backwards.

    python scripts/spec_tests.py            # report; exit 1 on NEW unnamed units
    python scripts/spec_tests.py --all      # exit 1 on the historical debt too
    python scripts/spec_tests.py --list     # print the debt, one unit per line
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_drift import claimed_units, split_at  # noqa: E402

_UNIT_TOKEN = re.compile(r"\bU\d{1,3}[a-z]?\b")
_SPEC_GLOB = ".specify/specs/*/spec.md"
_COVERAGE = ".specify/coverage.json"
# The desktop shell's checks are plain-node scripts named test-*.cjs, run by
# the gate like any other suite (U375b): a test file is whatever the gate
# runs, not whatever pytest or vitest happen to collect.
_TEST_GLOBS = ("*test_*.py", "*.test.ts", "*test-*.cjs")


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def unit_key(unit: str) -> tuple[int, str]:
    """Sort units the way the ledger does: by number, then suffix."""
    return int(re.sub(r"\D", "", unit)), unit


def test_files(root: Path) -> list[Path]:
    """Every tracked test file. Tracked, so a stray local file cannot vouch."""
    out = subprocess.run(["git", "ls-files", *_TEST_GLOBS], cwd=root,
                         capture_output=True, text=True, check=True).stdout
    return [root / line for line in out.splitlines() if line]


def units_named_by(files: list[Path]) -> set[str]:
    named: set[str] = set()
    for file in files:
        try:
            named.update(_UNIT_TOKEN.findall(file.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return named


def claimed_by_spec(root: Path) -> dict[str, set[str]]:
    return {p.parent.name: claimed_units(p.read_text(encoding="utf-8"))
            for p in sorted(root.glob(_SPEC_GLOB))}


def unnamed(by_spec: dict[str, set[str]], named: set[str]) -> list[str]:
    """Every claimed unit no test names, in ledger order."""
    claimed = set().union(*by_spec.values()) if by_spec else set()
    return sorted(claimed - named, key=unit_key)


def tests_baseline(root: Path) -> str:
    try:
        return str(json.loads((root / _COVERAGE).read_text(encoding="utf-8"))
                   .get("tests_baseline", ""))
    except (OSError, ValueError):
        return ""


def report(missing: list[str], by_spec: dict[str, set[str]]) -> str:
    if not missing:
        total = sum(len(v) for v in by_spec.values())
        return f"every claimed unit is named by a test — {total} units across {len(by_spec)} specs"
    owner = {u: s for s, us in by_spec.items() for u in us}
    lines = [f"{len(missing)} claimed unit(s) that no test names:", ""]
    lines += [f"  {u:7s} {owner.get(u, '?')}" for u in missing]
    lines += ["",
              "A unit is a fix. A fix no test names is a fix the next refactor",
              "removes without noticing — that is what the repeat reports since",
              "U300 were. To fix: write the test that guards the behaviour and say",
              "the unit's id in its docstring, the way every other test here does.",
              "If the unit changed nothing testable (a doc, a rename), name it in",
              "the test of the thing it touched."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="fail on the historical debt too, not just new units")
    ap.add_argument("--list", action="store_true",
                    help="print every unnamed unit, one per line, and exit 0")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    root = _root()
    by_spec = claimed_by_spec(root)
    missing = unnamed(by_spec, units_named_by(test_files(root)))
    if args.list:
        print("\n".join(missing))
        return 0

    # The baseline is a ledger position, so the split has to be in ledger
    # order over the *claimed* units, not over the missing ones alone.
    everything = sorted(set().union(*by_spec.values()), key=unit_key) if by_spec else []
    debt_side, _ = split_at(everything, tests_baseline(root))
    debt = [u for u in missing if u in set(debt_side)]
    fresh = [u for u in missing if u not in set(debt_side)]

    failing = missing if args.all else fresh
    if failing:
        print(report(failing, by_spec))
    elif debt:
        claimed = sum(len(v) for v in by_spec.values())
        print(f"no new untested units — but {len(debt)} claimed unit(s) up to the "
              f"{tests_baseline(root)} baseline are named by no test "
              f"({claimed} claimed across {len(by_spec)} specs).")
        print("Paying one off: write the test, name the unit in its docstring, and "
              "move tests_baseline back in .specify/coverage.json.")
    elif not args.quiet:
        print(report([], by_spec))
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
