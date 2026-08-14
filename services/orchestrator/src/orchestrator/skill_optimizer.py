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
from collections.abc import Awaitable, Callable
from typing import Any

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
    """Compact, model-friendly digest of how a skill has been used.

    U247: this used to report only what was ASKED — modes, people, request
    texts — and the prompt then asked for "guardrails for the failure cases
    implied by the usage evidence" against evidence in which nothing ever
    failed. Observations now carry the tools a turn ran and the capabilities
    that came back unavailable, and the failures lead, because a step that dies
    the same way every time is the single most useful thing a rewrite can act
    on.
    """
    if not obs:
        return "(no recorded uses yet)"
    recent = obs[-limit:]
    reqs = [str(o.get("request", "")).strip() for o in recent if o.get("request")]
    personas = Counter(str(o.get("persona", "")) for o in recent if o.get("persona"))
    people = Counter(str(o.get("person", "")) for o in recent if o.get("person"))
    missing = Counter(
        cap for o in recent for cap in (o.get("unavailable") or []) if cap)
    tools = Counter(t for o in recent for t in (o.get("tools") or []) if t)
    steers = [str(s2)[:200] for o in recent for s2 in (o.get("steering") or []) if s2]
    lines = [f"uses: {len(recent)}"]
    if steers:
        # U249: the owner correcting a running turn is the strongest evidence
        # there is — they are saying, in their own words, how this should have
        # gone. It used to steer the turn and evaporate.
        lines.append("THE OWNER CORRECTED YOU MID-RUN — take these literally:")
        for s2 in steers[-5:]:
            lines.append(f"  - \"{s2}\"")
        lines.append("  Fold these into the procedure so they do not have to "
                     "say it again.")
    if missing:
        lines.append("UNAVAILABLE — these uses could not complete:")
        for cap, n in missing.most_common():
            lines.append(
                f"  - {cap}: {n} of {len(recent)} uses hit this and stopped there")
        lines.append(
            "  Treat this as the main thing to fix: prefer a route that does "
            "not need it, and if there is none, say so plainly instead of "
            "half-executing.")
    if tools:
        lines.append("tools used: " + ", ".join(f"{k}×{v}" for k, v in tools.most_common()))
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


_NEW_SKILL_PROMPT = """\
You draft a new "skill" — a step-by-step procedure an AI assistant will follow
for a task its owner keeps asking for and which no existing procedure covers.

Here are the real requests, in the owner's own words, that nothing handled:
{examples}

{failures}
Existing skills (do NOT duplicate one; if the topic really belongs in one of
these, say so instead of drafting):
{existing}

Available tools, in the order the assistant should prefer them:
{tools}

Write the procedure the assistant should have followed. Rules:
- Numbered, imperative, specific, checkable steps; prerequisites first.
- Use tools that EXIST. Never invent a capability, and never describe a step
  the assistant cannot actually take.
- If a step needs something that is currently unavailable, say what to do
  instead AND that the assistant should ask the owner for it.
- Same language the owner used.
- Keep it short. A procedure nobody reads is worse than none.

Return ONLY a JSON object:
{{"worth_adding": true|false,
  "name": "<kebab-case, max 64 chars>",
  "description": "<one line, what this is for>",
  "triggers": ["<word or phrase that should activate it>", ...],
  "body": "<the numbered procedure>",
  "rationale": "<=2 sentences: why this deserves to exist>"}}
"""


async def propose_new_skill(
    store: Any,
    examples: list[str],
    chat_fn: ChatFn,
    *,
    tools: str = "",
    model: str | None = None,
) -> dict:
    """U250: draft (never save) a skill for something asked repeatedly that no
    existing skill covers.

    ``worth_adding: false`` is a real answer and the common one — most repeated
    phrasings are conversation, not a procedure. A loop that produces a skill
    every time it is asked would bury the owner in things to approve, which is
    the same failure as never asking at all.
    """
    if not examples:
        return {"error": "nothing to draft from"}
    existing = "\n".join(
        f"  - {s.name}: {s.description}" for s in store.all()) or "  (none yet)"
    unavailable = sorted({
        cap for e in getattr(store, "unmatched", lambda: [])()
        for cap in (e.get("unavailable") or [])})
    failures = (
        "These attempts also ran into something that was not available: "
        + ", ".join(unavailable) + ". Take that into account.\n"
    ) if unavailable else ""
    prompt = _NEW_SKILL_PROMPT.format(
        examples="\n".join(f"  - {e[:160]}" for e in examples[:12]),
        failures=failures, existing=existing, tools=tools or "(not listed)",
    )
    try:
        resp = await chat_fn([{"role": "user", "content": prompt}], model=model)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"draft failed ({type(exc).__name__})"}
    data = _extract_json(resp.get("content") or "")
    if not data:
        return {"error": "the model did not return a usable draft"}
    if not data.get("worth_adding"):
        return {"worth_adding": False,
                "rationale": str(data.get("rationale", "")).strip()}
    body = str(data.get("body", "")).strip()
    name = str(data.get("name", "")).strip().lower()
    if not body or not name:
        return {"error": "the draft had no name or no body"}
    triggers = [str(t).strip().lower() for t in (data.get("triggers") or []) if str(t).strip()]
    return {
        "worth_adding": True,
        "name": name,
        "description": str(data.get("description", "")).strip(),
        "triggers": triggers,
        "body": body,
        "rationale": str(data.get("rationale", "")).strip(),
        "based_on": len(examples),
    }
