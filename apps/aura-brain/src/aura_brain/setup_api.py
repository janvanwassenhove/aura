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
    """U34: everything the onboarding wizard needs to decide what's left."""
    people_count = 0
    if _get_store is not None:
        try:
            people_count = len(await _get_store().list_people())
        except Exception:  # noqa: BLE001 — store may be locked
            people_count = 0
    return JSONResponse({
        "setup_done": os.environ.get("SETUP_DONE", "false").lower() == "true",
        "encrypted": bool(_already_encrypted and _already_encrypted()),
        "assistant_name": os.environ.get("ASSISTANT_NAME", "AURA"),
        "robot_url": os.environ.get("ROBOT_RUNTIME_URL", ""),
        "voice_mode": os.environ.get("VOICE_MODE", "off"),
        "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "openrouter_key_set": bool(os.environ.get("OPENROUTER_API_KEY")),
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "people_count": people_count,
    })


# ── U34: wizard config writer (secrets write-only) ────────────────────

_CONFIG_KEYS = {
    # body key -> env var; secret keys are never echoed back
    "robot_url": "ROBOT_RUNTIME_URL",
    "llm_provider": "LLM_PROVIDER",
    "llm_model": "LLM_MODEL",
    "openai_api_key": "OPENAI_API_KEY",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
}
_SECRET_KEYS = {"openai_api_key", "openrouter_api_key", "gemini_api_key"}


