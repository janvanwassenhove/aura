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
# U96: the store is only GATED after an explicit POST /knowledge/lock. On a
# fresh start the owner's own profiles are always readable (no confusing
# "everything vanished" benign wall). Unlock / restart clears this.
_explicitly_locked: bool = False


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
    global _omk_loaded, _tier, _explicitly_locked
    _omk_loaded = loaded
    if loaded:
        _tier = UnlockTier.SENSITIVE
        _explicitly_locked = False


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
    if _omk_loaded and _explicitly_locked:
        raise HTTPException(
            status_code=403,
            detail="Knowledge locked. POST /knowledge/unlock with the passphrase.",
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
    # U63: this person's SKILLS (their way of working, part of the digital
    # twin) live in the skill store — referenced here so the profile is the
    # one place that shows everything AURA knows about someone.
    skills: list[dict] = []
    try:
        from aura_brain import skills_api

        skill_store = skills_api.get_store()
        if skill_store is not None:
            # Scoped skills (their way of working) + skills that MENTION this
            # person via an Obsidian-style [[link]] in their body (U68).
            mention = f"[[{person_id}]]".lower()
            skills = [
                {"name": sk.name, "description": sk.description,
                 "enabled": sk.enabled,
                 "via": "scope" if sk.person == person_id else "mention"}
                for sk in skill_store.all()
                if sk.person == person_id or mention in sk.body.lower()
            ]
    except Exception:  # noqa: BLE001 — skills are optional context
        skills = []
    return JSONResponse({
        "person": person.model_dump(mode="json"),
        "facts": [f.model_dump(mode="json") for f in facts],
        "signals": [s.model_dump(mode="json") for s in signals],
        "skills": skills,
    })


@router.put("/people/{person_id}")
async def upsert_person(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    store = _require()
    existing = await store.get_person(person_id)
    # Merge semantics (U63): omitted fields keep their current value so the
    # console can update just the description without resetting name/role.
    defaults = {
        "display_name": existing.display_name if existing else person_id,
        "role": existing.role.value if existing else "guest",
        "description": existing.description if existing else "",
    }
    try:
        role = PersonRole(body.get("role") or defaults["role"])
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid role")
    person = Person(
        person_id=person_id,
        display_name=body.get("display_name") or defaults["display_name"],
        role=role,
        description=body.get("description", defaults["description"]) or "",
    )
    await store.upsert_person(person)
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


@router.post("/people/{person_id}/ingest")
async def ingest_sources(
    person_id: str,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U103: grow the persona graph — read this person's fetchable sources
    (blog/website/github) and distill them into [[linked]] profile facts."""
    from aura_brain.source_ingest import ingest_person_sources

    result = await ingest_person_sources(_require(), person_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(result)


@router.post("/people/{person_id}/import-chats")
async def import_chats(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U104: mine a ChatGPT/Claude data-export for facts about this person.

    Body: {"export": <parsed conversations.json>} — the console reads the
    file locally and posts its content; nothing is sent anywhere else."""
    from aura_brain.brain_transfer import import_chat_export

    payload = (body or {}).get("export")
    if payload is None:
        raise HTTPException(status_code=422, detail="export (conversations.json content) is required")
    result = await import_chat_export(_require(), person_id, payload)
    if result.get("error", "").startswith("unknown person"):
        raise HTTPException(status_code=404, detail=result["error"])
    if "error" in result and not result.get("added"):
        raise HTTPException(status_code=422, detail=result["error"])
    return JSONResponse(result)


@router.get("/export")
async def export_brain(_: None = Depends(_require_sensitive)) -> JSONResponse:
    """U104: one honest JSON dump of everything AURA knows (people/facts/signals)."""
    from aura_brain.brain_transfer import export_knowledge

    return JSONResponse(await export_knowledge(_require()))


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
    """Drop to BENIGN tier (logical lock). Unlock via POST /knowledge/unlock."""
    global _tier, _explicitly_locked
    _tier = UnlockTier.BENIGN
    _explicitly_locked = True
    return JSONResponse({"tier": UnlockTier.BENIGN, "locked": True})


@router.post("/unlock")
async def unlock_knowledge(body: dict) -> JSONResponse:
    """U94: re-elevate to SENSITIVE by re-entering the knowledge passphrase.

    Verifies the passphrase by deriving the OMK (same salt) and comparing it to
    the store's loaded key — wrong passphrase never elevates, and the passphrase
    is never logged or stored."""
    global _tier, _explicitly_locked
    import os

    if not _omk_loaded:
        # Dev mode (no encryption) — nothing to unlock.
        _tier = UnlockTier.SENSITIVE
        _explicitly_locked = False
        return JSONResponse({"tier": _tier, "unlocked": True})
    passphrase = str((body or {}).get("passphrase", ""))
    if len(passphrase) < 1:
        return JSONResponse({"error": "passphrase required"}, status_code=422)
    store_omk = getattr(_store, "_omk", None)
    if store_omk is None:
        return JSONResponse({"error": "store has no key"}, status_code=500)
    from shared_schemas.knowledge import crypto

    salt = os.environ.get("KNOWLEDGE_SALT", "aura-knowledge").encode().ljust(16, b"0")[:16]
    if crypto.derive_omk(passphrase, salt) != store_omk:
        return JSONResponse({"error": "wrong passphrase"}, status_code=403)
    _tier = UnlockTier.SENSITIVE
    _explicitly_locked = False
    return JSONResponse({"tier": _tier, "unlocked": True})


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
