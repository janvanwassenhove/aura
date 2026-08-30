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
from shared_schemas.knowledge import (
    ConsentError,
    ConsentRecord,
    KnowledgeStore,
    Person,
    PersonRole,
    ProfileFact,
)

from aura_brain.stepup_gate import StepUpDeniedError, StepUpGate, StepUpTimeout

router = APIRouter(prefix="/knowledge")

_store: KnowledgeStore | None = None
_stepup_gate: StepUpGate | None = None
_recognition_gallery = None  # U127: RecognitionGallery | None


def set_recognition_gallery(gallery) -> None:
    global _recognition_gallery
    _recognition_gallery = gallery

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
_unlock_fails: int = 0          # U221 (S14): failed unlock attempts
_unlock_blocked_until: float = 0.0


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


def _pipeline():
    """The running pipeline, or None outside a full brain (tests)."""
    from aura_brain import main as _main  # noqa: PLC0415 — avoids a cycle

    return getattr(getattr(_main, "ctx", None), "pipeline", None)


@router.get("/speaker")
async def get_speaker() -> JSONResponse:
    """Who the BRAIN thinks it is talking to — and whether it is remembering.

    U276: the header has always let the owner say who is at the desk, and that
    choice never left the browser. `setSpeaker` set a ref in a Pinia store and
    nothing else; the brain's active person came from face recognition alone.
    So with no face taught — which is every fresh profile, and the state the
    owner was actually in — the console showed "Jan · owner" while the brain
    knew nobody, and the memory hook (`if hook and self._active_person_id`)
    never fired. Everything said in that conversation was answered properly
    and then forgotten, silently, while a Memory tab sat there implying
    otherwise. Reported as "ik vertel informatie, maar ik zie dat hij die niet
    gebruikt in zijn kennisopbouw".

    `remembering` is the honest bit: no person, no long-term memory, and the
    console can finally say so instead of leaving the owner to infer it.
    """
    pipeline = _pipeline()
    person_id = getattr(pipeline, "_active_person_id", None) if pipeline else None
    display = ""
    if person_id and _store is not None:
        person = await _store.get_person(person_id)
        display = person.display_name if person else ""
    return JSONResponse({
        "person_id": person_id,
        "display_name": display,
        "remembering": bool(person_id),
    })


@router.post("/speaker")
async def set_speaker(body: dict, _: None = Depends(_require_sensitive)) -> JSONResponse:
    """Tell the brain who it is talking to. `null` means nobody in particular."""
    pipeline = _pipeline()
    if pipeline is None:
        return JSONResponse({"error": "no pipeline"}, status_code=503)
    person_id = (body or {}).get("person_id")
    if person_id in ("", "guest"):
        person_id = None            # a guest is nobody to remember against
    if person_id is not None:
        store = _require()
        if await store.get_person(str(person_id)) is None:
            raise HTTPException(status_code=404, detail=f"Unknown person {person_id!r}")
        person_id = str(person_id)
    pipeline.set_active_person(person_id)
    return await get_speaker()


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
    # U274: build from the STORED person, not from a fresh default one. The
    # merge comment above was only true of the three fields it listed —
    # everything added since (the avatar, and now language and character) was
    # silently reset to its default on any update, so changing someone's role
    # deleted their photo. Starting from what is there cannot forget a field
    # that gets added later.
    base = existing.model_dump() if existing else {
        "person_id": person_id, "display_name": person_id, "role": "guest",
    }
    try:
        role = PersonRole(body.get("role") or base.get("role") or "guest")
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid role")
    updates = {
        "display_name": body.get("display_name") or base.get("display_name") or person_id,
        "role": role,
        "description": body.get("description", base.get("description", "")) or "",
        # Empty is a real choice here — it means "follow the house setting" —
        # so these read with a default rather than an `or`.
        "language": str(body.get("language", base.get("language", "")) or ""),
        "character": str(body.get("character", base.get("character", "")) or ""),
    }
    person = Person(**{**base, "person_id": person_id, **updates})
    await store.upsert_person(person)
    return JSONResponse(person.model_dump(mode="json"))


