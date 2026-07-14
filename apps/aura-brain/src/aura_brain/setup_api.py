"""In-app setup (U34-slice): enable encrypted knowledge + face recognition
WITHOUT the CLI wizard or a restart.

POST /setup/secure {passphrase, remember}:
  1. derives the owner master key (scrypt, per-install random salt),
  2. creates the encrypted store and MIGRATES everything from the current
     (unencrypted dev) store into it,
  3. live-swaps the store into the knowledge API + judgment layer,
  4. starts face recognition (matcher + perception loop),
  5. with remember=true, persists KNOWLEDGE_PASSPHRASE/SALT to the env file so
     the next start auto-unlocks.

The passphrase is write-only: it is never logged, stored in module state, or
returned by any endpoint.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])

_get_store: Callable[[], Any] | None = None
_swap_store: Callable[[Any], None] | None = None
_start_recognition: Callable[[bytes], None] | None = None
_already_encrypted: Callable[[], bool] | None = None


def init(
    get_store: Callable[[], Any],
    swap_store: Callable[[Any], None],
    start_recognition: Callable[[bytes], None],
    already_encrypted: Callable[[], bool],
) -> None:
    global _get_store, _swap_store, _start_recognition, _already_encrypted
    _get_store = get_store
    _swap_store = swap_store
    _start_recognition = start_recognition
    _already_encrypted = already_encrypted


async def _migrate(old: Any, new: Any) -> int:
    """Copy people + facts + signals from the old store into the new one."""
    people = await old.list_people()
    for person in people:
        await new.upsert_person(person)
        for fact in await old.get_facts(person.person_id):
            await new.add_fact(fact)
        for signal in await old.get_signals(person.person_id):
            await new.record_signal(signal)
    return len(people)


def _persist_env(passphrase: str, salt: str) -> bool:
    """Update KNOWLEDGE_PASSPHRASE/SALT in the env file (create keys if absent)."""
    return _write_env({"KNOWLEDGE_PASSPHRASE": passphrase, "KNOWLEDGE_SALT": salt})


def _write_env(updates: dict[str, str]) -> bool:
    env_path = Path(os.environ.get("AURA_ENV_FILE", "./infra/dev/.env"))
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        updates = dict(updates)
        out: list[str] = []
        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else None
            if key in updates:
                out.append(f"{key}={updates.pop(key)}")
            else:
                out.append(line)
        out.extend(f"{k}={v}" for k, v in updates.items())
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError as exc:
        logger.warning("could not persist passphrase to %s: %s", env_path, exc)
        return False


@router.get("/status")
async def status() -> JSONResponse:
    return JSONResponse({
        "encrypted": bool(_already_encrypted and _already_encrypted()),
    })


# ── Assistant preferences (U36h): call name + reply language ──────────

_ALLOWED_LANGUAGES = {"auto", "en", "nl", "fr"}


_ALLOWED_VOICE_MODES = {"off", "wake_word"}


def _prefs_snapshot() -> dict:
    return {
        "assistant_name": os.environ.get("ASSISTANT_NAME", "AURA"),
        "language": os.environ.get("ASSISTANT_LANGUAGE", "auto"),
        "voice_mode": os.environ.get("VOICE_MODE", "off"),
        "wake_word": os.environ.get("WAKE_WORD", os.environ.get("ASSISTANT_NAME", "AURA")),
    }


@router.get("/prefs")
async def get_prefs() -> JSONResponse:
    return JSONResponse(_prefs_snapshot())


@router.post("/prefs")
async def set_prefs(body: dict) -> JSONResponse:
    updates: dict[str, str] = {}
    name = (body or {}).get("assistant_name")
    if name is not None:
        name = name.strip()
        if not (1 <= len(name) <= 24) or not name.replace(" ", "").isalnum():
            return JSONResponse(
                {"error": "name must be 1-24 letters/digits"}, status_code=422,
            )
        updates["ASSISTANT_NAME"] = name
    language = (body or {}).get("language")
    if language is not None:
        language = language.strip().lower()
        if language not in _ALLOWED_LANGUAGES:
            return JSONResponse(
                {"error": f"language must be one of {sorted(_ALLOWED_LANGUAGES)}"},
                status_code=422,
            )
        updates["ASSISTANT_LANGUAGE"] = language
    voice_mode = (body or {}).get("voice_mode")
    if voice_mode is not None:
        voice_mode = voice_mode.strip().lower()
        if voice_mode not in _ALLOWED_VOICE_MODES:
            return JSONResponse(
                {"error": f"voice_mode must be one of {sorted(_ALLOWED_VOICE_MODES)}"},
                status_code=422,
            )
        updates["VOICE_MODE"] = voice_mode
    wake_word = (body or {}).get("wake_word")
    if wake_word is not None:
        wake_word = wake_word.strip()
        if not (1 <= len(wake_word) <= 24):
            return JSONResponse({"error": "wake word must be 1-24 characters"}, status_code=422)
        updates["WAKE_WORD"] = wake_word
    if not updates:
        return JSONResponse({"error": "nothing to update"}, status_code=422)
    os.environ.update(updates)          # effective immediately (read live)
    persisted = _write_env(updates)     # survives restarts
    return JSONResponse({**_prefs_snapshot(), "persisted": persisted})


@router.post("/secure")
async def secure(body: dict) -> JSONResponse:
    if _get_store is None or _swap_store is None:
        return JSONResponse({"error": "setup not initialised"}, status_code=503)
    if _already_encrypted and _already_encrypted():
        return JSONResponse({"error": "knowledge is already encrypted"}, status_code=409)

    passphrase = (body or {}).get("passphrase", "")
    if len(passphrase) < 8:
        return JSONResponse(
            {"error": "passphrase must be at least 8 characters"}, status_code=422,
        )
    remember = bool((body or {}).get("remember", True))

    from shared_schemas.knowledge import EncryptedKnowledgeStore, crypto

    salt = os.environ.get("KNOWLEDGE_SALT") or secrets.token_hex(8)
    omk = crypto.derive_omk(passphrase, salt.encode().ljust(16, b"0")[:16])
    new_store = EncryptedKnowledgeStore(
        omk, path=os.environ.get("KNOWLEDGE_DB_PATH", "./data/knowledge.enc.json"),
    )

    migrated = await _migrate(_get_store(), new_store)
    _swap_store(new_store)

    recognition_started = False
    if _start_recognition is not None:
        try:
            _start_recognition(omk)
            recognition_started = True
        except Exception as exc:  # noqa: BLE001 — recognition is optional
            logger.warning("recognition start failed: %s", exc)

    # Keep the env vars for THIS process consistent (salt reuse on /setup calls).
    os.environ["KNOWLEDGE_SALT"] = salt
    persisted = _persist_env(passphrase, salt) if remember else False

    logger.info("knowledge secured in-app: %d people migrated", migrated)
    return JSONResponse({
        "encrypted": True,
        "migrated_people": migrated,
        "recognition_started": recognition_started,
        "remembered": persisted,
    })
