"""aura-brain — unified FastAPI process for the laptop-side modules.

Phase 1, step 1 (this file): the inert SCAFFOLD — one FastAPI app that owns the
single shared ``AsyncEventBus`` and the ``WebSocketBroadcaster``, exposing
``/health`` and ``/ws/events``. No service routers are mounted yet.

Phase 1, step 2 (next): mount each module's router against THIS shared bus, in
the order below (smallest blast radius first). See ``docs/phase-1-design.md``.

    MOUNT ORDER (step 2):
      1. memory      — routes.init(store, bus);            include_router
      2. identity    — refactor app-level routes -> APIRouter; include_router
      3. connector   — routes.init(registry, bus);         include_router
      4. conversation— routes.init(stt, tts, bus, ...);     include_router
      5. orchestrator— routes.init(pipeline, ... bus);      include_router

Each module's ``routes.init(...)`` is called with the ONE bus created here so the
broadcaster carries the whole event stream (today each service has its own bus).
The seams (in-process vs HTTP) are flipped per ``docs/phase-1-design.md`` step 3 —
NOT in this scaffold.

The brain↔robot-runtime boundary stays a network hop (the Pi) and is never merged.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared_events.bus import AsyncEventBus
from shared_events.broadcaster import WebSocketBroadcaster


class BrainContext:
    """Holds the process-wide singletons shared by all mounted modules.

    In step 2 this grows to own the MemoryStore, TokenStore, connector registry,
    pipeline, persona manager, heartbeat, etc. — all built once and shared in
    process instead of reached over HTTP.
    """

    def __init__(self) -> None:
        self.bus = AsyncEventBus()
        self.broadcaster = WebSocketBroadcaster(self.bus)
        # Module singletons (populated in lifespan as modules are mounted).
        self.memory_store = None
        self._reminder_scheduler = None
        self.connector_registry = None
        self.knowledge_store = None
        self.person_memory = None  # U109: PersonMemory | None
        self.proactive = None      # U110: ProactiveEngine | None
        self.pipeline = None
        self.recognition_gallery = None  # U127: per-person snapshots
        self._perception = None
        self._robot_bridge = None
        self._maintenance = None
        self._voice_loop = None
        self._offline_queue = None
        self._webhook_dispatcher = None
        self._heartbeat = None
        # One ASGI client routes all intra-brain HTTP-shaped calls in-process
        # (connector, memory, orchestrator) — the Phase 1 seams.
        self._inproc_client = None


ctx = BrainContext()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await ctx.bus.start()

    # One in-process ASGI client for all intra-brain seams (U8/U9): connector,
    # memory, orchestrator calls route back into THIS app — no network hop.
    import httpx
    ctx._inproc_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://aura-brain",
    )

    # --- U1: memory module (shares ctx.bus) ---
    # Ensure the default file-backed SQLite dir exists for real runs (tests
    # override DATABASE_URL with :memory:).
    if "/:memory:" not in os.environ.get("DATABASE_URL", ""):
        os.makedirs("./data", exist_ok=True)

    from memory_service import routes as memory_routes
    from memory_service.db.session import init_db
    from memory_service.scheduler import ReminderScheduler
    from memory_service.store import SQLiteMemoryStore

    # --- U19d: knowledge store (ADR-008). Encrypted at rest if a passphrase is
    # set (OMK via scrypt), else in-memory for dev. ---
    from aura_brain import knowledge_api
    from shared_schemas.knowledge import (
        EncryptedKnowledgeStore,
        InMemoryKnowledgeStore,
        crypto,
    )

    _kpass = os.environ.get("KNOWLEDGE_PASSPHRASE")
    if _kpass:
        _salt = os.environ.get("KNOWLEDGE_SALT", "aura-knowledge").encode().ljust(16, b"0")[:16]
        # U29: ciphertext bundles persist across restarts (ciphertext-only file).
        _kpath = os.environ.get("KNOWLEDGE_DB_PATH", "./data/knowledge.enc.json")
        ctx.knowledge_store = EncryptedKnowledgeStore(
            crypto.derive_omk(_kpass, _salt), path=_kpath,
        )
    else:
        ctx.knowledge_store = InMemoryKnowledgeStore()
    knowledge_api.set_store(ctx.knowledge_store)
    knowledge_api.set_omk_loaded(bool(_kpass))

    # U19c: step-up gate for destructive knowledge operations (ADR-008 §9).
    from aura_brain.stepup_gate import StepUpGate

    _stepup_gate = StepUpGate()  # reads STEP_UP_WEBHOOK_URL + BRAIN_BASE_URL from env
    knowledge_api.set_stepup_gate(_stepup_gate)

    await init_db()
    ctx.memory_store = SQLiteMemoryStore()
    memory_routes.set_store(ctx.memory_store)
    session_id = os.environ.get("DEFAULT_SESSION_ID", "default")
    ctx._reminder_scheduler = ReminderScheduler(ctx.memory_store, ctx.bus, session_id=session_id)
    await ctx._reminder_scheduler.start()

    # U110: proactive Richie — voice fired reminders and a daily briefing out of
    # his own initiative (reusing the embodiment pipeline via ResponseDrafted).
    from aura_brain.proactive import ProactiveEngine
    from shared_schemas.events.system import ReminderTriggered

    ctx.proactive = ProactiveEngine(ctx.bus, session_id=session_id)
    ctx.bus.subscribe(ReminderTriggered, ctx.proactive.on_reminder)

    # --- U3: connector module ---
    from connector_service import routes as connector_routes
    from connector_service.registry import ConnectorRegistry
    from shared_config import ConnectorServiceSettings

    # U7 seam: connectors fetch tokens from identity in-process (no HTTP hop).
    from identity_service.main import get_valid_token as _identity_token

    connector_registry = ConnectorRegistry(
        settings=ConnectorServiceSettings(), token_fetcher=_identity_token,
    )
    connector_registry.build()
    primary = connector_registry.get_primary_m365()
    if primary is not None:
        connector_routes.set_connector(primary)
    connector_routes.set_registry(connector_registry)
    ctx.connector_registry = connector_registry

    # --- U4: conversation module (shares ctx.bus) ---
    # Default to the lightweight null STT/TTS in-process; real transport (Realtime)
    # is selected via STT_PROVIDER/TTS_PROVIDER. orchestrator/memory stay URL-based
    # here; in-process seams are flipped in later units.
    os.environ.setdefault("STT_PROVIDER", "null")
    os.environ.setdefault("TTS_PROVIDER", "null")
    from conversation_runtime import routes as conversation_routes
    from conversation_runtime.main import _build_stt, _build_tts
    from conversation_runtime.session_manager import SessionManager

    conversation_routes.init(
        _build_stt(), _build_tts(), ctx.bus, SessionManager(),
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8003"),
        memory_url=os.environ.get("MEMORY_SERVICE_URL", "http://memory-service:8005"),
        inproc_client=ctx._inproc_client,  # U9: memory + orchestrator in-process
    )

    # --- U5: orchestrator module (shares ctx.bus) ---
    from orchestrator import routes as orchestrator_routes
    from orchestrator.approval_manager import ApprovalManager
    from orchestrator.context_builder import ContextBuilder
    from orchestrator.fallback_agent import FallbackAgent
    from orchestrator.gateway import GatewayManager
    from orchestrator.intent_router import IntentRouter
    from orchestrator.offline_queue import OfflineQueue
    from orchestrator.persona_manager import PersonaManager
    from orchestrator.pipeline import OrchestratorPipeline
    from orchestrator.presentation import PresentationManager
    from orchestrator.webhook_dispatcher import WebhookDispatcher
    from shared_personas import Persona

    mode = os.environ.get("ACTIVE_PERSONA", "work")
    try:
        persona = Persona(mode)
    except ValueError:
        persona = Persona.WORK

    intent_router = IntentRouter(mode=mode)
    approval_mgr = ApprovalManager(ctx.bus, session_id=session_id)
    context_builder = ContextBuilder()
    persona_mgr = PersonaManager(initial_persona=persona)
    fallback_agent = FallbackAgent(memory_client=ctx._inproc_client)  # U9

    ctx._offline_queue = OfflineQueue(ctx.bus)
    await ctx._offline_queue.open()

    # U8 seam: the pipeline calls the connector module in-process via ASGI.
    ctx.pipeline = OrchestratorPipeline(
        ctx.bus, intent_router, approval_mgr, context_builder, persona_mgr,
        fallback_agent=fallback_agent, offline_queue=ctx._offline_queue,
        connector_client=ctx._inproc_client,
    )

    # U20: outbound dev-agent tool (gated by DEV_AGENT_ENABLED env var).
    from orchestrator.dev_agent import DevAgentTool

    def _apply_dev_agent(enabled: bool) -> None:
        ctx.pipeline._dev_agent = DevAgentTool(approval_mgr, ctx.bus) if enabled else None

    _apply_dev_agent(os.environ.get("DEV_AGENT_ENABLED", "false").lower() == "true")

    # U40: capabilities center — live-apply hooks for the toggles.
    from aura_brain import capabilities_api

    capabilities_api.set_live_hook("dev_agent", _apply_dev_agent)
    # speak_replies + app_launch read the env per use → toggling env is enough.
    capabilities_api.set_live_hook("speak_replies", lambda _on: None)
    capabilities_api.set_live_hook("app_launch", lambda _on: None)

    # U50: gated Computer Use — screenshot + mouse/keyboard control of the laptop.
    # Default OFF; needs ANTHROPIC_API_KEY + the [computeruse] extra (pyautogui).
    def _apply_computer_use(enabled: bool) -> None:
        from aura_brain.computer_use import create_default_agent

        os.environ["COMPUTER_USE_ENABLED"] = "true" if enabled else "false"
        ctx.pipeline._computer_use = create_default_agent() if enabled else None

    _apply_computer_use(os.environ.get("COMPUTER_USE_ENABLED", "false").lower() == "true")
    capabilities_api.set_live_hook("computer_use", _apply_computer_use)

    # U59: hand the shared skill store to the agentic loop.
    from aura_brain import skills_api as _skills_api

    if _skills_api.get_store() is not None:
        ctx.pipeline.set_skill_store(_skills_api.get_store())

    # U19e: judgment/anticipation layer — injects minimal personal context per turn.
    from shared_schemas.knowledge import JudgmentLayer
    from shared_schemas.events.perception import PersonRecognized

    _judgment = JudgmentLayer(ctx.knowledge_store)
    ctx.pipeline.set_judgment_layer(_judgment)

    # U109: long-term memory per person — distil each exchange into a durable
    # `memory` fact (encrypted at rest, injected into future turns). Gated by
    # PERSON_MEMORY_ENABLED so tests / minimal installs stay quiet.
    if os.environ.get("PERSON_MEMORY_ENABLED", "true").lower() == "true":
        from orchestrator.config import model_for_role
        from orchestrator.llm import openai_chat
        from aura_brain.person_memory import PersonMemory

        ctx.person_memory = PersonMemory(
            ctx.knowledge_store, openai_chat,
            model_getter=lambda: model_for_role("chat"),
            every=int(os.environ.get("PERSON_MEMORY_EVERY", "4")),
        )
        ctx.pipeline.set_memory_hook(ctx.person_memory.record)

    # U36: robot proxy for the console (video panel + quick actions) and the
    # greet-on-recognition flow. One RobotClient serves both.
    from aura_brain import robot_api
    from aura_brain.robot_client import RobotClient
    from shared_schemas.events.conversation import ResponseDrafted
    from shared_schemas.robot.models import MotionCommand

    _robot = RobotClient()
    robot_api.init(_robot)

    # U36d: relay the robot's own event stream (speech/motion/behavior/mode)
    # to the console — it only listens to the brain's WebSocket.
    from aura_brain.robot_events import RobotEventBridge

    ctx._robot_bridge = RobotEventBridge(
        ctx.broadcaster,
        os.environ.get("ROBOT_RUNTIME_URL", "http://robot-runtime:8001"),
        robot_client=_robot,
    )
    ctx._robot_bridge.start()

    # U40: follow-me toggle applies live via the robot proxy.
    def _apply_follow_me(enabled: bool) -> None:
        import asyncio as _asyncio

        _asyncio.ensure_future(_robot.set_tracking(enabled))

    capabilities_api.set_live_hook("follow_me", _apply_follow_me)

    # U37: body-yaw follow — the torso turns with the tracked face.
    def _apply_body_follow(enabled: bool) -> None:
        import asyncio as _asyncio

        _asyncio.ensure_future(_robot.set_body_follow(enabled))

    capabilities_api.set_live_hook("body_follow", _apply_body_follow)

    # U84: conversation state machine + character personas.
    from aura_brain.characters import CharacterStore
    from aura_brain.conversation_manager import ConversationManager

    ctx.characters = CharacterStore()
    ctx.conversation = ConversationManager(stop_robot_audio=_robot.stop_audio)

    def _active_character_note() -> str:
        c = ctx.characters.active()
        ctx.conversation.character = c
        return c.system_note() if c else ""

    ctx.pipeline.set_character_provider(_active_character_note)

    # U36: EMBODIMENT — every assistant reply is spoken out loud on the robot
    # with a gesture matched to the content (greeting→wave, question→tilt,
    # excitement→gesture, default→nod). Toggle with SPEAK_REPLIES=false.
    from aura_brain import voice
    from aura_brain.embodiment import embodiment_plan

    async def _embody_reply(event: ResponseDrafted) -> None:
        text = (event.response_text or "").strip()
        # U100: sleep mode → stay completely quiet.
        if os.environ.get("ROBOT_ASLEEP", "false").lower() == "true":
            return
        # Read the flag per reply so the Capabilities toggle applies live.
        if os.environ.get("SPEAK_REPLIES", "true").lower() != "true":
            return
        if not text or text.startswith("[echo]"):
            return
        # U51: the active mode shapes the embodiment — silent_desk stays mute
        # and still, work nods with restraint, presentation/demo go expressive.
        try:
            persona_cfg = ctx.pipeline.persona_config
        except Exception:  # noqa: BLE001 — never let persona lookup kill speech
            persona_cfg = None
        speak, gesture, amplitude = embodiment_plan(text, persona_cfg)
        if not speak:
            return
        # U84: the active character shapes voice, speed and motion energy.
        character = ctx.characters.active() if hasattr(ctx, "characters") else None
        if character is not None:
            amplitude = min(1.0, amplitude * character.motion_scale())
            if character.robot_motion_style == "still":
                gesture = None
        # U111: emotion & mimicry — express the reply's tone with head/antennas.
        # A detected mood REPLACES the generic reply gesture (they'd fight over
        # the head). Off via EMOTION_ENABLED=false or a "still" character.
        if gesture is not None and os.environ.get("EMOTION_ENABLED", "true").lower() == "true":
            from aura_brain.mood import detect_mood, mood_motion

            mood_id = mood_motion(detect_mood(text))
            if mood_id is not None:
                gesture = mood_id
        try:
            if gesture is not None:
                await _robot.execute_motion(MotionCommand(
                    motion_id=gesture, speed=1.0, amplitude=amplitude, direction=None,
                ))
            # U54: streamed speech — first sentence starts playing while the
            # rest is still being synthesized (SPEAK_STREAMING=false → old path).
            # U65: the voice follows the global pref, with per-persona override.
            # U84: character voice/speed override; the speak runs as a
            # CANCELLABLE task registered with the conversation manager so a
            # barge-in cuts it (and the robot playback) instantly.
            capped = text[:600]  # cap TTS cost
            reply_voice = voice.resolve_voice(
                str(persona_cfg.name) if persona_cfg is not None else None)
            reply_speed = 1.0
            if character is not None:
                if character.voice_id:
                    reply_voice = character.voice_id
                reply_speed = character.voice_speed or 1.0

            async def _synth(chunk: str) -> str:
                return await voice.synthesize_b64(chunk, reply_voice, speed=reply_speed)

            # U83: streaming is default OFF — one synth + one continuous file
            # plays the whole answer smoothly (per-chunk playbin files gapped).
            async def _do_speak() -> None:
                if os.environ.get("SPEAK_STREAMING", "false").lower() == "true":
                    from aura_brain.streaming import stream_speech

                    async def _speak_chunk(chunk: str, audio_b64: str) -> None:
                        if ctx.conversation.tts_cancel.is_set():
                            raise asyncio.CancelledError
                        await _robot.speak(chunk, audio_b64=audio_b64)

                    await stream_speech(capped, _synth, _speak_chunk)
                else:
                    audio_b64 = await _synth(capped)
                    if ctx.conversation.tts_cancel.is_set():
                        return  # interrupted during synthesis — stay silent
                    await _robot.speak(capped, audio_b64=audio_b64)

            speak_task = asyncio.ensure_future(_do_speak())
            ctx.conversation.register_speak_task(speak_task)
            try:
                await speak_task
            except asyncio.CancelledError:
                logging.getLogger(__name__).info("speak task cancelled (barge-in)")
        except Exception as exc:  # robot offline → the console turn still shows
            logging.getLogger(__name__).debug("embodied reply failed: %s", exc)

    ctx.bus.subscribe(ResponseDrafted, _embody_reply)

    # U36e: voice input — the console mic posts audio here.
    from aura_brain import voice_api

    voice_api.init(ctx.pipeline, ctx.bus, session_id, robot=_robot)

    # U47: hands-free wake-word voice loop on the robot mic. Runs always but
    # only acts when VOICE_MODE=wake_word (read live). Each spoken reply opens
    # a follow-up window so a greeting/answer becomes a conversation.
    from aura_brain.voice_loop import VoiceLoop

    ctx._voice_loop = VoiceLoop(
        _robot, ctx.pipeline, ctx.bus, session_id=session_id,
        default_wake_word=os.environ.get("ASSISTANT_NAME", "AURA").lower(),
        manager=ctx.conversation,
        followup_s=0.0,  # U92: wake word required every turn by default
    )
    ctx.pipeline.set_cancel_event(session_id, ctx.conversation.llm_cancel)
    ctx._voice_loop.start()

    async def _voice_note_spoken(event: ResponseDrafted) -> None:
        if ctx._voice_loop is not None:
            ctx._voice_loop.note_spoken(event.response_text or "")

    ctx.bus.subscribe(ResponseDrafted, _voice_note_spoken)

    # U69: when AURA starts/controls music, the robot mic will hear lyrics —
    # tell the voice loop so it requires the wake word instead of treating
    # transcribed lyrics as conversation (the NOFX incident).
    from shared_schemas.events.orchestrator import ToolCallSucceeded as _TCS

    _MUSIC_TOOLS = {"play_music", "media_control", "next_track", "use_computer"}

    _dance_task: list = [None]  # single slot — one dance at a time

    async def _dance() -> None:
        """U77: groove along while the music plays — a loose loop of moves.
        DANCE_ON_MUSIC=false switches it off; stops early when a reply speaks."""
        import random
        import time as _time

        moves = ["nod", "tilt", "shake", "gesture", "wave"]
        end = _time.monotonic() + float(os.environ.get("DANCE_DURATION_S", "25"))
        try:
            while _time.monotonic() < end:
                await _robot.execute_motion(MotionCommand(
                    motion_id=random.choice(moves), speed=1.2,
                    amplitude=0.7 + random.random() * 0.3, direction=None,
                ))
                await asyncio.sleep(0.8 + random.random() * 0.6)
        except Exception:  # noqa: BLE001 — robot offline etc.: dance is best-effort
            pass

    async def _voice_note_music(event) -> None:
        if event.tool_name in _MUSIC_TOOLS and ctx._voice_loop is not None:
            ctx._voice_loop.note_music_started()
            if os.environ.get("DANCE_ON_MUSIC", "true").lower() == "true":
                if _dance_task[0] is None or _dance_task[0].done():
                    import asyncio as _a

                    _dance_task[0] = _a.ensure_future(_dance())

    ctx.bus.subscribe(_TCS, _voice_note_music)

    _last_greeted: dict[str, float] = {}
    _greet_cooldown = float(os.environ.get("GREET_COOLDOWN_S", "120"))

    async def _on_person_recognized(event: PersonRecognized) -> None:
        ctx.pipeline.set_active_person(event.person_id if event.known else None)
        # U100: sleep mode → recognize silently, no greeting.
        if os.environ.get("ROBOT_ASLEEP", "false").lower() == "true":
            return
        # Greet a KNOWN person: personalized text (the pipeline injects their
        # profile facts via the judgment layer, U19e). The pipeline publishes
        # ResponseDrafted → the embodiment handler above speaks it + waves.
        # A per-person cooldown avoids re-greeting when they briefly leave/return
        # the frame (which was flooding speech and cutting off replies, U49).
        if event.known and event.display_name and event.person_id:
            import time as _time

            now = _time.monotonic()
            if now - _last_greeted.get(event.person_id, 0.0) < _greet_cooldown:
                return
            _last_greeted[event.person_id] = now
            name = event.display_name
            # U85: varied greetings — never the same "Dag Jan" twice in a row.
            # A character's greeting_message wins when set; otherwise the LLM
            # gets a random angle to riff on (time of day, plans, callback to
            # a fact, playful, curious, …).
            character = ctx.characters.active() if hasattr(ctx, "characters") else None
            if character is not None and character.greeting_message:
                await ctx.bus.publish(ResponseDrafted(
                    session_id=session_id, response_text=character.greeting_message))
                return
            import random

            angle = random.choice([
                "reference the time of day",
                "ask what they're up to right now",
                "make a playful observation",
                "callback to one of their profile facts or interests",
                "sound genuinely curious about their day",
                "keep it ultra-short and warm",
                "offer to help with something concrete",
            ])
            try:
                await ctx.pipeline.orchestrate(
                    f"(system note: {name} just walked up and you recognized "
                    f"their face.) Greet {name} by name in ONE short spoken "
                    f"sentence. Vary it: this time, {angle}. Never start with "
                    f"the same words as your previous greeting. No lists.",
                    session_id,
                )
            except Exception as exc:
                logging.getLogger(__name__).debug("personalized greeting failed: %s", exc)
                await ctx.bus.publish(ResponseDrafted(
                    session_id=session_id,
                    response_text=f"Hello {name}! Good to see you.",
                ))

    ctx.bus.subscribe(PersonRecognized, _on_person_recognized)

    # U36e: react to hand gestures — an open palm ("hi!") gets a wave back.
    from shared_schemas.events.perception import GestureDetected

    _GESTURE_REACTIONS = {
        "open_palm": "wave",     # you wave → it waves back
        "thumbs_up": "gesture",  # you approve → it celebrates
    }

    async def _on_gesture(event: GestureDetected) -> None:
        motion = _GESTURE_REACTIONS.get(event.gesture)
        if motion is None:
            return
        try:
            await _robot.execute_motion(MotionCommand(
                motion_id=motion, speed=1.2, amplitude=0.7, direction=None,
            ))
        except Exception as exc:
            logging.getLogger(__name__).debug("gesture reaction failed: %s", exc)

    ctx.bus.subscribe(GestureDetected, _on_gesture)

    # U27: the presenter drives the robot (speech + synced gesture) over the
    # brain↔robot boundary via RobotClient.
    from aura_brain.robot_client import RobotClient

    presentation_mgr = PresentationManager(
        ctx.bus, session_id=session_id, robot=RobotClient(),
    )

    api_keys: dict[str, str] = {}
    for pair in os.environ.get("GATEWAY_KEYS", "").split(","):
        pair = pair.strip()
        if ":" in pair:
            kid, raw = pair.split(":", 1)
            api_keys[kid.strip()] = raw.strip()
    gateway_mgr = GatewayManager(
        api_keys=api_keys,
        rate_limit=int(os.environ.get("GATEWAY_RATE_LIMIT", "10")),
    )
    ctx._webhook_dispatcher = WebhookDispatcher(ctx.bus)

    orchestrator_routes.init(
        intent_router, approval_mgr, context_builder, persona_mgr, ctx.pipeline,
        presentation_mgr,
        gateway_mgr=gateway_mgr, webhook_dispatcher=ctx._webhook_dispatcher,
    )

    # --- U18: live perception loop — camera → face embedding → PersonRecognized.
    # Needs encryption (embeddings are biometric data). Started at boot when the
    # passphrase is in the env, or later via /setup/secure (in-app enable).
    from aura_brain import recognition_api, setup_api
    from aura_brain.perception import PerceptionLoop, build_embedder, build_gesture_detector

    # One perception loop serves BOTH gestures (no identity, always available)
    # and face recognition (added once the store is encrypted).
    if os.environ.get("GESTURES_ENABLED", "true").lower() == "true":
        _gesture_detector = build_gesture_detector()
    else:
        _gesture_detector = None

    # The face embedder runs from boot: it powers the unknown-visitor log
    # (U36f) even before recognition is enabled; it stores nothing itself.
    _boot_embedder = build_embedder(os.environ.get("FACE_EMBEDDER", "null"))

    from aura_brain.sightings import SightingLog

    _sighting_log = SightingLog()
    recognition_api.set_sightings(_sighting_log)

    # U127: per-person recognition snapshots (in-memory, gated to SENSITIVE).
    from aura_brain.recognition_gallery import RecognitionGallery

    ctx.recognition_gallery = RecognitionGallery()
    knowledge_api.set_recognition_gallery(ctx.recognition_gallery)

    ctx._perception = PerceptionLoop(
        ctx.bus, None, _robot, _boot_embedder,
        knowledge_store=ctx.knowledge_store,
        interval_s=float(os.environ.get("RECOGNITION_INTERVAL_S", "2.0")),
        session_id=session_id,
        gesture_detector=_gesture_detector,
        sighting_log=_sighting_log,
        gallery=ctx.recognition_gallery,
    )
    if _gesture_detector is not None or _boot_embedder.name != "null":
        ctx._perception.start()

    # U43-fix: gestures toggle live — attach/detach the detector on the loop.
    def _apply_gestures(enabled: bool) -> None:
        if enabled and _gesture_detector is not None:
            ctx._perception._gestures = _gesture_detector
            ctx._perception.start()
        else:
            ctx._perception._gestures = None

    capabilities_api.set_live_hook("gestures", _apply_gestures)

    def _start_recognition(omk: bytes) -> None:
        from shared_schemas.knowledge.recognition import EmbeddingMatcher

        _rec_matcher = EmbeddingMatcher(
            omk, path=os.environ.get("RECOGNITION_DB_PATH", "./data/recognition.enc.json"),
        )
        ctx._perception.set_matcher(_rec_matcher, _boot_embedder)
        ctx._perception._store = ctx.knowledge_store  # may have been swapped
        ctx._perception.start()  # no-op when already running
        recognition_api.init(
            _rec_matcher, _boot_embedder, _robot, ctx.knowledge_store,
            loop=ctx._perception,
        )

    def _swap_knowledge_store(new_store) -> None:
        """Live-swap to the encrypted store (in-app secure enable, U34-slice)."""
        from shared_schemas.knowledge import JudgmentLayer as _JL

        ctx.knowledge_store = new_store
        knowledge_api.set_store(new_store)
        knowledge_api.set_omk_loaded(True)
        ctx.pipeline.set_judgment_layer(_JL(new_store))

    if os.environ.get("RECOGNITION_ENABLED", "false").lower() == "true" and _kpass:
        _start_recognition(crypto.derive_omk(_kpass, _salt))

    setup_api.init(
        get_store=lambda: ctx.knowledge_store,
        swap_store=_swap_knowledge_store,
        start_recognition=_start_recognition,
        already_encrypted=lambda: knowledge_api.is_omk_loaded(),
    )

    # --- U36g: self-maintenance loop — the brain checks & heals itself.
    from aura_brain.maintenance import MaintenanceLoop

    def _make_maintenance() -> MaintenanceLoop:
        return MaintenanceLoop(
            ctx.bus, _robot,
            knowledge_encrypted=knowledge_api.is_omk_loaded,
            session_id=session_id,
            interval_s=float(os.environ.get("MAINTENANCE_INTERVAL_S", "300")),
        )

    if os.environ.get("MAINTENANCE_ENABLED", "true").lower() == "true":
        ctx._maintenance = _make_maintenance()
        ctx._maintenance.start()

    # U43-fix: maintenance toggles live — start/stop the loop.
    def _apply_maintenance(enabled: bool) -> None:
        import asyncio as _asyncio

        if enabled and ctx._maintenance is None:
            ctx._maintenance = _make_maintenance()
            ctx._maintenance.start()
        elif not enabled and ctx._maintenance is not None:
            _asyncio.ensure_future(ctx._maintenance.stop())
            ctx._maintenance = None

    capabilities_api.set_live_hook("maintenance", _apply_maintenance)

    # --- U14: heartbeat watches the REAL failure surface — the brain↔robot link
    # and upstream internet — not sibling containers (which no longer exist after
    # the collapse). Gated by env so it doesn't flap during tests.
    if os.environ.get("HEARTBEAT_ENABLED", "false").lower() == "true":
        from orchestrator.heartbeat import HeartbeatMonitor

        robot_url = os.environ.get("ROBOT_RUNTIME_URL", "http://robot-runtime:8001")
        hb_services = {"robot": f"{robot_url.rstrip('/')}/health"}
        upstream = os.environ.get("UPSTREAM_HEALTH_URL")  # e.g. the LLM/API endpoint
        if upstream:
            hb_services["upstream"] = upstream
        ctx._heartbeat = HeartbeatMonitor(ctx.bus, hb_services)
        ctx._heartbeat.start()
        ctx.pipeline.set_heartbeat_monitor(ctx._heartbeat)

    # --- U105: periodic source refresh — the persona graph keeps growing with
    # new blog posts. SOURCE_REFRESH_HOURS (default 168 = weekly, 0 = off);
    # gated like the heartbeat so it never runs during tests.
    _refresh_task = None
    if os.environ.get("SOURCE_REFRESH_ENABLED", "false").lower() == "true":
        from aura_brain.source_ingest import refresh_loop

        # Read the store via ctx so a wizard store-swap is picked up live.
        class _StoreProxy:
            def __getattr__(self, name):  # noqa: ANN001, ANN204
                return getattr(ctx.knowledge_store, name)

        _refresh_task = asyncio.ensure_future(refresh_loop(_StoreProxy()))

    # U110: daily-briefing loop — once a day at PROACTIVE_BRIEFING_TIME Richie
    # gives a short spoken brief (reminders for today). Empty time = off.
    _briefing_task = None

    async def _build_brief() -> str:
        name = os.environ.get("ASSISTANT_NAME", "AURA")
        try:
            reminders = await ctx.memory_store.get_reminders()
        except Exception:  # noqa: BLE001
            reminders = []
        if reminders:
            items = "; ".join(r.text for r in reminders[:5])
            return f"Goedemorgen! Je hebt {len(reminders)} herinnering{'en' if len(reminders) != 1 else ''} openstaan: {items}."
        return f"Goedemorgen! Er staan geen herinneringen open — een rustige start. Ik ben er als je iets nodig hebt."

    async def _briefing_loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                if ctx.proactive is not None:
                    await ctx.proactive.maybe_briefing(_build_brief)
            except Exception:  # noqa: BLE001 — never kill the loop
                logging.getLogger(__name__).exception("briefing loop error")

    if os.environ.get("PROACTIVE_BRIEFING_TIME", "").strip():
        _briefing_task = asyncio.ensure_future(_briefing_loop())

    yield

    if _briefing_task is not None:
        _briefing_task.cancel()
    if _refresh_task is not None:
        _refresh_task.cancel()
    if ctx._voice_loop is not None:
        await ctx._voice_loop.stop()
    if ctx._maintenance is not None:
        await ctx._maintenance.stop()
    if ctx._robot_bridge is not None:
        await ctx._robot_bridge.stop()
    if ctx._perception is not None:
        await ctx._perception.stop()
    if ctx._heartbeat is not None:
        await ctx._heartbeat.stop()
    if ctx._inproc_client is not None:
        await ctx._inproc_client.aclose()
    if ctx._webhook_dispatcher is not None:
        await ctx._webhook_dispatcher.close()
    if ctx._offline_queue is not None:
        await ctx._offline_queue.close()
    if ctx._reminder_scheduler is not None:
        await ctx._reminder_scheduler.stop()
    await ctx.bus.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="AURA Brain", version="0.1.0", lifespan=lifespan)

    origins = [o.strip() for o in
               os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
    # SEC: "*" with credentials lets any site make authenticated cross-origin
    # calls (and browsers reject the combo anyway). If someone sets a wildcard,
    # drop credentials rather than silently running an insecure config.
    allow_credentials = "*" not in origins
    if not allow_credentials:
        logging.getLogger("aura_brain").warning(
            "CORS_ORIGINS contains '*' — disabling credentialed CORS. "
            "Set explicit origins to allow credentials.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "aura-brain", "phase": "1-scaffold"})

    @app.get("/voice/realtime-cost")
    async def realtime_cost() -> JSONResponse:
        """U129: running Realtime spend estimate (this brain session)."""
        import os as _os

        from aura_brain.realtime_voice import METER
        return JSONResponse({
            "engine": _os.environ.get("VOICE_ENGINE", "pipeline"),
            "model": _os.environ.get("REALTIME_MODEL", "gpt-4o-mini-realtime-preview"),
            **METER.summary(),
        })

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await ctx.broadcaster.connect(websocket)
        try:
            await websocket.receive_text()
        finally:
            ctx.broadcaster.disconnect(websocket)

    # --- step 2 mounts (see module docstring for order) ---
    from memory_service import routes as memory_routes
    app.include_router(memory_routes.router)  # U1

    from identity_service.main import router as identity_router
    app.include_router(identity_router)  # U2

    from connector_service import routes as connector_routes
    app.include_router(connector_routes.router)  # U3

    from conversation_runtime import routes as conversation_routes
    app.include_router(conversation_routes.router)  # U4

    from orchestrator import routes as orchestrator_routes
    app.include_router(orchestrator_routes.router)  # U5

    from aura_brain import knowledge_api
    app.include_router(knowledge_api.router)  # U19d

    from aura_brain import recognition_api
    app.include_router(recognition_api.router)  # U18

    from aura_brain import robot_api
    app.include_router(robot_api.router)  # U36: console → robot proxy

    from aura_brain import setup_api
    app.include_router(setup_api.router)  # U34: in-app secure/setup

    from aura_brain import voice_api
    app.include_router(voice_api.router)  # U36e: console mic → voice turn

    from aura_brain import capabilities_api
    app.include_router(capabilities_api.router)  # U40: permissions center

    from aura_brain import logs_api
    logs_api.install()  # ring buffer on the root logger — no files, no telemetry
    app.include_router(logs_api.router)  # U56: in-app log viewer

    # U59: owner-taught skills — CRUD API; the store is shared with the
    # pipeline in the lifespan (pipeline doesn't exist yet at mount time).
    from aura_brain import skills_api
    from orchestrator.skills import SkillStore

    skills_api.init(SkillStore())
    app.include_router(skills_api.router)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "aura_brain.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("RELOAD", "false").lower() == "true",
    )
