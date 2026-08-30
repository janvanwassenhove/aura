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
_pipeline: Any = None    # OrchestratorPipeline — for tool-backed improvise (U208)
_runner: ScenarioRunner | None = None
_watcher: Any = None    # PowerPointWatcher | None

_SESSION = "presentation"


def init(robot: Any, bus: Any, pipeline: Any = None) -> None:
    global _robot, _bus, _pipeline
    _robot = robot
    _bus = bus
    _pipeline = pipeline


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
    """Say a beat OUT LOUD.

    U269: this called `_robot.speak(text)` with no audio, and the robot's
    speak route treats a text-only request as a LOG LINE — it plays nothing
    and answers `ok: true`. Every other speaking path in the app (the voice
    loop, /robot/say, the streaming replies) synthesizes first and passes
    `audio_b64`; the presentation was the one that never did. So beats fired,
    the console filled in "all beats done", nothing errored anywhere, and the
    room heard silence. Reported as "he never said anything".

    Failures RAISE, so the runner records them and the console can say what
    went wrong. The show still goes on — that guard is U265's and it stays —
    but a silent robot must never again look like a successful beat.
    """
    if not text:
        return
    if _robot is None:
        raise RuntimeError("no robot is connected, so nothing could be said out loud")

    from aura_brain import voice  # noqa: PLC0415 — optional at import time

    # U273: the Present screen has its own Voice dropdown, and this call
    # ignored it — `synthesize_b64(text)` resolves with no mode and no
    # persona, so every beat came out in the Settings default no matter what
    # the presenter had chosen for the talk.
    audio_b64 = await voice.synthesize_b64(text, voice.resolve_voice(mode="presentation"))
    if audio_b64 is None:
        # Text-only reaches the robot as a log line. Saying so is the whole
        # point: "he is mute because there is no TTS key" and "he is mute
        # because the robot is off" need different fixes.
        raise RuntimeError(
            "speech could not be synthesized (no TTS key or the provider "
            "failed), so the robot had nothing to play")
    await _robot.speak(text, audio_b64=audio_b64)


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

    U208: `engine: pipeline` runs the FULL agentic loop (tools included) so a
    beat can pull live data — calendar, music, a lookup — and speak the result.
    `announce=False` keeps the pipeline from auto-speaking it (the runner speaks
    it once, so the subtitle and the robot stay in sync). Any other engine is a
    single LLM completion: faster, no tools, can't wander mid-talk.
    """
    guard = guardrails or "Keep it to 1-2 sentences."
    if engine == "pipeline" and _pipeline is not None:
        prompt = (
            "You are co-presenting live. In ONE short spoken remark, first "
            f"person, no markdown, address this — using tools if you need live "
            f"data: {topic}. {guard}"
        )
        try:
            return (await _pipeline.orchestrate(prompt, _SESSION, announce=False,
                                                from_user=False) or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("presentation pipeline improvise failed: %s", exc)
            return ""

    from orchestrator.llm import openai_chat

    system = (
        "You are a robot co-presenter on stage. Say ONE short spoken remark "
        "about the topic — natural, out loud, first person, no preamble, no "
        "markdown. " + guard
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

def _scenario_from_body(body: dict) -> tuple[Scenario, str | None]:
    """Accept either {yaml} (power users) or {scenario:{...}} (the builder).
    Returns (validated scenario, raw_yaml-or-None). Raises ValueError."""
    if body.get("scenario") is not None:
        return Scenario.model_validate(body["scenario"]), None
    raw = body.get("yaml", "")
    if not raw:
        raise ValueError("give a scenario or yaml")
    return Scenario.model_validate(yaml.safe_load(raw)), raw


@router.post("/scenario")
async def load_scenario(body: dict) -> JSONResponse:
    global _runner, _watcher
    try:
        scenario, _ = _scenario_from_body(body or {})
    except Exception as exc:  # noqa: BLE001 — bad YAML / failed validation
        return JSONResponse({"error": _readable(exc)}, status_code=422)

    await _stop_watcher()
    _runner = ScenarioRunner(
        scenario, speak=_speak, generate=_generate, gesture=_gesture, on_event=_on_event)

    # U263: ALWAYS start watching. The old code asked once whether a slideshow
    # was already up and, if not, created no watcher at all - so setting the
    # scenario up first (the natural order) silently cost you every slide cue
    # for the whole talk. Waiting for a slideshow is a state we report, not a
    # reason to give up before the talk has begun.
    try:
        from aura_brain.slides_watcher import SlidesWatcher

        _watcher = SlidesWatcher(on_slide=_on_slide)
        _watcher.start()
    except Exception as exc:  # noqa: BLE001
        logger.debug("slides watcher not started: %s", exc)

    return JSONResponse(_status_payload())


def _readable(exc: Exception) -> str:
    """Say what is wrong with the scenario in one line a presenter can act on.

    U264: this used to hand the console the raw Pydantic dump - the field path,
    the repr of the whole beat, `[type=value_error, ...]` and a link to the
    pydantic docs. That is a fine thing to log and a hopeless thing to read
    five minutes before a talk. The sentence the validators themselves raise
    ("beat 'beat-1': speak mode needs 'text'") is already exactly right; it
    just needs digging out of the wrapper.
    """
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        lines = []
        for err in exc.errors():
            msg = str(err.get("msg", "")).removeprefix("Value error, ").strip()
            if msg and msg not in lines:
                lines.append(msg)
        if lines:
            return "; ".join(lines[:3])
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else "unreadable scenario"
    return text[:200]


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


@router.post("/rehearse")
async def set_rehearsing(body: dict) -> JSONResponse:
    """U267: rehearsal, which up to now existed only as a label in the browser.

    The console's Rehearse button promised "beats fire, but nothing is sent"
    while the robot said every line out loud — nothing here had ever heard of
    rehearsal. Now it does: beats fire and emit exactly as in the real show,
    and only the two outputs that reach the room, voice and motion, are held.
    """
    if _runner is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    _runner.rehearsing = bool((body or {}).get("on", False))
    return JSONResponse(_status_payload())


@router.get("/scenario")
async def active_scenario() -> JSONResponse:
    """The scenario that is loaded, so it can be EDITED rather than retyped.

    U267: "New scenario" opened an empty builder and there was no other way
    in, so changing one line of a loaded talk meant typing the whole thing
    again — asked as "how to edit presentation".
    """
    if _runner is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    scenario = getattr(_runner, "_scenario", None)
    if scenario is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    # Same shape the saved-scenario endpoint hands back, so the builder has
    # exactly one thing to load.
    return JSONResponse({"scenario": scenario.model_dump(mode="json", exclude_none=True)})


@router.post("/speech")
async def push_speech(body: dict) -> JSONResponse:
    if _runner is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    fired = await _runner.on_speech((body or {}).get("text", ""))
    return JSONResponse({"fired": [b.id for b in fired], "status": _runner.status()})


def _status_payload() -> dict:
    """Everything the Present view needs to tell the presenter where they are.

    U263: the old status said `powerpoint_watching: true` as soon as a watcher
    OBJECT existed, which is not the same as a slideshow being on screen - the
    one thing the presenter actually needs to know before walking on stage.
    """
    if _runner is None:
        return {"active": False}
    out: dict = {"active": True, **_runner.status()}

    state = _watcher.state if _watcher is not None else None
    out["watching"] = _watcher is not None
    out["slides_app"] = state.app if state else ""
    out["deck"] = state.deck if state else ""
    out["slide"] = state.slide if state else 0
    out["slide_total"] = state.total if state else 0
    # "waiting" is the honest middle state: we ARE watching, there is just no
    # slideshow yet. It used to be indistinguishable from "no cues for you".
    out["slides_state"] = (
        "off" if _watcher is None else ("live" if state else "waiting")
    )
    # U266: "waiting" assumes he is able to look. When the library that reads
    # the slideshow is missing he never can, and an endless "waiting for your
    # slideshow" while the slideshow is up is a lie the presenter can do
    # nothing with. Say which of the two it is.
    if state:
        out["slides_blocker"] = ""
    else:
        from aura_brain.slides_watcher import read_blocker  # noqa: PLC0415

        out["slides_blocker"] = read_blocker()

    warnings: list[dict] = []
    if state is not None and _runner is not None:
        from aura_brain import deck_check

        scenario = getattr(_runner, "_scenario", None)
        if scenario is not None:
            warnings = [
                {"kind": w.kind, "message": w.message}
                for w in deck_check.check(
                    expected_deck=getattr(scenario, "pptx", "") or "",
                    actual_deck=state.deck,
                    total_slides=state.total,
                    slide_triggers=deck_check.slide_triggers(scenario),
                )
            ]
    out["deck_warnings"] = warnings
    return out


@router.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(_status_payload())


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


# ------------------------------------------------------------------
# U207: saved scenarios — build once in the app, reuse (no re-pasting)
# ------------------------------------------------------------------

def _store() -> Any:
    from aura_brain.scenario_store import ScenarioStore

    return ScenarioStore()


@router.get("/scenarios")
async def list_scenarios() -> JSONResponse:
    return JSONResponse({"scenarios": _store().list()})


@router.get("/scenarios/{name}")
async def get_scenario(name: str) -> JSONResponse:
    raw = _store().get_yaml(name)
    if raw is None:
        return JSONResponse({"error": f"unknown scenario {name!r}"}, status_code=404)
    structured = None
    try:
        structured = Scenario.model_validate(yaml.safe_load(raw)).model_dump(exclude_none=True)
    except Exception:  # noqa: BLE001 — hand-edited file; still hand back the raw text
        pass
    return JSONResponse({"name": name, "yaml": raw, "scenario": structured})


@router.put("/scenarios/{name}")
async def save_scenario(name: str, body: dict) -> JSONResponse:
    try:
        scenario, raw = _scenario_from_body(body or {})
        saved_name, scenario = _store().save(name, raw_yaml=raw, scenario=scenario)
    except Exception as exc:  # noqa: BLE001 — validation / bad name
        # U282: SAVE never got the treatment LOAD did. `_readable` was written
        # in U264 for exactly this and wired into one route; pressing Save
        # still returned the raw Pydantic dump — field paths, the repr of every
        # offending beat, `[type=value_error, ...]` and a link to the pydantic
        # docs — as a wall of red under the builder.
        return JSONResponse({"error": _readable(exc)}, status_code=422)
    return JSONResponse({"name": saved_name, "title": scenario.title,
                         "beats": len(scenario.beats)})


@router.delete("/scenarios/{name}")
async def delete_scenario(name: str) -> JSONResponse:
    return JSONResponse({"deleted": _store().delete(name)})
