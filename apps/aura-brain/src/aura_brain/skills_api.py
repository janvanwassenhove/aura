"""U59: skills CRUD — the owner manages what the agent has been taught.

Skills are markdown files (see orchestrator.skills). This API lets the console
list, inspect, create/update, toggle and delete them. Writing skills through
the AGENT (self-training, U60) goes through the approval gate; the owner
editing their own skills here does not — the owner IS the authority.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from orchestrator.skills import Skill, SkillStore

router = APIRouter(prefix="/skills", tags=["skills"])

_store: SkillStore | None = None


def init(store: SkillStore) -> None:
    global _store
    _store = store


def get_store() -> SkillStore | None:
    return _store


def _dump(skill: Skill) -> dict:
    return {
        "name": skill.name,
        "description": skill.description,
        "triggers": skill.triggers,
        "personas": skill.personas,
        "person": skill.person,
        "enabled": skill.enabled,
        "body": skill.body,
    }


@router.get("")
async def list_skills() -> JSONResponse:
    if _store is None:
        return JSONResponse({"skills": []})
    return JSONResponse({"skills": [_dump(s) for s in _store.all()]})


@router.get("/suggestions")
async def optimization_suggestions() -> JSONResponse:
    """U108: skills that have accumulated enough new usage signals to be worth
    re-optimizing. Threshold via SKILL_OPTIMIZE_THRESHOLD (default 8). This is
    the proactive trigger — the console surfaces it so the owner doesn't have
    to remember to click Optimize. (Declared before /{name} so it isn't
    swallowed by that path parameter.)"""
    import os

    if _store is None:
        return JSONResponse({"suggestions": [], "threshold": 0})
    threshold = max(1, int(os.environ.get("SKILL_OPTIMIZE_THRESHOLD", "8")))
    out = []
    for skill in _store.all():
        m = _store.metrics(skill.name)
        if m["new_since_optimized"] >= threshold:
            out.append({"name": skill.name, "description": skill.description, **m})
    out.sort(key=lambda s: s["new_since_optimized"], reverse=True)
    return JSONResponse({"suggestions": out, "threshold": threshold})


@router.get("/{name}")
async def get_skill(name: str) -> JSONResponse:
    skill = _store.get(name) if _store else None
    if skill is None:
        return JSONResponse({"error": f"unknown skill {name!r}"}, status_code=404)
    return JSONResponse(_dump(skill))


@router.post("")
async def save_skill(body: dict) -> JSONResponse:
    if _store is None:
        return JSONResponse({"error": "skills not initialised"}, status_code=503)
    body = body or {}
    try:
        skill = Skill(
            name=str(body.get("name", "")).strip().lower(),
            description=str(body.get("description", "")).strip(),
            triggers=[str(t).strip().lower() for t in body.get("triggers", []) if str(t).strip()],
            personas=[str(p).strip().lower() for p in body.get("personas", []) if str(p).strip()],
            person=str(body.get("person", "")).strip(),
            enabled=bool(body.get("enabled", True)),
            body=str(body.get("body", "")),
        )
        _store.save(skill)
        # U107: applying an optimization resets the "new signals" counter.
        if body.get("mark_optimized"):
            _store.mark_optimized(skill.name)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse(_dump(skill))


@router.get("/{name}/metrics")
async def skill_metrics(name: str) -> JSONResponse:
    """U107: usage counts for a skill (uses, new signals since last optimize)."""
    if _store is None or _store.get(name) is None:
        return JSONResponse({"error": f"unknown skill {name!r}"}, status_code=404)
    return JSONResponse(_store.metrics(name))


@router.post("/{name}/optimize")
async def optimize_skill(name: str, body: dict | None = None) -> JSONResponse:
    """U107: propose (never save) a rewrite of the skill body for optimal
    execution, based on accumulated usage evidence + an optional owner hint.
    The owner reviews the diff and applies it via POST /skills."""
    if _store is None or _store.get(name) is None:
        return JSONResponse({"error": f"unknown skill {name!r}"}, status_code=404)
    from orchestrator.config import model_for_role
    from orchestrator.llm import openai_chat
    from orchestrator.skill_optimizer import propose_optimization

    result = await propose_optimization(
        _store, name, openai_chat,
        hint=str((body or {}).get("hint", "")),
        model=model_for_role("agent"),
    )
    if "error" in result:
        return JSONResponse(result, status_code=422)
    return JSONResponse(result)


@router.delete("/{name}")
async def delete_skill(name: str) -> JSONResponse:
    if _store is None:
        return JSONResponse({"error": "skills not initialised"}, status_code=503)
    if not _store.delete(name):
        return JSONResponse({"error": f"unknown skill {name!r}"}, status_code=404)
    return JSONResponse({"deleted": name})
