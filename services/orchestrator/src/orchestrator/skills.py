"""U59: skills — owner-taught procedures the agent follows and refines.

A skill is one markdown file in ``SKILLS_DIR`` (default ``./skills``):

    ---
    name: presenting-with-jan
    description: How Jan wants presentations to run
    triggers: presentation, slides, deck
    personas: work, presentation
    person: jan
    enabled: true
    ---
    1. Open the deck in the browser first.
    2. Jan announces the slide; wait for his nod before advancing.

Frontmatter is deliberately tiny (``key: value`` lines, comma-separated
lists) — no YAML dependency. ``person`` scopes a skill to one person's
digital twin; ``personas`` limits it to modes; ``triggers`` are substrings
matched against the user's request (no triggers → always relevant).

The store is file-backed and reloaded lazily so external edits (or the
self-training flow, U60) are picked up without restarts.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_INJECTED = 3          # full skill bodies per turn
_MAX_BODY = 2000           # chars per injected body
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MAX_OBS = 200             # U107: usage observations kept per skill


@dataclass
class Skill:
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)  # empty → all modes
    person: str = ""                                   # empty → everyone
    enabled: bool = True
    body: str = ""

    def to_markdown(self) -> str:
        lines = ["---", f"name: {self.name}", f"description: {self.description}"]
        if self.triggers:
            lines.append("triggers: " + ", ".join(self.triggers))
        if self.personas:
            lines.append("personas: " + ", ".join(self.personas))
        if self.person:
            lines.append(f"person: {self.person}")
        lines.append(f"enabled: {'true' if self.enabled else 'false'}")
        lines.append("---")
        return "\n".join(lines) + "\n" + self.body.strip() + "\n"

    def matches(self, text: str, persona: str, person_id: str | None) -> bool:
        if not self.enabled:
            return False
        if self.personas and persona not in self.personas:
            return False
        if self.person and self.person != (person_id or ""):
            return False
        if self.triggers:
            lower = text.lower()
            return any(t in lower for t in self.triggers)
        return True


def _parse(text: str, fallback_name: str) -> Skill:
    body = text
    meta: dict[str, str] = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                key, _, value = line.partition(":")
                key, value = key.strip().lower(), value.strip()
                if key and value:
                    meta[key] = value
            body = parts[2]
    split = [s.strip() for s in meta.get("triggers", "").split(",") if s.strip()]
    personas = [s.strip().lower() for s in meta.get("personas", "").split(",") if s.strip()]
    return Skill(
        name=meta.get("name", fallback_name),
        description=meta.get("description", ""),
        triggers=[t.lower() for t in split],
        personas=personas,
        person=meta.get("person", ""),
        enabled=meta.get("enabled", "true").lower() != "false",
        body=body.strip(),
    )


class SkillStore:
    def __init__(self, directory: str | None = None) -> None:
        self._dir = Path(directory or os.environ.get("SKILLS_DIR", "./skills"))
        self._skills: dict[str, Skill] = {}
        self._loaded_at = 0.0

    # -- loading --------------------------------------------------------

    def _reload_if_stale(self) -> None:
        try:
            mtime = self._dir.stat().st_mtime if self._dir.exists() else 0.0
        except OSError:
            mtime = 0.0
        if mtime <= self._loaded_at and self._skills:
            return
        self._skills = {}
        if self._dir.exists():
            for f in sorted(self._dir.glob("*.md")):
                if f.name.lower() == "readme.md":  # vault doc, not a skill (U68)
                    continue
                try:
                    skill = _parse(f.read_text(encoding="utf-8"), f.stem)
                    self._skills[skill.name] = skill
                except OSError as exc:
                    logger.warning("skill %s unreadable: %s", f, exc)
        self._loaded_at = time.time()

    # -- queries ----------------------------------------------------------

    def all(self) -> list[Skill]:
        self._reload_if_stale()
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get(self, name: str) -> Skill | None:
        self._reload_if_stale()
        return self._skills.get(name)

    def relevant(self, text: str, persona: str, person_id: str | None) -> list[Skill]:
        return [s for s in self.all() if s.matches(text, persona, person_id)]

    def prompt_block(self, text: str, persona: str, person_id: str | None) -> str:
        """The skills section for the system prompt: full body for relevant
        skills (capped), one-line mentions for the rest."""
        skills = self.all()
        training_note = (
            "SELF-TRAINING: when the owner corrects your approach or shows you "
            "their way of working, propose saving it with the save_skill tool "
            "(the owner approves every write)."
        )
        if not skills:
            return training_note
        relevant = self.relevant(text, persona, person_id)[:_MAX_INJECTED]
        lines = ["SKILLS — procedures the owner taught you. Follow a relevant "
                 "skill exactly; mention which skill you're using. " + training_note]
        for s in relevant:
            lines.append(f"\n## Skill: {s.name} — {s.description}\n{s.body[:_MAX_BODY]}")
        others = [s for s in skills if s.enabled and s not in relevant]
        if others:
            listing = "; ".join(f"{s.name} ({s.description})" for s in others[:10])
            lines.append(f"\nOther available skills: {listing}.")
        return "\n".join(lines)

    # -- mutations (CRUD API + self-training, U60) ------------------------

    _VAULT_README = (
        "# AURA brain vault\n\n"
        "Every `.md` file here is one skill the owner taught the assistant.\n"
        "This folder is a plain markdown vault — open it in Obsidian if you\n"
        "like: `[[person-id]]` / `[[skill-name]]` links work there AND render\n"
        "as clickable links in the AURA app (with backlinks on the person's\n"
        "profile). Person data itself is NOT stored here — profiles stay\n"
        "encrypted inside the app (see docs/user-guide.md).\n"
    )

    def save(self, skill: Skill) -> Skill:
        if not _NAME_RE.match(skill.name):
            raise ValueError("name must be kebab-case: a-z, 0-9 and dashes (max 64)")
        self._dir.mkdir(parents=True, exist_ok=True)
        readme = self._dir / "README.md"
        if not readme.exists():  # U68: make the vault self-describing
            readme.write_text(self._VAULT_README, encoding="utf-8")
        path = self._dir / f"{skill.name}.md"
        path.write_text(skill.to_markdown(), encoding="utf-8")
        self._loaded_at = 0.0  # force reload
        logger.info("skill saved: %s", skill.name)
        return skill

    def delete(self, name: str) -> bool:
        path = self._dir / f"{name}.md"
        if not path.exists():
            return False
        path.unlink()
        self._loaded_at = 0.0
        for side in (self._obs_path(name), self._opt_path(name)):
            side.unlink(missing_ok=True)
        logger.info("skill deleted: %s", name)
        return True

    # -- U107: usage observations → self-optimizing loop -----------------
    #
    # Every time a skill is injected into a turn we append one observation
    # (the request + context). Accumulated evidence drives skill_optimizer,
    # which rewrites the body for optimal execution — the owner approves the
    # rewrite (a normal save), keeping the "no unattended writes" invariant.

    @property
    def _metrics_dir(self) -> Path:
        return self._dir / ".metrics"

    def _obs_path(self, name: str) -> Path:
        return self._metrics_dir / f"{name}.jsonl"

    def _opt_path(self, name: str) -> Path:
        # Records the observation count at the last optimization, so the UI
        # can surface "N new signals since you last optimized this skill".
        return self._metrics_dir / f"{name}.optimized"

    def record_observation(self, name: str, obs: dict) -> None:
        """Append one usage observation. Best-effort — never raises into a turn."""
        try:
            self._metrics_dir.mkdir(parents=True, exist_ok=True)
            path = self._obs_path(name)
            entry = {"ts": round(time.time()), **obs}
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Cap: keep only the most recent _MAX_OBS lines.
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) > _MAX_OBS:
                path.write_text("\n".join(lines[-_MAX_OBS:]) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.debug("skill observation not recorded for %s: %s", name, exc)

    def observations(self, name: str) -> list[dict]:
        path = self._obs_path(name)
        if not path.exists():
            return []
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def mark_optimized(self, name: str) -> None:
        try:
            self._metrics_dir.mkdir(parents=True, exist_ok=True)
            self._opt_path(name).write_text(str(len(self.observations(name))), encoding="utf-8")
        except OSError as exc:
            logger.debug("skill optimize-marker not written for %s: %s", name, exc)

    def metrics(self, name: str) -> dict:
        """Lightweight counts for the UI: total uses and new since last optimize."""
        obs = self.observations(name)
        prev = 0
        try:
            prev = int(self._opt_path(name).read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            prev = 0
        last_ts = obs[-1]["ts"] if obs else None
        return {
            "uses": len(obs),
            "new_since_optimized": max(0, len(obs) - prev),
            "last_used": last_ts,
        }
