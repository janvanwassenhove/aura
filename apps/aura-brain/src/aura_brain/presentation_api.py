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

import asyncio
import logging
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from orchestrator.scenario_runner import ScenarioRunner
from shared_schemas.events.system import (
    PresentationBeatFired,
    PresentationOverlayChanged,
)
from shared_schemas.presentation import Scenario, split_persona_segments

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presentation", tags=["presentation"])

_robot: Any = None      # RobotClient
_bus: Any = None        # AsyncEventBus
_pipeline: Any = None    # OrchestratorPipeline — for tool-backed improvise (U208)
_runner: ScenarioRunner | None = None
# U389: the talk that was loaded, kept after End so it can run again or be
# removed. End used to forget it, and "run again" rebuilt it from the HUD's
# display rows — every slide and keyword cue turned into a hand press.
_kept: Scenario | None = None
_watcher: Any = None    # PowerPointWatcher | None
# U349: why the last line did not sound the way the scenario asked, if it
# didn't. Empty means every persona it named was found.
_voice_note = ""

_SESSION = "presentation"

# U349: the silence between two characters in one line. Long enough to read as
# a hand-over, short enough not to read as a pause in the talk.
_HANDOVER_MS = 120


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

def _character(persona: str) -> Any:
    """The brain character behind a scenario's persona id, or None.

    Looked up case-insensitively: the id is typed by hand into YAML, and
    `[persona:Kids_Companion]` meaning nothing would be a cruel way to find out.
    """
    if not persona:
        return None
    from aura_brain.characters import CharacterStore  # noqa: PLC0415

    wanted = persona.strip().lower()
    try:
        return next((c for c in CharacterStore().all() if c.id.lower() == wanted), None)
    except OSError as exc:                      # unreadable store — not fatal
        logger.warning("character store unreadable: %s", exc)
        return None


def _voice_for(persona: str) -> tuple[str, float, str]:
    """(voice, speed, what went wrong) for one persona id.

    An id nobody recognises still gets spoken — losing a line mid-talk over a
    typo would be worse — but in the presentation's own voice, and the third
    element says so. Constitution XI: the degradation is reported, never
    dressed up as the thing that was asked for.
    """
    from aura_brain import voice  # noqa: PLC0415

    if not persona:
        return voice.resolve_voice(mode="presentation"), 1.0, ""
    character = _character(persona)
    if character is None:
        return voice.resolve_voice(mode="presentation"), 1.0, (
            f"persona {persona!r} is not a character here, so that line was "
            f"spoken in the presentation voice")
    return (voice.resolve_voice(mode="presentation",
                                character_voice=character.voice_id),
            character.voice_speed or 1.0, "")


def _direction_for(beat: Any, persona: str, scenario: Any) -> str:
    """U409: how a stretch of a line is delivered — the narrowest that says.

    The beat's own `direction`; else the persona speaking that stretch (its
    `voice_direction`), so a voice handed over mid-line with `[persona:x]`
    speaks its own way; else the talk's `direction`; else nothing.
    """
    own = (getattr(beat, "direction", "") or "").strip()
    if own:
        return own
    if persona:
        character = _character(persona)
        theirs = (getattr(character, "voice_direction", "") or "").strip()
        if theirs:
            return theirs
    return (getattr(scenario, "direction", "") or "").strip()


def _scenario_now() -> Any:
    """The talk that is loaded — running, or ended and kept (U389)."""
    if _runner is not None:
        return getattr(_runner, "_scenario", None)
    return _kept


