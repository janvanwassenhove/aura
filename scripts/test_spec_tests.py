"""U369 (audit T2): the check that closes the loop spec_drift.py left open.

spec_drift.py asks "is every shipped unit claimed by a spec?". Nothing asked
"is every claimed unit protected by a test?" — and the audit measured 122
claimed units that no test names. These pin the mechanism; the real numbers
are printed by `python scripts/spec_tests.py`.

Fixture ids are in the U8xx range on purpose (U369b): this file is itself a test file,
so any real unit id it mentioned — even as fixture data — would count as
that unit being named by a test. The first version used ids from the
live two-hundred range and quietly "covered" five real units it knew nothing
about — the debt count dropped from 122 to 117 with no test written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec_tests  # noqa: E402
from spec_tests import report, unit_key, units_named_by, unnamed  # noqa: E402


def _write(dirpath: Path, name: str, text: str) -> Path:
    p = dirpath / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_a_unit_named_anywhere_in_a_test_file_counts(tmp_path) -> None:
    py = _write(tmp_path, "test_x.py", '"""U839: pairing.\n"""\ndef test_it(): ...\n')
    ts = _write(tmp_path, "views/Y.test.ts", "/** U841: sleep. */\nit('x', () => {})\n")
    assert units_named_by([py, ts]) == {"U839", "U841"}


def test_a_desktop_check_is_a_test_file_too(tmp_path) -> None:
    """U375b: the shell's checks are plain-node `test-*.cjs` scripts, run by
    the gate. The first version of this check did not count them, so U375 —
    guarded by one — was reported as a unit no test names, and the gate went
    red on the commit that added the guard."""
    cjs = _write(tmp_path, "test-brain-env.cjs", "// U875: pins the env
")
    assert units_named_by([cjs]) == {"U875"}
    assert "*test-*.cjs" in spec_tests._TEST_GLOBS


def test_a_suffix_is_its_own_unit() -> None:
    p = Path.cwd()  # unused path; content only
    assert units_named_by([]) == set()
    assert unit_key("U842b") == (842, "U842b") and unit_key("U842") < unit_key("U842b")
    del p


def test_unnamed_is_what_a_spec_claims_minus_what_tests_name() -> None:
    by_spec = {"016": {"U825", "U826", "U836"}, "021": {"U839"}}
    assert unnamed(by_spec, {"U826", "U839"}) == ["U825", "U836"]


def test_the_report_names_the_spec_that_owns_each_debt() -> None:
    text = report(["U836"], {"016-embodiment": {"U836"}})
    assert "U836" in text and "016-embodiment" in text
    assert "docstring" in text, "the fix must say HOW to pay it off"


def test_nothing_missing_is_said_plainly() -> None:
    assert "every claimed unit is named by a test" in report([], {"a": {"U801"}})


# ── the baseline: debt reported, new units blocking ────────────────────────

def _repo(tmp_path: Path, *, baseline: str, claimed: list[str], named: list[str]) -> Path:
    spec = tmp_path / ".specify" / "specs" / "099-x"
    _write(spec, "spec.md", f"---\nunits: [{', '.join(claimed)}]\n---\n# x\n")
    _write(tmp_path / ".specify", "coverage.json", json.dumps({"tests_baseline": baseline}))
    _write(tmp_path / "tests", "test_named.py", '"""' + " ".join(named) + '"""\n')
    return tmp_path


def _run(monkeypatch, root: Path, *argv: str) -> tuple[int, str]:
    import io
    from contextlib import redirect_stdout

    monkeypatch.setattr(spec_tests, "_root", lambda: root)
    # git ls-files would look at the real repo; the fixture is the tree.
    monkeypatch.setattr(spec_tests, "test_files", lambda r: sorted(r.rglob("test_*.py")))
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = spec_tests.main(list(argv))
    return code, buf.getvalue()


def test_debt_behind_the_baseline_is_reported_not_failed(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path, baseline="U900", claimed=["U899", "U900", "U901"],
                 named=["U901"])
    code, out = _run(monkeypatch, root)
    assert code == 0
    assert "2 claimed unit(s)" in out and "U900 baseline" in out


def test_a_new_unit_no_test_names_fails_the_gate(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path, baseline="U900", claimed=["U900", "U901", "U902"],
                 named=["U901"])
    code, out = _run(monkeypatch, root)
    assert code == 1
    assert "U902" in out and "U900" not in out.split("no test names")[1].split("A unit is a fix")[0]


def test_no_baseline_forgives_nothing(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path, baseline="", claimed=["U810", "U811"], named=["U811"])
    code, out = _run(monkeypatch, root)
    assert code == 1 and "U810" in out


def test_all_fails_on_the_debt_too(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path, baseline="U900", claimed=["U899", "U900"], named=[])
    assert _run(monkeypatch, root, "--all")[0] == 1


def test_list_prints_the_debt_one_per_line_and_exits_clean(tmp_path, monkeypatch) -> None:
    root = _repo(tmp_path, baseline="U900", claimed=["U899", "U900", "U901"], named=["U900"])
    code, out = _run(monkeypatch, root, "--list")
    assert code == 0
    assert out.split() == ["U899", "U901"]


# ── the baseline may only shrink ───────────────────────────────────────────

def test_the_real_baseline_never_moves_forward() -> None:
    """Mirror of spec_drift's rule. The debt is paid by writing tests, not by
    moving the line past the units nobody wrote them for."""
    root = Path(__file__).resolve().parents[1]
    current = spec_tests.tests_baseline(root)
    # Spelled in two parts on purpose: written as one token, this file would
    # itself "name" the ceiling unit, which it does not guard.
    ceiling = "U367" + "b"   # the day this check was written
    if current:
        assert unit_key(current) <= unit_key(ceiling), (
            f"tests_baseline moved FORWARD to {current}; it may only move back")
