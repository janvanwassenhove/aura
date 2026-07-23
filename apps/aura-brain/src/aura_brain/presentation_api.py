"""U206: drive a co-presenter scenario live — the phase-2 wiring.

Owns ONE active presentation session at a time: a ScenarioRunner wired to the
real robot (speech + gesture), the LLM (for improvise/chime_in), the event bus
(so the console's presenter view shows subtitles), and — on Windows — the
PowerPoint watcher (so `slide:N` beats fire as you advance your deck).

    POST   /presentation/scenario   {yaml}   → load & start; returns status
    POST   /presentation/next                → fire the next hand-advanced beat
    POST   /presentation/speech     {text}   → feed presenter speech (keywords)
    GET    /presentation/status              → current slide, fired beats, …
    DELETE /presentation/scenario            → stop and clear

The keyword path is ALSO fed automatically from the voice loop while a
presentation is active (main.py wires it); this endpoint lets the console or a
test push text too.
"""

from __future__ import annotations

import logging
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from orchestrator.scenario_runner import ScenarioRunner
from shared_schemas.events.system import PresentationBeatFired
from shared_schemas.presentation import Scenario

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presentation", tags=["presentation"])

_robot: Any = None      # RobotClient
_bus: Any = None        # AsyncEventBus
_persona: Any = None    # CharacterStore/persona switch (optional)
_runner: ScenarioRunner | None = None
_watcher: Any = None    # PowerPointWatcher | None


def init(robot: Any, bus: Any) -> None:
    global _robot, _bus
    _robot = robot
    _bus = bus


def is_active() -> bool:
    return _runner is not None


async def feed_speech(text: str) -> None:
    """Voice-loop hook: presenter speech → keyword beats (no-op when idle)."""
    if _runner is not None and text:
        try:
            await _runner.on_speech(text)
        except Exception as exc:  # noqa: BLE001 — a beat must never break the mic loop
            logger.debug("presentation on_speech failed: %s", exc)


# ------------------------------------------------------------------
# Runner wiring — the messy real-world edges the runner stays out of
# ------------------------------------------------------------------

async def _speak(text: str) -> None:
    if _robot is not None and text:
        await _robot.speak(text)


async def _gesture(name: str) -> None:
    if _robot is None or not name:
        return
    try:
        from shared_schemas.robot.models import MotionCommand

        await _robot.execute_motion(MotionCommand(motion_id=name))
    except Exception as exc:  # noqa: BLE001
        logger.debug("presentation gesture %r failed: %s", name, exc)


async def _generate(topic: str, guardrails: str, engine: str) -> str:
    """Improvise a spoken line about `topic`. Text only — the runner speaks it.

    Kept to a single LLM completion (no tools) so a beat can't wander off into
    tool calls mid-talk. A beat that genuinely needs live data should be a
    `speak` beat with the data filled in, or a future pipeline-backed beat.
    """
    from orchestrator.llm import openai_chat

    system = (
        "You are a robot co-presenter on stage. Say ONE short spoken remark "
        "about the topic — natural, out loud, first person, no preamble, no "
        "markdown. " + (guardrails or "Keep it to 1-2 sentences.")
    )
    try:
        choice = await openai_chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": f"Topic: {topic}"}])
        return (choice.get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("presentation improvise failed: %s", exc)
        return ""


async def _on_event(event: dict) -> None:
    """Runner events → the bus, so the presenter view can render subtitles."""
    if _bus is None or event.get("type") != "beat_done":
        return
    slide = _runner.current_slide if _runner else None
    beat_id = event.get("beat", "")
    mode = next((b.mode for b in _runner._scenario.beats if b.id == beat_id), "") if _runner else ""
    await _bus.publish(PresentationBeatFired(
        session_id="presentation", beat_id=beat_id, mode=mode,
        spoken=event.get("spoken", ""), slide_number=slide))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("/scenario")
async def load_scenario(body: dict) -> JSONResponse:
    global _runner, _watcher
    raw = (body or {}).get("yaml", "")
    if not raw:
        return JSONResponse({"error": "yaml field is required"}, status_code=422)
    try:
        scenario = Scenario.model_validate(yaml.safe_load(raw))
    except Exception as exc:  # noqa: BLE001 — bad YAML / failed validation
        return JSONResponse({"error": f"invalid scenario: {exc}"}, status_code=422)

    await _stop_watcher()
    _runner = ScenarioRunner(
        scenario, speak=_speak, generate=_generate, gesture=_gesture, on_event=_on_event)

    # Start the PowerPoint watcher if we can; the talk still runs without it
    # (you advance slides yourself, keyword + manual beats work regardless).
    pptx_watching = False
    try:
        from aura_brain.pptx_watcher import PowerPointWatcher, powerpoint_available

        if powerpoint_available():
            _watcher = PowerPointWatcher(on_slide=_on_slide)
            _watcher.start()
            pptx_watching = True
    except Exception as exc:  # noqa: BLE001
        logger.debug("PowerPoint watcher not started: %s", exc)

    status = _runner.status()
    status["powerpoint_watching"] = pptx_watching
    return JSONResponse(status)


async def _on_slide(slide_number: int) -> None:
    if _runner is not None:
        try:
            await _runner.on_slide(slide_number)
        except Exception as exc:  # noqa: BLE001
            logger.debug("presentation on_slide failed: %s", exc)


@router.post("/next")
async def next_beat() -> JSONResponse:
    if _runner is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    beat = await _runner.next()
    return JSONResponse({
        "fired": beat.id if beat else None,
        "done": beat is None,
        "status": _runner.status(),
    })


@router.post("/speech")
async def push_speech(body: dict) -> JSONResponse:
    if _runner is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    fired = await _runner.on_speech((body or {}).get("text", ""))
    return JSONResponse({"fired": [b.id for b in fired], "status": _runner.status()})


@router.get("/status")
async def status() -> JSONResponse:
    if _runner is None:
        return JSONResponse({"active": False})
    out = {"active": True, **_runner.status()}
    out["powerpoint_watching"] = _watcher is not None
    return JSONResponse(out)


@router.delete("/scenario")
async def clear_scenario() -> JSONResponse:
    global _runner
    await _stop_watcher()
    _runner = None
    return JSONResponse({"active": False})


async def _stop_watcher() -> None:
    global _watcher
    if _watcher is not None:
        try:
            await _watcher.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug("stopping PowerPoint watcher failed: %s", exc)
        _watcher = None