def _takes(beat: Any, scenario: Any, text: str | None = None) -> list[tuple[Any, str]]:
    """Each stretch of the line as it is to be performed — words, voice, speed,
    direction and model — with what went wrong choosing its voice, if anything.

    The one place both recording ahead (U409) and speaking at the cue decide
    this, so a recording made at load is the take the cue asks for.
    """
    from aura_brain import voice  # noqa: PLC0415 — optional at import time
    from aura_brain.recordings import Take  # noqa: PLC0415

    persona = getattr(beat, "persona", "") or ""
    named_voice = (getattr(beat, "voice", "") or "").strip().lower()
    named_speed = float(getattr(beat, "speed", 0.0) or 0.0)
    line = getattr(beat, "text", "") if text is None else text
    model = voice.tts_model()
    out: list[tuple[Any, str]] = []
    for segment in split_persona_segments(line or "", persona):
        # U273: a beat persona outranks the Present screen's voice — the same
        # order every other speaking path uses.
        voice_id, speed, why = _voice_for(segment.persona)
        # U360: a voice named on the beat overrides every segment's — including
        # the inline `[persona:x]` ones, because a line cannot both be "all in
        # onyx" and "this bit in somebody else's voice".
        if named_voice or named_speed:
            voice_id, speed = named_voice or voice_id, named_speed or speed
        out.append((Take(text=segment.text, voice=voice_id, speed=float(speed),
                         direction=_direction_for(beat, segment.persona, scenario),
                         model=model), why))
    return out


async def _joined(takes: list[Any]) -> str | None:
    """U410: a line as the robot plays it — its recordings (awaited if still
    being made), joined into one utterance. None if any of it failed."""
    from aura_brain import recordings, voice  # noqa: PLC0415

    store = recordings.store()
    audio = await asyncio.gather(*(store.take(t) for t in takes))
    if not all(audio):
        return None
    return voice.join_pcm_b64(list(audio), _HANDOVER_MS)


def _send_ahead(beat_ids: list[str] | None = None, *, replace: bool = True) -> None:
    """U410: send the talk's recorded lines to the robot before their cues."""
    from aura_brain import robot_takes  # noqa: PLC0415

    ids = list(_plan) if beat_ids is None else beat_ids
    lines = []
    for beat_id in ids:
        takes = _plan.get(beat_id) or []
        if takes:
            lines.append((beat_id, lambda t=takes: _joined(t)))
    try:
        robot_takes.store().send_ahead(_robot, lines, replace=replace)
    except Exception as exc:  # noqa: BLE001 — the cue sends the audio, as before
        logger.warning("the talk's lines could not be sent to the robot ahead: %s", exc)


#: U409: the takes each fixed line of the loaded talk was recorded as, so the
#: status (polled every second while presenting) does not re-read every
#: persona file for every beat.
_plan: dict[str, list[Any]] = {}


def _prepare(scenario: Scenario) -> None:
    """U409: record every fixed line of the talk in the background.

    Only `speak` beats: an improvised line does not exist until it fires. Each
    persona's stretch is its own take, in its own voice, speed and direction.
    A line already recorded — reloaded, run again, or rehearsed before a
    restart — is not recorded again.
    """
    from aura_brain import recordings  # noqa: PLC0415

    _plan.clear()
    for beat in scenario.beats:
        if beat.mode == "speak":
            _plan[beat.id] = [take for take, _ in _takes(beat, scenario)]
    try:
        recordings.store().prepare(t for takes in _plan.values() for t in takes)
    except Exception as exc:  # noqa: BLE001 — the cue records it then, as before
        logger.warning("recording the talk's lines could not start: %s", exc)
    _send_ahead()                    # U410: and to the robot, before their cues


def _recordings_status(scenario: Any) -> dict:
    """U409: lines ready, being recorded, failed — out of the fixed lines.

    Counted per line, not per voice: a line with two voices is one line, ready
    when both are. A failed take is not ready; it is tried again when its beat
    fires, and if that fails too the beat says so (speech_error, U269).
    """
    from aura_brain import recordings  # noqa: PLC0415

    store = recordings.store()
    beats: dict[str, str] = {}
    for beat in getattr(scenario, "beats", []):
        if beat.mode != "speak":
            continue
        takes = _plan.get(beat.id) or [take for take, _ in _takes(beat, scenario)]
        states = {store.state(t) for t in takes}
        for state in (recordings.FAILED, recordings.RENDERING, recordings.WAITING):
            if state in states:
                beats[beat.id] = state
                break
        else:
            beats[beat.id] = recordings.READY
    count = list(beats.values())
    # U410: which lines the robot already holds, so the cue names them.
    from aura_brain import robot_takes  # noqa: PLC0415

    held = robot_takes.store()
    on_robot = sum(1 for beat_id in beats if held.holds_line(beat_id))
    return {"ready": count.count(recordings.READY), "total": len(count),
            "failed": count.count(recordings.FAILED),
            "rendering": count.count(recordings.RENDERING), "beats": beats,
            "on_robot": on_robot, "robot": held.state(), "sending": held.sending()}


