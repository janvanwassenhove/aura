"""U327: the owner's settings must not live inside the install directory.

Reported as "in quiet mode he should not talk, but he still talks" — with a
screenshot of two cheerful openers under a header that read HUSHED.

He really did speak, and the switch was not at fault. Quiet is stored in
`./data/mode-policy.json`, resolved against the brain's working directory,
which for the packaged app **is the install directory**. Every update replaces
that directory, so the switch the owner set silently went back to off. Measured
on the owner's machine: the persistent copy under `userData` said quiet since
1 September; the copy the brain was actually reading had been created that same
afternoon, when they switched it on again after noticing.

U177 moved knowledge, recognition, the database, skills and scenarios under
`userData` "so an update can never wipe it" — and stopped there. Four more
paths kept the old default, and one of them was the one that decides whether he
opens his mouth.

This test is the part U177 was missing: every environment variable whose
default resolves inside the install directory must be pinned by the desktop
app, so the NEXT one cannot be forgotten the same way.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DESKTOP_MAIN = REPO / "apps" / "desktop" / "main.cjs"

#: Where the brain and its services live.
SOURCES = (
    REPO / "apps" / "aura-brain" / "src",
    REPO / "services",
    REPO / "packages",
)

#: A default that lands in the working directory: "./data/x", "data/x",
#: "./skills", os.path.join("data", "x").
_RELATIVE = re.compile(
    r"""^(?:"|')?\.?[/\\]?(?:data|skills|scenarios)[/\\'"]""",
)

#: os.environ.get("NAME", <default>)
_ENV_DEFAULT = re.compile(
    r"""os\.environ\.get\(\s*["']([A-Z_]+)["']\s*,\s*([^)]+)\)""",
)

#: A module-level constant used as that default: _DEFAULT_PATH = "./data/x"
_CONSTANT = re.compile(
    r"""^(_[A-Z_]+)\s*=\s*(["'][^"']+["'])""", re.M,
)


def _is_relative_default(raw: str, constants: dict[str, str]) -> bool:
    raw = constants.get(raw.strip(), raw).strip()
    if raw.startswith("os.path.join("):
        first = raw[len("os.path.join("):].lstrip()
        return bool(_RELATIVE.match(first))
    return bool(_RELATIVE.match(raw))


def owner_state_vars() -> dict[str, str]:
    """Every env var whose default puts owner state in the working directory."""
    found: dict[str, str] = {}
    for root in SOURCES:
        for py in root.rglob("*.py"):
            if "/tests/" in py.as_posix() or "\\tests\\" in str(py):
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            constants = dict(_CONSTANT.findall(text))
            for name, default in _ENV_DEFAULT.findall(text):
                if _is_relative_default(default, constants):
                    found.setdefault(name, py.relative_to(REPO).as_posix())
    return found


def pinned_by_the_desktop_app() -> set[str]:
    """Env vars main.cjs gives an absolute home under userData."""
    text = DESKTOP_MAIN.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"""env\.([A-Z_]+)\s*=\s*env\.\1\s*\|\|""", text))


def test_the_scan_still_finds_the_paths_it_is_meant_to_guard() -> None:
    """A silent regex is worse than no test: if this ever finds nothing, the
    check below would pass while guarding nothing at all."""
    found = owner_state_vars()
    assert "MODE_POLICY_PATH" in found, found
    assert "KNOWLEDGE_DB_PATH" in found, found
    assert len(found) >= 5, found


def test_every_owner_setting_survives_an_update() -> None:
    """The install directory is replaced on every update. Anything the owner
    set that lives there is lost — quietly, which is the worst way."""
    unpinned = {
        name: where for name, where in owner_state_vars().items()
        if name not in pinned_by_the_desktop_app()
    }
    assert not unpinned, (
        "these keep owner state in the install directory, which every update "
        f"replaces — pin them to DATA_DIR in apps/desktop/main.cjs: {unpinned}"
    )
