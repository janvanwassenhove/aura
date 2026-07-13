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


def init(matcher: Any, embedder: Any, robot: Any, store: Any, loop: Any = None) -> None:
    global _matcher, _embedder, _robot, _store, _loop
    _matcher, _embedder, _robot, _store, _loop = matcher, embedder, robot, store, loop


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

    frame = await _robot.camera_frame()
    embedding = await asyncio.to_thread(_embedder.embed, frame)
    if embedding is None:
        return JSONResponse(
            {"error": "no face in frame — look at the robot and try again"},
            status_code=422,
        )
    _matcher.enroll(person_id, embedding)
    # Immediate self-check: the frame we just enrolled must match its own person.
    check_id, confidence = _matcher.identify(embedding)
    return JSONResponse({
        "enrolled": person_id,
        "confidence_check": round(confidence, 3),
        "ok": check_id == person_id,
    })


@router.delete("/people/{person_id}")
async def forget(person_id: str) -> JSONResponse:
    if _matcher is None:
        return JSONResponse({"error": "recognition disabled"}, status_code=503)
    _matcher.forget(person_id)
    return JSONResponse({"forgotten": person_id})