async def _speak(text: str, beat: Any = None) -> None:
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

    U349: `persona` is the character the beat belongs to, and the line itself
    may hand over to others with `[persona:x]`. Each stretch is synthesized in
    its own voice and speed, and the pieces are joined into ONE utterance
    before they reach the robot — the robot decides loudness per utterance
    (FR-019), so separate calls would turn a change of character into a change
    of volume as well.

    U360: the whole beat arrives now, because a line may also name a `voice`
    and `speed` outright — the narrower instruction, so it wins over the
    persona's. That is what a generated scenario reaches for when it wants one
    gag in a second voice rather than a character behind the whole beat.
    """
    global _voice_note
    if not text:
        return
    if _robot is None:
        raise RuntimeError("no robot is connected, so nothing could be said out loud")

    from aura_brain import recordings, voice  # noqa: PLC0415 — optional at import time

    persona = getattr(beat, "persona", "") or ""
    takes = _takes(beat, _scenario_now(), text)
    if not takes:
        return
    # U409: a fixed line plays its recording — the same take every run, and no
    # round-trip at the cue; one still being recorded is waited for, never
    # asked for twice. An improvised line is new every time and is performed
    # now. Either way the stretches go together, not one after the other: a
    # slide-triggered beat has 500 ms to start speaking (SC-002).
    fixed = getattr(beat, "mode", "") == "speak" and text == getattr(beat, "text", None)
    store = recordings.store()
    audio = await asyncio.gather(*(
        store.take(take) if fixed else recordings.perform(take) for take, _ in takes))

    if any(part is None for part in audio):
        # Text-only reaches the robot as a log line. Saying so is the whole
        # point: "he is mute because there is no TTS key" and "he is mute
        # because the robot is off" need different fixes. A line that lost
        # only ONE of its voices is not played either — a sentence quietly
        # missing from the middle of a talk is the harder failure to notice.
        raise RuntimeError(
            "speech could not be synthesized (no TTS key or the provider "
            "failed), so the robot had nothing to play")

    notes = [why for _, why in takes if why]
    # U409: constitution XI — a direction the model cannot take is said, not
    # quietly dropped. The line was still spoken, undirected.
    directed = next((t.direction for t, _ in takes if t.direction), "")
    if directed and not voice.direction_applies():
        notes.append(f"the TTS model {voice.tts_model()} cannot take a direction, "
                     f"so {directed!r} was not applied")
    _voice_note = " ".join(dict.fromkeys(notes))
    # U364: the robot's speaker, or this laptop if that is what the owner
    # chose. The joined utterance is the same either way.
    from aura_brain import speech_out  # noqa: PLC0415

    line = " ".join(take.text for take, _ in takes)
    joined = voice.join_pcm_b64(list(audio), _HANDOVER_MS)
    # U410: a fixed line may already be on the robot; then its name is enough.
    # Named by its audio, so a new take is never mistaken for the one it replaced.
    line_key = ""
    if fixed:
        from aura_brain import robot_takes  # noqa: PLC0415

        line_key = robot_takes.key_of(joined)
        robot_takes.store().named[str(getattr(beat, "id", ""))] = line_key
    await speech_out.deliver(
        _robot, _bus, line, joined,
        # U400: announced as it starts, with its real length, for the overlay.
        subtitle={"text": line, "persona": persona,
                  "beat_id": str(getattr(beat, "id", "") or "")},
        take=line_key)


async def _gesture(name: str) -> None:
    if _robot is None or not name:
        return
    try:
        from shared_schemas.robot.models import MotionCommand

        await _robot.execute_motion(MotionCommand(motion_id=name))
    except Exception as exc:  # noqa: BLE001
        logger.debug("presentation gesture %r failed: %s", name, exc)


async def _generate(topic: str, guardrails: str, engine: str, persona: str = "") -> str:
    """Improvise a spoken line about `topic`. Text only — the runner speaks it.

    U208: `engine: pipeline` runs the FULL agentic loop (tools included) so a
    beat can pull live data — calendar, music, a lookup — and speak the result.
    `announce=False` keeps the pipeline from auto-speaking it (the runner speaks
    it once, so the subtitle and the robot stay in sync). Any other engine is a
    single LLM completion: faster, no tools, can't wander mid-talk.

    U349: a beat's persona shapes the WORDS as well as the voice. A butler's
    line and a kids-companion's line differ in what they say long before they
    differ in timbre, so the character's own note is appended here. Appended,
    never substituted (FR-004): a persona that replaces the whole instruction
    is how the language rule got deleted in U291.
    """
    guard = guardrails or "Keep it to 1-2 sentences."
    character = _character(persona)
    in_character = f" {character.system_note()}" if character is not None else ""
    if engine == "pipeline" and _pipeline is not None:
        prompt = (
            "You are co-presenting live. In ONE short spoken remark, first "
            f"person, no markdown, address this — using tools if you need live "
            f"data: {topic}. {guard}{in_character}"
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
        "markdown. " + guard + in_character
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
    """Runner events → the robot, and → the bus so the presenter view can
    render subtitles."""
    # U394: a slide or a beat changed whether he wanders or follows. Told to
    # the ROBOT, so it must not wait on the subtitle bus below — found by the
    # example-scenario walk, which runs without one.
    if event.get("type") == "robot":
        await _wander_follows_the_show()
        return
    if _bus is None:
        return
    # U352: the overlay is a separate window with its own store, so a beat that
    # moves it has to cross an explicit channel. It crosses both: this one
    # reaches a window that is already open, and `overlay_visible` in the
    # status reaches one opened halfway through the talk.
    if event.get("type") == "overlay":
        await _bus.publish(PresentationOverlayChanged(
            session_id="presentation", visible=bool(event.get("visible", True)),
            beat_id=event.get("beat", "")))
        return
    if event.get("type") != "beat_done":
        return
    slide = _runner.current_slide if _runner else None
    beat_id = event.get("beat", "")
    mode = next((b.mode for b in _runner._scenario.beats if b.id == beat_id), "") if _runner else ""
    await _bus.publish(PresentationBeatFired(
        session_id="presentation", beat_id=beat_id, mode=mode,
        spoken=event.get("spoken", ""), slide_number=slide,
        persona=event.get("persona", "")))


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
    global _runner, _watcher, _voice_note, _kept
    try:
        scenario, _ = _scenario_from_body(body or {})
    except Exception as exc:  # noqa: BLE001 — bad YAML / failed validation
        return JSONResponse({"error": _readable(exc)}, status_code=422)

    await _stop_watcher()
    # U349: the note describes the line that was last spoken. Carried into
    # the next talk it would accuse it of the previous one's typo.
    _voice_note = ""
    _runner = ScenarioRunner(
        scenario, speak=_speak, generate=_generate, gesture=_gesture, on_event=_on_event)
    _kept = scenario
    _prepare(scenario)               # U409: every fixed line, before its cue

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

    await _wander_follows_the_show()
    return JSONResponse(_status_payload())


def stage_robot() -> dict:
    """U394: what the running talk asks of his body — None where it does not say."""
    if _runner is None:
        return {"wander": None, "follow_me": None}
    st = _runner.status()
    return {"wander": st.get("wander"), "follow_me": st.get("follow_me")}


async def _wander_follows_the_show() -> None:
    """U393: on stage only the scenario moves and speaks (U334), so wandering
    pauses for the talk and comes back after it."""
    try:
        from aura_brain import wander  # noqa: PLC0415

        await wander.apply(_robot)
    except Exception as exc:  # noqa: BLE001 — never break a load for it
        logger.debug("wander re-apply failed: %s", exc)


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


@router.post("/rerecord")
async def rerecord(body: dict | None = None) -> JSONResponse:
    """U409: another take of one line (`beat_id`), or of every fixed line.

    The take that is there is dropped and a new one recorded in the background;
    the next cue plays the new one, and every run after it. 409 when no talk is
    loaded, 404 for a beat that is not in it, 422 for one that is improvised —
    it has no recording, it is written when it fires.
    """
    from aura_brain import recordings  # noqa: PLC0415

    scenario = _scenario_now()
    if scenario is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    beat_id = str((body or {}).get("beat_id") or "").strip()
    if beat_id:
        beat = next((b for b in scenario.beats if b.id == beat_id), None)
        if beat is None:
            return JSONResponse({"error": f"there is no beat {beat_id!r} in this talk"},
                                status_code=404)
        if beat.mode != "speak":
            return JSONResponse(
                {"error": f"{beat_id!r} is {beat.mode}: it is written when it fires, "
                          f"so there is no recording to take again"}, status_code=422)
        targets = [beat]
    else:
        targets = [b for b in scenario.beats if b.mode == "speak"]
    takes = []
    for beat in targets:
        _plan[beat.id] = [take for take, _ in _takes(beat, scenario)]
        takes += _plan[beat.id]
    store = recordings.store()
    store.forget(takes)
    store.prepare(takes)
    _send_ahead([b.id for b in targets], replace=False)   # U410: the new take, ahead
    return JSONResponse(_status_payload())


@router.get("/scenario")
async def active_scenario() -> JSONResponse:
    """The scenario that is loaded, so it can be EDITED rather than retyped.

    U267: "New scenario" opened an empty builder and there was no other way
    in, so changing one line of a loaded talk meant typing the whole thing
    again — asked as "how to edit presentation".
    """
    scenario = getattr(_runner, "_scenario", None) if _runner is not None else _kept
    if scenario is None:
        return JSONResponse({"error": "no presentation loaded"}, status_code=409)
    # Same shape the saved-scenario endpoint hands back, so the builder has
    # exactly one thing to load. U389: `running` says whether it is on now or
    # was ended and kept.
    return JSONResponse({"scenario": scenario.model_dump(mode="json", exclude_none=True),
                         "running": _runner is not None})


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
        if _kept is None:
            return {"active": False}
        # U389: ended, not gone. Enough for any window to offer Run again and
        # Remove; the scenario itself is one GET away.
        return {"active": False, "kept": {"title": _kept.title,
                                          "beats_total": len(_kept.beats)}}
    out: dict = {"active": True, **_runner.status()}
    # U349: he was heard, but not as the scenario asked. Distinct from
    # speech_error, which means he was not heard at all.
    out["voice_note"] = _voice_note
    # U409: which lines are recorded and ready to play on their cue.
    scenario = getattr(_runner, "_scenario", None)
    if scenario is not None:
        out["recordings"] = _recordings_status(scenario)

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


@router.post("/end")
async def end_presentation() -> JSONResponse:
    """U389: stop the show and keep the talk — it can run again, be edited,
    or be removed. Ending used to be the same call as removing."""
    global _runner, _voice_note
    await _stop_watcher()
    _runner = None
    _voice_note = ""
    await _wander_follows_the_show()
    return JSONResponse(_status_payload())


@router.delete("/scenario")
async def clear_scenario() -> JSONResponse:
    """Remove the talk: stop it if it runs, and forget it."""
    global _runner, _voice_note, _kept
    await _stop_watcher()
    _runner = None
    _kept = None
    _voice_note = ""
    await _wander_follows_the_show()
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