@router.post("/config")
async def set_config(body: dict) -> JSONResponse:
    """Write wizard config to env (+persist). Secrets are write-only: they are
    stored, never logged and never returned. `setup_done: true` marks the
    onboarding as finished so the wizard stops appearing."""
    body = body or {}
    updates: dict[str, str] = {}
    for key, env_var in _CONFIG_KEYS.items():
        value = body.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if not value:
            continue
        updates[env_var] = value
    if body.get("setup_done") is not None:
        updates["SETUP_DONE"] = "true" if body["setup_done"] else "false"
    if not updates:
        return JSONResponse({"error": "nothing to update"}, status_code=422)
    os.environ.update(updates)
    persisted = _write_env(updates)
    # Apply the LLM switch live (same path as the Settings panel).
    if "LLM_PROVIDER" in updates:
        try:
            from orchestrator.config import update_config

            provider = updates["LLM_PROVIDER"]
            model = updates.get("LLM_MODEL", "") or {
                "openrouter": os.environ.get("OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
                "gemini": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                "echo": "",
            }.get(provider, os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
            update_config(provider, model)
        except Exception as exc:  # noqa: BLE001 — env is set; live apply is best-effort
            logger.debug("live LLM apply failed: %s", exc)
    applied = sorted(k for k in updates if k not in
                     {_CONFIG_KEYS[s] for s in _SECRET_KEYS})
    secrets_set = sorted(_CONFIG_KEYS[s] for s in _SECRET_KEYS
                         if _CONFIG_KEYS[s] in updates)
    return JSONResponse({
        "applied": applied,
        "secrets_set": [s.lower() for s in secrets_set],  # names only, never values
        "persisted": persisted,
    })


# ── U34: robot connectivity test + discovery ──────────────────────────


async def _probe_robot(url: str, timeout: float = 2.5) -> dict:
    import httpx

    url = url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url}/robot/status")
            resp.raise_for_status()
            data = resp.json()
        return {"url": url, "ok": True, "mode": data.get("mode"),
                "battery_pct": data.get("battery_pct")}
    except Exception as exc:  # noqa: BLE001 — probe reports, never raises
        return {"url": url, "ok": False, "error": type(exc).__name__}


@router.post("/test-robot")
async def test_robot(body: dict) -> JSONResponse:
    url = str((body or {}).get("url", "")).strip() or os.environ.get("ROBOT_RUNTIME_URL", "")
    if not url:
        return JSONResponse({"error": "no url given or configured"}, status_code=422)
    return JSONResponse(await _probe_robot(url))


@router.get("/discover")
async def discover() -> JSONResponse:
    """Find robot-runtime candidates: configured URL, mDNS name, then a quick
    /24 subnet sweep on :8001 (sub-second timeouts, bounded concurrency)."""
    import asyncio
    import socket

    candidates: list[str] = []
    configured = os.environ.get("ROBOT_RUNTIME_URL", "").strip().rstrip("/")
    if configured:
        candidates.append(configured)
    candidates.append("http://reachy-mini.local:8001")

    # Subnet sweep: derive the local /24 from the primary interface.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        base = ".".join(local_ip.split(".")[:3])
        candidates.extend(f"http://{base}.{i}:8001" for i in range(1, 255))
    except OSError:
        pass

    seen: set[str] = set()
    unique = [c for c in candidates if not (c in seen or seen.add(c))]
    sem = asyncio.Semaphore(50)

    async def probe(url: str) -> dict:
        async with sem:
            return await _probe_robot(url, timeout=0.8)

    results = await asyncio.gather(*(probe(u) for u in unique))
    found = [r for r in results if r["ok"]]
    return JSONResponse({"found": found, "scanned": len(unique)})


# ── Assistant preferences (U36h): call name + reply language ──────────

_ALLOWED_LANGUAGES = {"auto", "en", "nl", "fr"}


_ALLOWED_VOICE_MODES = {"off", "wake_word"}


def _prefs_snapshot() -> dict:
    return {
        "assistant_name": os.environ.get("ASSISTANT_NAME", "AURA"),
        "language": os.environ.get("ASSISTANT_LANGUAGE", "auto"),
        "voice_mode": os.environ.get("VOICE_MODE", "off"),
        "wake_word": os.environ.get("WAKE_WORD", os.environ.get("ASSISTANT_NAME", "AURA")),
        "tts_voice": os.environ.get("TTS_VOICE", "alloy"),
        # U84: conversation-layer settings
        "character": os.environ.get("ACTIVE_CHARACTER", ""),
        "interrupt_sensitivity": os.environ.get("BARGE_IN_FACTOR", "3.0"),
        "session_memory": os.environ.get("SESSION_MEMORY", "true"),
        "mic_sensitivity": os.environ.get("VOICE_SPEECH_PEAK", "0.012"),
        # U90: per-task-type model roles (empty → use the active LLM model).
        "chat_model": os.environ.get("CHAT_MODEL", ""),
        "agent_model": os.environ.get("AGENT_MODEL", ""),
        "computer_use_model": os.environ.get("COMPUTER_USE_OPENAI_MODEL", "gpt-4o"),
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
    tts_voice = (body or {}).get("tts_voice")
    if tts_voice is not None:
        from aura_brain.voice import TTS_VOICES

        tts_voice = tts_voice.strip().lower()
        if tts_voice not in TTS_VOICES:
            return JSONResponse(
                {"error": f"tts_voice must be one of {sorted(TTS_VOICES)}"},
                status_code=422,
            )
        updates["TTS_VOICE"] = tts_voice
    character = (body or {}).get("character")
    if character is not None:
        character = str(character).strip()
        if character:
            from aura_brain.characters import CharacterStore

            if CharacterStore().get(character) is None:
                return JSONResponse({"error": f"unknown character {character!r}"},
                                    status_code=422)
        updates["ACTIVE_CHARACTER"] = character
    sensitivity = (body or {}).get("interrupt_sensitivity")
    if sensitivity is not None:
        try:
            updates["BARGE_IN_FACTOR"] = str(max(1.5, min(8.0, float(sensitivity))))
        except (TypeError, ValueError):
            return JSONResponse({"error": "interrupt_sensitivity must be a number"},
                                status_code=422)
    for role_key, env_key in (("chat_model", "CHAT_MODEL"),
                              ("agent_model", "AGENT_MODEL"),
                              ("computer_use_model", "COMPUTER_USE_OPENAI_MODEL")):
        val = (body or {}).get(role_key)
        if val is not None:
            updates[env_key] = str(val).strip()
    mic_sensitivity = (body or {}).get("mic_sensitivity")
    if mic_sensitivity is not None:
        try:
            updates["VOICE_SPEECH_PEAK"] = str(max(0.004, min(0.1, float(mic_sensitivity))))
        except (TypeError, ValueError):
            return JSONResponse({"error": "mic_sensitivity must be a number"}, status_code=422)
    session_memory = (body or {}).get("session_memory")
    if session_memory is not None:
        updates["SESSION_MEMORY"] = "true" if str(session_memory).lower() in ("true", "1", "on") else "false"
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


@router.post("/voice-check")
async def voice_check(body: dict) -> JSONResponse:
    """U86: one-shot mic diagnostic — record from the robot, report the raw
    peak, the transcript and whether the wake word matched. Lets the owner
    verify voice input without guessing."""
    import os as _os

    from aura_brain import voice as _voice
    from aura_brain.robot_client import RobotClient
    from aura_brain.voice_loop import wake_word_index

    robot = RobotClient()
    try:
        wav, peak = await robot.listen(float((body or {}).get("duration_s", 4)))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"robot mic unreachable: {exc}"}, status_code=503)
    gate = float(_os.environ.get("VOICE_SPEECH_PEAK", "0.012"))
    transcript = ""
    if peak >= gate:
        transcript = (await _voice.transcribe(wav, filename="check.wav") or "").strip()
    wake = _os.environ.get("WAKE_WORD", _os.environ.get("ASSISTANT_NAME", "AURA")).lower()
    return JSONResponse({
        "raw_peak": round(peak, 4),
        "gate": gate,
        "passed_gate": peak >= gate,
        "transcript": transcript,
        "wake_word": wake,
        "wake_matched": wake_word_index(transcript, wake) >= 0 if transcript else False,
    })


@router.get("/characters")
async def list_characters() -> JSONResponse:
    """U84: available character personas + which one is active."""
    from aura_brain.characters import CharacterStore
    from dataclasses import asdict

    store = CharacterStore()
    return JSONResponse({
        "active": os.environ.get("ACTIVE_CHARACTER", ""),
        "characters": [asdict(c) for c in store.all()],
    })


@router.post("/characters/{character_id}")
async def update_character(character_id: str, body: dict) -> JSONResponse:
    """U85: owner edits a character (prompt, traits, voice, …) from the app."""
    from dataclasses import asdict

    from aura_brain.characters import CharacterStore

    updated = CharacterStore().update(character_id, body or {})
    if updated is None:
        return JSONResponse({"error": f"unknown character {character_id!r}"},
                            status_code=404)
    return JSONResponse(asdict(updated))


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
