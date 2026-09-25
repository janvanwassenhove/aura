"""U367: CI was red for six units and the installers kept shipping.

Reported as "build failed?" — it had, since U361, on every push. Nobody saw it
because the Release workflow is green and independent, so builds kept appearing
in the usual place while the checks beside them failed.

The cause is a leftover from my own U337, which replaced a hand-kept list of
*tests* in the "Repository checks" step with `pytest scripts/ -q`, and left a
hand-kept list of *dependencies* one line above it:

    pip install pillow pyyaml
    pytest scripts/ -q

U361 added `scripts/check_scenario.py`, which imports `shared_schemas` and so
needs pydantic. The list did not know. Seven tests failed with
`ModuleNotFoundError` buried inside a subprocess's captured stdout, which reads
like the script is broken rather than the job.

The step now installs the workspace instead of guessing. This file is the part
that stays useful afterwards: it reads the top-level imports of every script
and says, by name, which module cannot be imported here. When the next script
arrives with a new dependency, the failure is one line that names it.

Deliberately `ast`-based rather than importing each script: importing runs
module-level code, and the point is to be able to say what is missing without
depending on being able to run it.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
#: Packages that live in this repository — importable once the workspace is
#: installed, which is exactly what the CI step must do.
LOCAL = {"shared_schemas", "shared_config", "orchestrator", "aura_brain",
         "memory_service", "connector_service", "identity_service",
         "conversation_runtime", "robot_runtime"}


def _top_level_imports(path: Path) -> set[str]:
    """Every module imported at the top level of one script."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in tree.body:                      # top level only, on purpose
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Try):         # optional imports are allowed
            continue
    return found


def _scripts() -> list[Path]:
    return sorted(p for p in SCRIPTS.glob("*.py")
                  if not p.name.startswith("test_"))


def test_every_script_can_import_what_it_needs() -> None:
    missing: dict[str, set[str]] = {}
    for script in _scripts():
        for module in _top_level_imports(script):
            if module in sys.stdlib_module_names or module in LOCAL:
                continue
            if importlib.util.find_spec(module) is None:
                missing.setdefault(script.name, set()).add(module)

    assert not missing, (
        "these scripts import something this environment does not have — "
        "install it in the CI step that runs them (.github/workflows/ci.yml, "
        f"'Repository checks'): { {k: sorted(v) for k, v in missing.items()} }")


def test_the_local_packages_are_actually_importable() -> None:
    """The half a dependency list cannot express: the scripts import this
    repository's own packages, so the job has to install the workspace rather
    than a handful of names from PyPI."""
    for module in ("shared_schemas",):
        assert importlib.util.find_spec(module) is not None, (
            f"{module} is not importable — the Repository checks step must "
            f"install the workspace (uv sync), not a list of packages")


def test_a_missing_module_would_actually_be_reported() -> None:
    """A guard that cannot fail guards nothing."""
    assert importlib.util.find_spec("a_module_that_does_not_exist_anywhere") is None
