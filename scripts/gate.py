#!/usr/bin/env python3
"""U372 (audit T5): run the gate here, from the file CI reads.

"Verified locally" used to mean "ran the suite I remembered". U367b was
verified that way and was wrong: this machine's environment already had
everything, so the command could not fail here for the reason it failed there.
And there was no single command that did what CI does -- no Makefile, no root
script -- so remembering was the only option.

This reads `.github/workflows/checks.yml` and runs its steps. Not a copy of
them: the file itself. Add a step to the gate and it runs here on the next
invocation; there is no second list to forget.

    python scripts/gate.py               # every job, every step, stop on first failure
    python scripts/gate.py --job test    # one job (privacy, test, console, desktop-lint, lint)
    python scripts/gate.py --list        # print what would run, and nothing else
    python scripts/gate.py --keep-going  # run everything, report all failures at the end

Environment steps (`pip install …`, `npm ci`, `uv sync …`) are run too, so a
fresh clone gets the same treatment as the runner. Steps run through `bash`,
because that is what the runner uses and what the `run:` blocks are written
in; on Windows that is Git Bash, which every checkout of this repository
already needs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / ".github" / "workflows" / "checks.yml"


@dataclass(frozen=True)
class Step:
    job: str
    name: str
    run: str
    cwd: str            # relative to the repository root
    env: dict[str, str]


def steps_of(workflow: dict) -> list[Step]:
    """Every `run:` step in the gate, in the order the runner would take."""
    out: list[Step] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        job_env = {k: str(v) for k, v in (job.get("env") or {}).items()}
        for step in job.get("steps") or []:
            if "run" not in step:
                continue                      # `uses:` steps are the runner's own
            env = dict(job_env)
            env.update({k: str(v) for k, v in (step.get("env") or {}).items()})
            out.append(Step(
                job=job_name,
                name=str(step.get("name") or step["run"].strip().splitlines()[0]),
                run=str(step["run"]),
                cwd=str(step.get("working-directory") or "."),
                env=env,
            ))
    return out


def load_gate(path: Path = GATE) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _bash() -> str:
    for candidate in ("bash", "C:/Program Files/Git/bin/bash.exe"):
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    raise SystemExit("bash not found -- the gate's steps are written for it (Git Bash on Windows)")


def run_step(step: Step, root: Path = REPO) -> int:
    env = dict(os.environ)
    env.update(step.env)
    # The runner sets these; some steps (and the privacy scan) read them.
    env.setdefault("CI", "true")
    return subprocess.call([_bash(), "-e", "-o", "pipefail", "-c", step.run],
                           cwd=root / step.cwd, env=env)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--job", action="append", help="only this job (repeatable)")
    ap.add_argument("--list", action="store_true", help="print the steps and exit")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not stop at the first failing step")
    args = ap.parse_args(argv)

    # Windows consoles default to cp1252; a step that prints a check mark must
    # not take the gate down with it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    steps = steps_of(load_gate())
    if args.job:
        wanted = set(args.job)
        unknown = wanted - {s.job for s in steps}
        if unknown:
            print(f"no such job(s): {sorted(unknown)} -- jobs are {sorted({s.job for s in steps})}")
            return 2
        steps = [s for s in steps if s.job in wanted]

    if args.list:
        for s in steps:
            where = f" (in {s.cwd})" if s.cwd != "." else ""
            print(f"[{s.job}] {s.name}{where}")
        return 0

    failed: list[Step] = []
    started = time.monotonic()
    for s in steps:
        print(f"\n== [{s.job}] {s.name}" + (f"  (in {s.cwd})" if s.cwd != "." else ""), flush=True)
        code = run_step(s)
        if code != 0:
            print(f"FAIL [{s.job}] {s.name} -- exit {code}", flush=True)
            failed.append(s)
            if not args.keep_going:
                break
    took = time.monotonic() - started
    if failed:
        print(f"\ngate FAILED -- {len(failed)} step(s) in {took:.0f}s:")
        for s in failed:
            print(f"  FAIL [{s.job}] {s.name}")
        return 1
    print(f"\ngate green -- {len(steps)} step(s) in {took:.0f}s, the same steps CI runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
