"""Knowledge transparency API (U19d backend, ADR-008 §7) + owner-unlock tiers (U19c, ADR-008 §9).

Owner-unlock tiers
------------------
BENIGN   — no OMK configured (dev/in-memory mode).  All endpoints accessible.
SENSITIVE — OMK is loaded (KNOWLEDGE_PASSPHRASE set).  All read/write endpoints
            accessible while the brain process is running under the owner's session.
            POST /knowledge/lock drops to BENIGN (logical lock; restart or set
            KNOWLEDGE_PASSPHRASE again to restore SENSITIVE).
STEP_UP  — destructive operations (delete person, delete fact) always require a
            possession-factor step-up via STEP_UP_WEBHOOK_URL.  If that env var is
            not set the operation is denied.

NOTE: when KNOWLEDGE_PASSPHRASE is not set (in-memory dev store) no tier gating
is applied — all endpoints function as before, preserving backward compatibility
with tests.
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from aura_brain.stepup_gate import StepUpDeniedError, StepUpGate, StepUpTimeout
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
_stepup_gate: StepUpGate | None = None

# Tier state — mutated at startup (set_omk_loaded) and by POST /knowledge/lock.
class UnlockTier(StrEnum):
    BENIGN = "benign"
    SENSITIVE = "sensitive"


_omk_loaded: bool = False
_tier: UnlockTier = UnlockTier.BENIGN


# ------------------------------------------------------------------
# Setters (called from main.py at startup)
# ------------------------------------------------------------------

def set_store(store: KnowledgeStore) -> None:
    global _store
    _store = store


def set_stepup_gate(gate: StepUpGate) -> None:
    global _stepup_gate
    _stepup_gate = gate


def set_omk_loaded(loaded: bool) -> None:
    """Signal whether the EncryptedKnowledgeStore is active (KNOWLEDGE_PASSPHRASE set)."""
    global _omk_loaded, _tier
    _omk_loaded = loaded
    if loaded:
        _tier = UnlockTier.SENSITIVE


def is_omk_loaded() -> bool:
    return _omk_loaded


# ------------------------------------------------------------------
# Tier helpers
# ------------------------------------------------------------------

def _require() -> KnowledgeStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="Knowledge store not initialised")
    return _store


def _require_sensitive() -> None:
    """FastAPI dependency: 403 when the store is encrypted but the tier is BENIGN (locked)."""
    if _omk_loaded and _tier == UnlockTier.BENIGN:
        raise HTTPException(
            status_code=403,
            detail="Knowledge locked. POST /knowledge/lock to unlock (restart with KNOWLEDGE_PASSPHRASE).",
        )


async def _require_stepup(operation: str, context: dict) -> None:
    """Require a phone step-up for destructive operations.

    No-op when OMK is not loaded (dev mode, nothing to protect).
    Auto-denies when STEP_UP_WEBHOOK_URL is not set.
    """
    if not _omk_loaded:
        return
    if _stepup_gate is None:
        raise HTTPException(status_code=503, detail="Step-up gate not wired")
    try:
        await _stepup_gate.request(operation, context)
    except StepUpDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except StepUpTimeout as exc:
        raise HTTPException(status_code=408, detail=str(exc))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/people")
async def list_people(_: None = Depends(_require_sensitive)) -> JSONResponse:
    people = await _require().list_people()
    return JSONResponse([p.model_dump(mode="json") for p in people])


@router.get("/people/{person_id}")
async def inspect_person(person_id: str, _: None = Depends(_require_sensitive)) -> JSONResponse:
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
async def upsert_person(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
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
    """Right-to-be-forgotten: step-up required (destructive, ADR-008 §9)."""
    await _require_stepup("delete_person", {"person_id": person_id})
    await _require().delete_person(person_id)
    return JSONResponse({"deleted": person_id})


@router.post("/people/{person_id}/facts")
async def add_fact(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    key, value = body.get("key"), body.get("value")
    if not key or value is None:
        raise HTTPException(status_code=422, detail="key and value are required")
    fact = await _require().add_fact(ProfileFact(person_id=person_id, key=key, value=str(value)))
    return JSONResponse(fact.model_dump(mode="json"))


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: str) -> JSONResponse:
    """Delete a fact: step-up required (destructive, ADR-008 §9)."""
    await _require_stepup("delete_fact", {"fact_id": fact_id})
    await _require().delete_fact(fact_id)
    return JSONResponse({"deleted": fact_id})


@router.post("/people/{person_id}/consent")
async def set_consent(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
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


# ------------------------------------------------------------------
# Tier management
# ------------------------------------------------------------------

@router.post("/lock")
async def lock_knowledge() -> JSONResponse:
    """Drop to BENIGN tier (logical lock). Restart brain with KNOWLEDGE_PASSPHRASE to restore."""
    global _tier
    _tier = UnlockTier.BENIGN
    return JSONResponse({"tier": UnlockTier.BENIGN, "locked": True})


@router.get("/tier")
async def get_tier() -> JSONResponse:
    """Return the current unlock tier and whether encryption is active."""
    return JSONResponse({"tier": _tier, "omk_loaded": _omk_loaded})


# ------------------------------------------------------------------
# Step-up callbacks (called by the paired phone or webhook recipient)
# ------------------------------------------------------------------

@router.post("/stepup/callback/{token}/grant")
async def stepup_grant(token: str) -> JSONResponse:
    """Resolve a pending step-up request as granted."""
    if _stepup_gate is None:
        raise HTTPException(status_code=503, detail="Step-up gate not wired")
    found = _stepup_gate.resolve(token, granted=True)
    if not found:
        raise HTTPException(status_code=404, detail=f"Unknown or expired token {token!r}")
    return JSONResponse({"token": token, "granted": True})


@router.post("/stepup/callback/{token}/deny")
async def stepup_deny(token: str) -> JSONResponse:
    """Resolve a pending step-up request as denied."""
    if _stepup_gate is None:
        raise HTTPException(status_code=503, detail="Step-up gate not wired")
    found = _stepup_gate.resolve(token, granted=False)
    if not found:
        raise HTTPException(status_code=404, detail=f"Unknown or expired token {token!r}")
    return JSONResponse({"token": token, "granted": False})
