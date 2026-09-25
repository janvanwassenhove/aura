"""U368 (audit T1): one gate, and a release that cannot skip it.

CI and Release each kept their own list of what must pass. The lists had
already drifted — Release lacked `identity-service` and `test-brain-launch.cjs`
and ran none of the repository checks — so a red CI shipped installers for
seven units (U361–U367) and nothing said so. U337 removed one hand-kept list,
U367 a second; this removes the one that decides whether a build reaches the
owner.

The shape: `.github/workflows/checks.yml` is a reusable workflow
(`on: workflow_call`) holding every job. `ci.yml` calls it and nothing else.
`release.yml`'s gate job calls it too, and building depends on that job. There
is then exactly one place a suite is listed, and these tests refuse a second.

They also refuse the drift that started this: every package with a `tests/`
directory, and every ad-hoc desktop check, must appear in the gate — computed
from the tree, not from a list of their own.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WF = REPO / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def _text(name: str) -> str:
    return (WF / name).read_text(encoding="utf-8")


def _steps_text(workflow: dict) -> str:
    """Every `run:` line in every job, joined — what the workflow executes."""
    out: list[str] = []
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if "run" in step:
                out.append(str(step["run"]))
    return "\n".join(out)


def _on(workflow: dict) -> dict:
    # PyYAML reads the bare key `on:` as boolean True.
    return workflow.get("on") or workflow.get(True) or {}


# ── one gate ───────────────────────────────────────────────────────────────

def test_the_gate_is_a_reusable_workflow() -> None:
    gate = _load("checks.yml")
    assert "workflow_call" in _on(gate), "checks.yml must be callable (on: workflow_call)"
    assert gate.get("jobs"), "the gate has no jobs"


def test_ci_runs_the_gate_and_keeps_no_list_of_its_own() -> None:
    ci = _load("ci.yml")
    uses = [j.get("uses", "") for j in ci["jobs"].values()]
    assert any(u.endswith("checks.yml") for u in uses), "ci.yml does not call checks.yml"
    ran = _steps_text(ci)
    for marker in ("pytest", "npm test", "node test-", "ruff check"):
        assert marker not in ran, (
            f"ci.yml runs `{marker}` itself — that is a second list. It belongs in checks.yml")


def test_the_release_builds_only_behind_the_same_gate() -> None:
    rel = _load("release.yml")
    jobs = rel["jobs"]
    gate_jobs = [n for n, j in jobs.items() if str(j.get("uses", "")).endswith("checks.yml")]
    assert gate_jobs, "release.yml has no job that calls checks.yml"
    gate = gate_jobs[0]
    for name in ("build", "release"):
        needs = jobs[name].get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        assert gate in needs, f"release.yml job `{name}` does not depend on the gate `{gate}`"
    ran = _steps_text(rel)
    for marker in ("pytest", "npm test", "node test-"):
        assert marker not in ran, (
            f"release.yml runs `{marker}` itself — the drifted copy this unit removes")


# ── the gate cannot quietly miss a suite ───────────────────────────────────

def _packages_with_tests() -> list[str]:
    """Packages that have at least one test to run.

    A `tests/` directory alone is not enough: `shared-prompts` has had one since
    April with only an `__init__.py` in it, and pytest on an empty directory
    exits 5, which would fail the gate for a suite that does not exist. That
    empty directory is its own finding (audit T11); this walk is about suites
    the gate could run and does not.
    """
    out = []
    for root in ("packages", "services", "apps"):
        for pkg in sorted((REPO / root).iterdir()):
            tests = pkg / "tests"
            if tests.is_dir() and (pkg / "pyproject.toml").exists()                     and any(tests.rglob("test_*.py")):
                out.append(pkg.name)
    return out


def test_every_python_suite_in_the_tree_is_in_the_gate() -> None:
    """Computed from the tree. `identity-service` had a tests/ directory and was
    in CI's list but not Release's; a list cannot notice that, a directory
    walk can."""
    ran = _steps_text(_load("checks.yml"))
    missing = [p for p in _packages_with_tests() if f"--package {p} " not in ran]
    assert not missing, f"suites the gate never runs: {missing}"


def test_every_desktop_check_is_in_the_gate() -> None:
    ran = _steps_text(_load("checks.yml"))
    scripts = sorted(p.name for p in (REPO / "apps" / "desktop").glob("test-*.cjs"))
    assert scripts, "no desktop checks found — did they move?"
    missing = [s for s in scripts if s not in ran]
    assert not missing, f"desktop checks the gate never runs: {missing}"


def test_the_repository_checks_are_in_the_gate() -> None:
    """These are the ones Release skipped entirely. A privacy scan that does
    not run before an installer is published protects nothing."""
    ran = _steps_text(_load("checks.yml"))
    for needle in ("privacy_scan.py --all", "spec_drift.py", "check_doc_links.py",
                   "sync_agent_docs.py --check", "pytest scripts/", "npm test",
                   "ruff check"):
        assert needle in ran, f"the gate does not run `{needle}`"
