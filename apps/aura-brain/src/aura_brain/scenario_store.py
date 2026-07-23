"""U207: save and load co-presenter scenarios, so you build one in the app once
and reuse it — no re-pasting YAML.

One scenario per YAML file in ``SCENARIOS_DIR`` (default ``./scenarios``; the
desktop app points it at userData so an update never wipes them). Each file is
validated against the ``Scenario`` model on read, so a hand-edited file that
went wrong surfaces as an error instead of a broken presentation.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import yaml
from shared_schemas.presentation import Scenario

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def slugify(name: str) -> str:
    """A safe filename stem from a free-text title/name."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:64] or "scenario"


class ScenarioStore:
    def __init__(self, directory: str | None = None) -> None:
        self._dir = Path(directory or os.environ.get("SCENARIOS_DIR", "./scenarios"))

    def _path(self, name: str) -> Path | None:
        if not _NAME_RE.match(name or ""):
            return None
        return self._dir / f"{name}.yaml"

    def list(self) -> list[dict]:
        """Saved scenarios as {name, title, beats} — newest first, skip broken."""
        if not self._dir.exists():
            return []
        out: list[dict] = []
        for f in self._dir.glob("*.yaml"):
            try:
                sc = Scenario.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
                out.append({"name": f.stem, "title": sc.title, "beats": len(sc.beats),
                            "mtime": f.stat().st_mtime})
            except Exception as exc:  # noqa: BLE001 — a bad file must not hide the rest
                logger.warning("scenario %s unreadable: %s", f, exc)
        out.sort(key=lambda s: s["mtime"], reverse=True)
        for s in out:
            s.pop("mtime", None)
        return out

    def get_yaml(self, name: str) -> str | None:
        path = self._path(name)
        if path is None or not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save(self, name: str, *, raw_yaml: str | None = None,
             scenario: Scenario | None = None) -> tuple[str, Scenario]:
        """Validate and write. Give either raw YAML (power users) or a validated
        Scenario (the builder). Returns (name, scenario). Raises ValueError on an
        invalid name or scenario — we never persist something that can't run."""
        name = name if _NAME_RE.match(name or "") else slugify(name)
        if scenario is None:
            try:
                scenario = Scenario.model_validate(yaml.safe_load(raw_yaml or ""))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"invalid scenario: {exc}") from exc
        # Serialise the VALIDATED model, not the raw text, so a builder save and
        # a YAML save produce the same clean file.
        text = raw_yaml if raw_yaml is not None else yaml.safe_dump(
            scenario.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True)
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / f"{name}.yaml").write_text(text, encoding="utf-8")
        return name, scenario

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path is None or not path.exists():
            return False
        path.unlink()
        return True
