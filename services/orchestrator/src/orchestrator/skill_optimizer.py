"""U107: self-optimizing skills — rewrite a skill for optimal execution.

A skill (U59) is a procedure the owner taught the agent. Every time it is
used, the SkillStore records an observation (the request + context). This
module turns that accumulated evidence into a PROPOSED rewrite: tighter,
better-ordered steps with guardrails for the request patterns actually seen —
the "agentic learning loop".

The loop is owner-in-the-loop by design: ``propose_optimization`` never
writes. It returns the current body, a proposed body, and a rationale; the
console shows the diff and the owner approves it via the normal save path
(which then calls ``store.mark_optimized``). No unattended self-modification.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

ChatFn = Callable[..., Awaitable[dict]]

_OPTIMIZE_PROMPT = """\
You optimize a reusable "skill" — a step-by-step procedure an AI assistant
follows to execute a recurring task well. You are given the current skill and
real evidence of how it has been used.

Rewrite ONLY the body (the numbered procedure) so the assistant executes it
more reliably and efficiently. Concretely:
- Order steps so prerequisites come first; remove redundancy and dead steps.
- Make each step imperative, specific, and checkable.
- Add short guardrails for the failure/edge cases implied by the usage evidence.
- Keep the skill's ORIGINAL intent and scope — do not invent unrelated features.
- Preserve any [[wiki-links]] to people or other skills.
- Same language as the current body.

Current skill "{name}" — {description}
Current body:
---
{body}
---

Usage evidence ({n} recent uses):
{evidence}
{hint}

Return ONLY a JSON object:
{{"changed": true|false, "rationale": "<=2 sentences on what you improved and why",
  "body": "<the rewritten procedure, or the original if nothing should change>"}}
"""


def summarize_observations(obs: list[dict], limit: int = 40) -> str:
    """Compact, model-friendly digest of how a skill has been used."""
    if not obs:
        return "(no recorded uses yet)"
    recent = obs[-limit:]
    reqs = [str(o.get("request", "")).strip() for o in recent if o.get("request")]
    personas = Counter(str(o.get("persona", "")) for o in recent if o.get("persona"))
    people = Counter(str(o.get("person", "")) for o in recent if o.get("person"))
    lines = []
    if personas:
        lines.append("modes: " + ", ".join(f"{k}×{v}" for k, v in personas.most_common()))
    if people:
        lines.append("people: " + ", ".join(f"{k}×{v}" for k, v in people.most_common()))
    lines.append("recent requests:")
    for r in reqs[-20:]:
        lines.append(f"  - {r[:160]}")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict | None:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Salvage the first {...} block if the model wrapped it in prose.
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


_POLISH_PROMPT = """\
You polish a freshly written "skill" — a step-by-step procedure an AI
assistant will follow to execute a recurring task. The owner just wrote it in
rough form; rewrite ONLY the body so the assistant executes it reliably:
- Numbered, imperative, specific, checkable steps; prerequisites first.
- Keep the owner's intent and every concrete detail (URLs, app names, names);
  do not invent new capabilities.
- Preserve [[wiki-links]]. Same language as the draft.

Skill "{name}" — {description}
Draft body:
---
{body}
---

Return ONLY a JSON object:
{{"changed": true|false, "rationale": "<=1 sentence",
  "body": "<the polished procedure, or the draft if already clean>"}}
"""


async def polish_draft(
    name: str,
    description: str,
    body: str,
    chat_fn: ChatFn,
    *,
    model: str | None = None,
) -> dict:
    """U118: rewrite a just-written skill body for optimal execution (no usage
    evidence yet — pure writing quality). Never saves anything itself."""
    prompt = _POLISH_PROMPT.format(
        name=name or "unnamed", description=description or "(no description)",
        body=body or "(empty)",
    )
    try:
        resp = await chat_fn([{"role": "user", "content": prompt}], model=model)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"polish failed ({type(exc).__name__})"}
    data = _extract_json(resp.get("content") or "")
    if not data or "body" not in data:
        return {"error": "the model did not return a usable rewrite"}
    polished = str(data["body"]).strip()
    return {
        "changed": bool(data.get("changed", True)) and polished != body.strip(),
        "rationale": str(data.get("rationale", "")).strip(),
        "body": polished or body,
    }


async def propose_optimization(
    store: Any,
    name: str,
    chat_fn: ChatFn,
    *,
    hint: str = "",
    model: str | None = None,
) -> dict:
    """Propose (never save) an optimized body for skill ``name``.

    Returns {name, changed, rationale, current_body, proposed_body, based_on}
    or {error} if the skill is unknown / the model output was unusable.
    """
    skill = store.get(name)
    if skill is None:
        return {"error": f"unknown skill {name!r}"}
    obs = store.observations(name)
    evidence = summarize_observations(obs)
    hint_line = f"\nOwner's note on what to improve: {hint.strip()}" if hint.strip() else ""
    prompt = _OPTIMIZE_PROMPT.format(
        name=skill.name, description=skill.description or "(no description)",
        body=skill.body or "(empty)", n=len(obs), evidence=evidence, hint=hint_line,
    )
    try:
        resp = await chat_fn([{"role": "user", "content": prompt}], model=model)
    except Exception as exc:  # noqa: BLE001 — offline, no key, quota, …
        return {"error": f"optimization failed ({type(exc).__name__})"}
    data = _extract_json(resp.get("content") or "")
    if not data or "body" not in data:
        return {"error": "the model did not return a usable rewrite"}

    proposed = str(data["body"]).strip()
    changed = bool(data.get("changed", True)) and proposed != (skill.body or "").strip()
    return {
        "name": skill.name,
        "changed": changed,
        "rationale": str(data.get("rationale", "")).strip(),
        "current_body": skill.body,
        "proposed_body": proposed,
        "based_on": len(obs),
    }
