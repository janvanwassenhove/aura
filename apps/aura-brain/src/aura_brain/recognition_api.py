"""U18 — recognition/enrollment API.

Enroll a person's face: the robot grabs a frame, the embedder turns it into a
vector, the matcher stores it ENCRYPTED (biometric data, ADR-008). Enrollment
requires the person to already exist in the knowledge store — recognition links
to people, it never creates them.

    POST   /recognition/enroll {person_id}   → {enrolled, confidence_check}
    DELETE /recognition/people/{person_id}   → {forgotten}
    GET    /recognition/status               → {enabled, embedder, enrolled}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/recognition", tags=["recognition"])

_matcher: Any = None      # EmbeddingMatcher | None
_embedder: Any = None     # FaceEmbedder | None
_robot: Any = None        # RobotClient | None
_store: Any = None        # KnowledgeStore | None
_loop: Any = None         # PerceptionLoop | None
_sightings: Any = None    # SightingLog | None (U36f — set at boot, works pre-secure)


def init(matcher: Any, embedder: Any, robot: Any, store: Any, loop: Any = None) -> None:
    global _matcher, _embedder, _robot, _store, _loop
    _matcher, _embedder, _robot, _store, _loop = matcher, embedder, robot, store, loop


def set_sightings(log: Any) -> None:
    global _sightings
    _sightings = log


def get_sightings() -> Any:
    """U136: the unknown-visitor log, so a misrecognized snapshot can be
    re-filed there for correct tagging."""
    return _sightings


@router.get("/status")
async def status() -> JSONResponse:
    if _matcher is None:
        return JSONResponse({"enabled": False, "embedder": None, "enrolled": []})
    return JSONResponse({
        "enabled": True,
        "embedder": getattr(_embedder, "name", "unknown"),
        "loop_running": _loop is not None and _loop._task is not None,
        "enrolled": _matcher.enrolled_ids(),
    })


@router.post("/enroll")
async def enroll(body: dict) -> JSONResponse:
    if _matcher is None or _embedder is None or _robot is None:
        return JSONResponse({"error": "recognition disabled"}, status_code=503)
    person_id = (body or {}).get("person_id", "")
    if not person_id:
        return JSONResponse({"error": "person_id is required"}, status_code=422)
    if _store is not None and await _store.get_person(person_id) is None:
        return JSONResponse(
            {"error": f"unknown person {person_id!r} — add them to knowledge first"},
            status_code=404,
        )

    # Grab a few frames over ~1.5s so we enroll several angles → robust matching.
    captured = 0
    last_embedding = None
    avatar_frame = None
    for i in range(4):
        frame = await _robot.camera_frame()
        embedding = await asyncio.to_thread(_embedder.embed, frame)
        if embedding is not None:
            _matcher.enroll(person_id, embedding)
            last_embedding = embedding
            captured += 1
            if avatar_frame is None:      # U204: first frame WITH a face → avatar
                avatar_frame = frame
        if i < 3:
            await asyncio.sleep(0.4)
    if captured == 0:
        return JSONResponse(
            {"error": "no face in frame — look straight at the robot and try again"},
            status_code=422,
        )

    # U204: give a freshly-taught person a face icon — but never clobber one the
    # owner deliberately chose. Best-effort: a failed avatar must not fail teach.
    if avatar_frame is not None and _store is not None:
        try:
            person = await _store.get_person(person_id)
            if person is not None and not person.avatar:
                from aura_brain.avatar import avatar_from_image_bytes

                avatar = await asyncio.to_thread(avatar_from_image_bytes, avatar_frame)
                if avatar:
                    person.avatar = avatar
                    await _store.upsert_person(person)
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning("avatar set on teach failed: %s", exc)
    check_id, confidence = _matcher.identify(last_embedding)
    return JSONResponse({
        "enrolled": person_id,
        "samples": _matcher.sample_count(person_id),
        "confidence_check": round(confidence, 3),
        "ok": check_id == person_id,
    })


@router.post("/people/{person_id}/avatar/capture")
async def capture_avatar(person_id: str) -> JSONResponse:
    """U204: grab a fresh camera frame and use it as this person's avatar.

    The 'change avatar → take a new photo' path. Unlike teach, this OVERWRITES:
    the owner asked for a new picture, so give them one.
    """
    if _robot is None:
        return JSONResponse({"error": "recognition disabled"}, status_code=503)
    if _store is None:
        return JSONResponse({"error": "knowledge store unavailable"}, status_code=503)
    person = await _store.get_person(person_id)
    if person is None:
        return JSONResponse({"error": f"unknown person {person_id!r}"}, status_code=404)

    try:
        frame = await _robot.camera_frame()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"camera unavailable: {exc}"}, status_code=503)

    from aura_brain.avatar import avatar_from_image_bytes

    avatar = await asyncio.to_thread(avatar_from_image_bytes, frame)
    if not avatar:
        return JSONResponse(
            {"error": "could not read a picture from the camera"}, status_code=422)
    person.avatar = avatar
    await _store.upsert_person(person)
    return JSONResponse({"person_id": person_id, "avatar": avatar})


@router.post("/merge")
async def merge_person(body: dict) -> JSONResponse:
    """U189: assign one person's face to another, then erase the source.

    The case this exists for: a face auto-enrolled as "Guest 1" (U181) turns
    out to be Piet. Moving the samples keeps recognition working under Piet's
    id instead of forcing the owner to re-teach the face; the guest profile
    and its face are then erased.
    """
    if _matcher is None:
        return JSONResponse({"error": "recognition disabled"}, status_code=503)
    source = str((body or {}).get("from_person_id", "")).strip().lower()
    target = str((body or {}).get("to_person_id", "")).strip().lower()
    if not source or not target:
        return JSONResponse(
            {"error": "from_person_id and to_person_id are required"}, status_code=422)
    if source == target:
        return JSONResponse({"error": "cannot merge a person into themselves"},
                            status_code=422)
    if _store is not None and await _store.get_person(target) is None:
        return JSONResponse({"error": f"unknown person {target!r}"}, status_code=404)

    moved = _matcher.transfer(source, target)
    if _store is not None:
        await _store.delete_person(source)      # the guest profile is absorbed
    return JSONResponse({"merged": source, "into": target, "faces_moved": moved})


@router.delete("/people/{person_id}")
async def forget(person_id: str) -> JSONResponse:
    if _matcher is None:
        return JSONResponse({"error": "recognition disabled"}, status_code=503)
    _matcher.forget(person_id)
    return JSONResponse({"forgotten": person_id})


# ------------------------------------------------------------------
# Unknown-visitor sightings (U36f) — in-memory, tag to train recognition
# ------------------------------------------------------------------


@router.get("/sightings")
async def list_sightings() -> JSONResponse:
    if _sightings is None:
        return JSONResponse({"sightings": []})
    return JSONResponse({"sightings": _sightings.list()})


@router.get("/sightings/{sighting_id}/image")
async def sighting_image(sighting_id: str):
    from fastapi import Response

    entry = _sightings.get(sighting_id) if _sightings is not None else None
    if entry is None:
        return JSONResponse({"error": "unknown sighting"}, status_code=404)
    return Response(content=entry.thumbnail, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@router.post("/sightings/{sighting_id}/tag")
async def tag_sighting(sighting_id: str, body: dict) -> JSONResponse:
    """Tag an unknown visitor as a known person → their face is enrolled
    (encrypted) and future recognition improves."""
    if _sightings is None:
        return JSONResponse({"error": "sightings disabled"}, status_code=503)
    if _matcher is None:
        return JSONResponse(
            {"error": "recognition is not enabled — secure knowledge first "
                      "(Knowledge panel)"},
            status_code=409,
        )
    entry = _sightings.get(sighting_id)
    if entry is None:
        return JSONResponse({"error": "unknown sighting"}, status_code=404)
    person_id = (body or {}).get("person_id", "").strip().lower()
    if not person_id:
        return JSONResponse({"error": "person_id is required"}, status_code=422)
    if _store is not None and await _store.get_person(person_id) is None:
        return JSONResponse(
            {"error": f"unknown person {person_id!r} — add them to knowledge first"},
            status_code=404,
        )
    _matcher.enroll(person_id, entry.embedding)
    # This sighting (and any others of the same face) now match → clean up.
    purged = _sightings.purge_matching(_matcher)
    return JSONResponse({"tagged": person_id, "purged_sightings": purged})


@router.delete("/sightings/{sighting_id}")
async def dismiss_sighting(sighting_id: str) -> JSONResponse:
    if _sightings is None or not _sightings.remove(sighting_id):
        return JSONResponse({"error": "unknown sighting"}, status_code=404)
    return JSONResponse({"dismissed": sighting_id})