@router.put("/people/{person_id}/avatar")
async def set_avatar(
    person_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U204: set or clear a person's avatar from an uploaded image.

    `{"image": "data:image/png;base64,..."}` sets it (re-encoded to a small
    square JPEG); `{"clear": true}` removes it so the console falls back to
    initials. Capture-from-camera lives in recognition_api, which has the robot.
    """
    store = _require()
    person = await store.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"unknown person {person_id!r}")

    if (body or {}).get("clear"):
        person.avatar = ""
        await store.upsert_person(person)
        return JSONResponse({"person_id": person_id, "avatar": ""})

    from aura_brain.avatar import avatar_from_data_uri

    avatar = avatar_from_data_uri((body or {}).get("image", ""))
    if avatar is None:
        raise HTTPException(
            status_code=422,
            detail="image must be a data:image/...;base64 URI of a real image")
    person.avatar = avatar
    await store.upsert_person(person)
    return JSONResponse({"person_id": person_id, "avatar": avatar})


@router.get("/people/{person_id}/snapshots")
async def person_snapshots(person_id: str, _: None = Depends(_require_sensitive)) -> JSONResponse:
    """U127: recent recognition snapshots of this person (in-memory, newest
    first). Face images of a known person → gated to the SENSITIVE tier."""
    if _recognition_gallery is None:
        return JSONResponse({"snapshots": []})
    return JSONResponse({"snapshots": _recognition_gallery.list(person_id)})


@router.post("/people/{person_id}/snapshots/{snapshot_id}/wrong")
async def snapshot_wrong(
    person_id: str,
    snapshot_id: str,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U136: 'that isn't them' — drop a misrecognized snapshot and re-file it as
    an unknown sighting so the owner can tag it to the RIGHT person, which
    re-enrols the face correctly and improves recognition."""
    if _recognition_gallery is None:
        return JSONResponse({"error": "no gallery"}, status_code=404)
    snap = _recognition_gallery.mark_wrong(person_id, snapshot_id)
    if snap is None:
        return JSONResponse({"error": "unknown snapshot"}, status_code=404)
    refiled = False
    try:  # re-file for correct tagging when we kept the embedding + frame
        from aura_brain import recognition_api

        log = recognition_api.get_sightings() if hasattr(recognition_api, "get_sightings") else None
        if log is not None and snap.embedding and snap.frame:
            log.record(snap.frame, snap.embedding)
            refiled = True
    except Exception:  # noqa: BLE001 — the correction must never fail loudly
        refiled = False
    return JSONResponse({"removed": snapshot_id, "refiled_for_tagging": refiled})


@router.delete("/people/{person_id}")
async def forget_person(person_id: str, confirm: str = "") -> JSONResponse:
    """Right-to-be-forgotten (destructive, ADR-008 §9).

    U185: with STEP_UP_WEBHOOK_URL configured the phone approval still rules.
    Without one, every delete used to be auto-denied — so erasure was simply
    impossible, which is untenable now that guest profiles are created
    automatically (U181) and the owner must be able to remove people. The
    fallback is a TYPED CONFIRMATION: `?confirm=<person_id>` from the console.
    That is deliberate intent from the owner's own screen, not a possession
    factor — a weaker but honest gate, and far better than a dead feature.
    """
    if _stepup_gate is not None and getattr(_stepup_gate, "_webhook_url", None):
        await _require_stepup("delete_person", {"person_id": person_id})
    elif _omk_loaded and confirm != person_id:
        return JSONResponse(
            {"error": "confirmation required",
             "detail": f"repeat the id as ?confirm={person_id} to delete this person"},
            status_code=428,   # Precondition Required
        )
    await _require().delete_person(person_id)
    if _recognition_gallery is not None:  # U127: wipe their snapshots too
        _recognition_gallery.forget(person_id)
    # U244: and their FACE. This was missing, so every deleted person left an
    # enrolled embedding behind — ten of them by the time it was noticed. Two
    # separate harms: the orphan still wins matches and hands the pipeline an
    # id that resolves to nobody, and an erasure that leaves biometric data on
    # disk is not an erasure (ADR-008 §9).
    from aura_brain import recognition_api

    faces = recognition_api.matcher()
    if faces is not None:
        faces.forget(person_id)
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
    body: dict | None = None,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U103: grow the persona graph — read this person's fetchable sources
    (blog/website/github) and distill them into [[linked]] profile facts.
    U105: body {"kind","value"} restricts to one source (auto-ingest on add)."""
    from aura_brain.source_ingest import ingest_person_sources

    only = body if body and body.get("kind") else None
    result = await ingest_person_sources(_require(), person_id, only=only)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return JSONResponse(result)


@router.post("/refresh-sources")
async def refresh_sources(_: None = Depends(_require_sensitive)) -> JSONResponse:
    """U105: re-read every person's fetchable sources now (same loop the
    weekly SOURCE_REFRESH_HOURS timer runs; dedupe keeps it idempotent)."""
    from aura_brain.source_ingest import refresh_all_sources

    return JSONResponse(await refresh_all_sources(_require()))


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


@router.put("/people/{person_id}/memory")
async def put_memory(person_id: str, body: dict,
                     _: None = Depends(_require_sensitive)) -> JSONResponse:
    """REPLACE this person's long-term memory note.

    U278: "bij memory, wanneer ik aanpassing (correctie) maak lijkt hij niet te
    saven". It saved — as a SECOND fact. The console's Save button called
    `addFact(person, "memory", text)`, which appends; both the console and the
    brain read the memory with a first-match lookup, so they kept returning the
    OLD note. The correction was stored, never displayed, and never reached the
    model — which is the worst of the three, because correcting something wrong
    about yourself is exactly when it has to take.

    Replacing is a different operation from adding, so it gets its own route
    rather than a fact POST that happens to use a reserved key.
    """
    store = _require()
    if await store.get_person(person_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown person {person_id!r}")
    text = str((body or {}).get("memory", "")).strip()

    # Always against THIS router's store. Routing it through
    # ctx.person_memory instead would write to whatever store that module was
    # built with — the same one in production, but "usually the same object"
    # is not a thing to depend on, and the full test suite proved it by
    # writing the note into a different store than the one being read.
    from shared_schemas.knowledge import ProfileFact  # noqa: PLC0415

    # Delete ALL of them: a store that already collected duplicates (every
    # press of the old Save button added one) is repaired here rather than
    # growing by one more.
    for f in await store.get_facts(person_id):
        if f.key == "memory":
            await store.delete_fact(str(f.fact_id))
    if text:
        await store.add_fact(ProfileFact(person_id=person_id, key="memory", value=text))
    kept = [f.value for f in await store.get_facts(person_id) if f.key == "memory"]
    return JSONResponse({"person_id": person_id, "memory": kept[0] if kept else "",
                         "notes": len(kept)})


@router.post("/people/{person_id}/memory/flush")
async def flush_memory(
    person_id: str,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """U109: distil any buffered exchanges into this person's long-term memory
    now (rather than waiting for the buffer to fill). Returns the memory."""
    from aura_brain import main as _main

    pm = getattr(getattr(_main, "ctx", None), "person_memory", None)
    if pm is None:
        return JSONResponse({"memory": "", "note": "long-term memory is disabled"})
    await pm.flush(person_id)
    return JSONResponse({"person_id": person_id, "memory": await pm.get_memory(person_id)})


@router.get("/export")
async def export_brain(_: None = Depends(_require_sensitive)) -> JSONResponse:
    """U104: one honest JSON dump of everything AURA knows (people/facts/signals)."""
    from aura_brain.brain_transfer import export_knowledge

    return JSONResponse(await export_knowledge(_require()))


@router.delete("/facts/{fact_id}")
async def delete_fact(fact_id: str, confirm: str = "") -> JSONResponse:
    """Delete a fact (destructive, ADR-008 §9).

    U262: this was step-up-only, and `_require_stepup` AUTO-DENIES when no
    STEP_UP_WEBHOOK_URL is configured. So on any encrypted install without a
    phone webhook - which is the normal install - deleting a fact was simply
    impossible, and the console's cross did nothing at all, silently.

    U185 already solved exactly this for forgetting a PERSON: the phone still
    rules when a webhook exists, and otherwise a typed confirmation from the
    owner's own screen stands in. Facts never got that treatment. They get it
    now, with the same reasoning: a weaker but honest gate beats a feature that
    cannot be used - especially this one, whose entire purpose is correcting
    what he wrongly believes about someone.
    """
    if _stepup_gate is not None and getattr(_stepup_gate, "_webhook_url", None):
        await _require_stepup("delete_fact", {"fact_id": fact_id})
    elif _omk_loaded and confirm != fact_id:
        return JSONResponse(
            {"error": "confirmation required",
             "detail": f"repeat the id as ?confirm={fact_id} to delete this fact"},
            status_code=428,   # Precondition Required
        )
    await _require().delete_fact(fact_id)
    return JSONResponse({"deleted": fact_id})


@router.patch("/facts/{fact_id}")
async def update_fact(
    fact_id: str,
    body: dict,
    _: None = Depends(_require_sensitive),
) -> JSONResponse:
    """Correct a fact in place.

    U262: asked for alongside the delete fix, and it is the more useful half.
    What prompted it was a fact reading "likes colelcting jellycats" - a typo
    the owner could neither fix nor remove, so a wrong belief about a person
    was simply permanent.

    Editing is NOT destructive - the fact stays, it just becomes right - so it
    needs no step-up. Correcting a mistake should be easier than living with
    it, or people stop correcting.
    """
    key, value = body.get("key"), body.get("value")
    if not key or value is None:
        raise HTTPException(status_code=422, detail="key and value are required")
    fact = await _require().update_fact(fact_id, str(key), str(value))
    if fact is None:
        raise HTTPException(status_code=404, detail=f"no fact {fact_id}")
    return JSONResponse(fact.model_dump(mode="json"))


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
    # U221 (S14): back off after repeated failures. scrypt costs ~50 ms, which
    # is no obstacle to an online dictionary attack against an 8-character
    # minimum — and success hands over every profile and face embedding.
    import time as _time

    global _unlock_fails, _unlock_blocked_until
    now = _time.monotonic()
    if now < _unlock_blocked_until:
        return JSONResponse(
            {"error": "too many attempts — wait a moment and try again",
             "retry_after_s": round(_unlock_blocked_until - now, 1)},
            status_code=429)

    # U225 (S9): derive with the parameters this store was actually written
    # under — reading them from key-params.json rather than assuming, so a
    # rotated work factor does not silently reject the right passphrase.
    from pathlib import Path

    from shared_schemas.knowledge import crypto
    from shared_schemas.knowledge import omk as _omk_mod

    _kpath = Path(os.environ.get("KNOWLEDGE_DB_PATH", "./data/knowledge.enc.json"))
    _params = _kpath.parent / _omk_mod.PARAMS_FILENAME
    if _params.exists():
        import json as _json

        candidate = _omk_mod.KdfParams.from_dict(
            _json.loads(_params.read_text(encoding="utf-8"))["current"]).derive(passphrase)
    else:  # never migrated (in-memory/test store) — legacy derivation
        candidate = crypto.derive_omk(
            passphrase, _omk_mod.legacy_salt(os.environ.get("KNOWLEDGE_SALT")),
            n=crypto.LEGACY_SCRYPT_N)
    # compare_digest, not `!=`: a byte-wise comparison leaks how much of the
    # derived key was right through its timing.
    import hmac

    if not hmac.compare_digest(candidate, store_omk):
        _unlock_fails += 1
        if _unlock_fails >= 5:
            _unlock_blocked_until = now + min(60.0, 2.0 ** (_unlock_fails - 4))
        return JSONResponse({"error": "wrong passphrase"}, status_code=403)
    _unlock_fails = 0
    _unlock_blocked_until = 0.0
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
