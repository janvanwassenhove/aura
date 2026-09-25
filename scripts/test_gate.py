"""U372 (audit T5): the local gate is the CI gate, by construction.

There was no single command that did what CI does, so "verified locally"
meant "ran the suite I remembered" — and the checks-job fix just before this
audit was verified that way and was wrong. `gate.py` reads `checks.yml` and runs its steps; these tests pin that it
reads the real thing, keeps the runner's order, honours `working-directory` and
`env`, and stops where the runner would.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # noqa: E402
from gate import Step, load_gate, steps_of  # noqa: E402

FIXTURE = {
    "jobs": {
        "privacy": {"steps": [
            {"uses": "actions/checkout@v4"},
            {"name": "Privacy scan", "run": "python scripts/privacy_scan.py --all"},
            {"run": "pytest scripts/test_privacy_scan.py -q\npython scripts/spec_drift.py"},
        ]},
        "console": {"env": {"LLM_PROVIDER": "echo"}, "steps": [
            {"name": "Console tests + build", "working-directory": "apps/operator-console",
             "run": "npm ci\nnpm test", "env": {"CI": "1"}},
        ]},
    }
}


def test_every_run_step_is_taken_in_the_runner_s_order() -> None:
    steps = steps_of(FIXTURE)
    assert [s.name for s in steps] == [
        "Privacy scan", "pytest scripts/test_privacy_scan.py -q", "Console tests + build"]
    assert all(isinstance(s, Step) for s in steps)


def test_uses_steps_are_the_runner_s_own_and_are_skipped() -> None:
    assert all("checkout" not in s.run for s in steps_of(FIXTURE))


def test_working_directory_and_env_travel_with_the_step() -> None:
    console = steps_of(FIXTURE)[-1]
    assert console.cwd == "apps/operator-console"
    assert console.env == {"LLM_PROVIDER": "echo", "CI": "1"}, "job env, then step env on top"
    assert steps_of(FIXTURE)[0].cwd == "."


def test_it_reads_the_real_gate_and_finds_every_job() -> None:
    """Not a copy of checks.yml — the file. A step added there runs here."""
    real = steps_of(load_gate())
    jobs = {s.job for s in real}
    assert {"privacy", "test", "console", "desktop-lint", "lint"} <= jobs
    assert any("spec_tests.py" in s.run for s in real), "the gate's own newest step is missing"


# ── running ────────────────────────────────────────────────────────────────

def _drive(monkeypatch, workflow: dict, *argv: str, fail_on: set[str] = frozenset()):
    ran: list[str] = []

    def fake_run(step: Step, root=None) -> int:
        ran.append(step.name)
        return 1 if step.name in fail_on else 0

    monkeypatch.setattr(gate, "load_gate", lambda path=None: workflow)
    monkeypatch.setattr(gate, "run_step", fake_run)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = gate.main(list(argv))
    return code, ran, buf.getvalue()


def test_list_prints_the_steps_and_runs_nothing(monkeypatch) -> None:
    code, ran, out = _drive(monkeypatch, FIXTURE, "--list")
    assert code == 0 and ran == []
    assert "[privacy] Privacy scan" in out and "(in apps/operator-console)" in out


def test_a_job_filter_runs_that_job_only(monkeypatch) -> None:
    code, ran, _ = _drive(monkeypatch, FIXTURE, "--job", "console")
    assert code == 0 and ran == ["Console tests + build"]


def test_an_unknown_job_is_refused_by_name(monkeypatch) -> None:
    code, ran, out = _drive(monkeypatch, FIXTURE, "--job", "nope")
    assert code == 2 and ran == [] and "nope" in out and "privacy" in out


def test_it_stops_at_the_first_failure_like_the_runner(monkeypatch) -> None:
    code, ran, out = _drive(monkeypatch, FIXTURE, fail_on={"Privacy scan"})
    assert code == 1
    assert ran == ["Privacy scan"], "it kept going after a red step"
    assert "gate FAILED" in out and "Privacy scan" in out


def test_keep_going_runs_everything_and_reports_all(monkeypatch) -> None:
    code, ran, out = _drive(monkeypatch, FIXTURE, "--keep-going",
                            fail_on={"Privacy scan", "Console tests + build"})
    assert code == 1 and len(ran) == 3
    assert out.count("FAIL") >= 4       # each failure, inline and in the summary


def test_green_says_so_and_says_it_is_the_same_gate(monkeypatch) -> None:
    code, _, out = _drive(monkeypatch, FIXTURE)
    assert code == 0 and "gate green" in out and "the same steps CI runs" in out
