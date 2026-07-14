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
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    return JSONResponse(_dump(skill))


@router.delete("/{name}")
async def delete_skill(name: str) -> JSONResponse:
    if _store is None:
        return JSONResponse({"error": "skills not initialised"}, status_code=503)
    if not _store.delete(name):
        return JSONResponse({"error": f"unknown skill {name!r}"}, status_code=404)
    return JSONResponse({"deleted": name})
