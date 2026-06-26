"""Knowledge transparency API (U19d backend, ADR-008 §7).

The owner can *see exactly what AURA knows* about each person, edit it, and delete
it (right-to-be-forgotten). This is the REST backend the operator-console
transparency view drives; the Vue view itself is front-end work left for review.

NOTE: owner-gating of these endpoints (only the authenticated owner may read
sensitive profiles) is U19c (🔒 DECIDE — ADR-008 §9). Until that lands, deploy the
brain bound to localhost only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from shared_schemas.knowledge import (
    ConsentError,
    ConsentRecord,
    KnowledgeStore,
    Person,
    PersonRole,
    ProfileFact,
)

router = APIRouter(prefix="/knowledge")

_store: KnowledgeStore | None = None


def set_store(store: KnowledgeStore) -> None:
    global _store
    _store = store


def _require() -> KnowledgeStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Knowledge store not initialised")
    return _store


@router.get("/people")
async def list_people() -> JSONResponse:
    people = await _require().list_people()
    return JSONResponse([p.model_dump(mode="json") for p in people])


@router.get("/people/{person_id}")
async def inspect_person(person_id: str) -> JSONResponse:
    """Everything AURA knows about a person — facts + observed signals."""
    store = _require()
    person = await store.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Unknown person {person_id!r}")
    facts = await store.get_facts(person_id)
    signals = await store.get_signals(person_id)
    return JSONResponse({
        "person": person.model_dump(mode="json"),
        "facts": [f.model_dump(mode="json") for f in facts],
        "signals": [s.model_dump(mode="json") for s in signals],
    })


@router.put("/people/{person_id}")
async def upsert_person(person_id: str, body: dict) -> JSONResponse:
    try:
        role = PersonRole(body.get("role", "guest"))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid role")
    person = Person(
        person_id=person_id,
        display_name=body.get("display_name", person_id),
        role=role,
    )
    await _require().upsert_person(person)
    return JSONResponse(person.model_dump(mode="json"))


@router.delete("/people/{person_id}")
async def forget_person(person_id: str) -> JSONResponse:
    """Right-to-be-forgotten: erase the person and all their data."""
    await _require().delete_person(person_id)
    return JSONResponse({"deleted": person_id})


@router.post("/people/{person_id}/facts")
async def add_fact(person_id: str, body: dict) -> JSONResponse:
    key, value = body.get("key"), body.get("value")
    if not key or value is None:
        raise HTTPException(status_code=422, detail="key and value are required")
    fact = await _require().add_fact(ProfileFact(person_id=person_id, key=key, value=str(value)))
    return JSONResponse(fact.model_dump(mode="json"))


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: str) -> JSONResponse:
    await _require().delete_fact(fact_id)
    return JSONResponse({"deleted": fact_id})


@router.post("/people/{person_id}/consent")
async def set_consent(person_id: str, body: dict) -> JSONResponse:
    rec = ConsentRecord(
        person_id=person_id,
        granted_by=body.get("granted_by", "owner"),
        scope=body.get("scope", "observed_learning"),
    )
    try:
        await _require().set_consent(rec)
    except ConsentError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return JSONResponse(rec.model_dump(mode="json"))
