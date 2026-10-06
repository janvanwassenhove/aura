"""U84: character personas — JSON-driven voice & character, on top of modes.

The existing mode system (work/home/presentation/…) keeps governing TOOLSETS
and gesture profiles. A *character* governs how the assistant sounds and
behaves as a personality: prompt, verbosity, humor, voice, speed, motion
style, interruptibility, greeting.

Characters live in ``CHARACTERS_DIR`` (default ``./personas``) as JSON files;
five ship built-in (created on first load if the dir is empty). The active
character is selected via ``ACTIVE_CHARACTER`` (Settings → prefs) and applied:

  - system prompt  ← character_prompt + speaking_style + verbosity rules
  - voice          ← voice_id / voice_speed (overrides the global TTS voice)
  - motions        ← robot_motion_style scales gesture amplitude
  - barge-in       ← interruptibility ("wake_word" | "vad" | "off")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_MOTION_SCALE = {"calm": 0.5, "normal": 1.0, "lively": 1.3, "still": 0.0}


@dataclass
class CharacterPersona:
    id: str
    display_name: str = ""
    description: str = ""
    language: str = "auto"
    character_prompt: str = ""
    speaking_style: str = ""
    humor_level: str = "medium"          # none | low | medium | high
    verbosity: str = "brief"             # brief | normal | detailed
    interruptibility: str = "wake_word"  # wake_word | vad | off
    # U203: which voice engine this character talks through. Empty → inherit the
    # global VOICE_ENGINE (pipeline by default). "pipeline" keeps skills, memory
    # and tools; "realtime" is fluid speech-to-speech but has NO tool access, so
    # it fits a chat-along presentation persona, not the everyday assistant.
    voice_engine: str = ""               # "" (inherit) | pipeline | realtime | live
    emotional_style: str = "warm"
    voice_provider: str = "openai"
    voice_id: str = ""                   # empty → global TTS voice
    voice_speed: float = 1.0
    voice_pitch: float = 1.0             # documented; OpenAI TTS has no pitch knob
    robot_motion_style: str = "normal"   # calm | normal | lively | still
    greeting_message: str = ""
    fallback_message: str = "Sorry, that didn't work — want me to try again?"
    # U85: the character GROWS — owner-approved trait notes accumulate here
    # (edited in the Robot panel; the agent suggests additions in teach-mode).
    learned_traits: str = ""
    # U404: how he looks on screen when this persona speaks — one of the
    # console's drawn archetypes (LOOKS). Empty: the character chosen in the
    # console's header, as before.
    look: str = ""
    # U409: how this character delivers a talk's lines — sent to the TTS model
    # as its instructions when a beat names no direction of its own.
    voice_direction: str = ""

    def motion_scale(self) -> float:
        return _MOTION_SCALE.get(self.robot_motion_style, 1.0)

    def system_note(self) -> str:
        verbosity_rule = {
            "brief": "Answer in 1-2 short spoken sentences unless the user asks for detail.",
            "normal": "Keep answers conversational and to the point.",
            "detailed": "You may elaborate, but stay structured.",
        }.get(self.verbosity, "")
        humor_rule = {
            "none": "No jokes.", "low": "At most a light touch of wit.",
            "medium": "Occasional humor is welcome.",
            "high": "Be playful and funny when it fits.",
        }.get(self.humor_level, "")
        parts = [f"CHARACTER — {self.display_name or self.id}: {self.character_prompt}"]
        if self.speaking_style:
            parts.append(f"Speaking style: {self.speaking_style}.")
        parts.append(f"{verbosity_rule} {humor_rule}")
        if self.emotional_style:
            parts.append(f"Emotional tone: {self.emotional_style}.")
        if self.learned_traits:
            parts.append(f"Traits you have developed over time: {self.learned_traits}")
        return " ".join(p for p in parts if p.strip())


# U404: the console's ten drawn archetypes (operator-console lib/characters.ts).
LOOKS = ("scout", "sentinel", "slab", "mender", "astro", "grump", "halo",
         "buddy", "host", "orb")

# U404: the look each built-in persona comes with — matched on the traits the
# console gives each archetype. Also filled in on reading a persona file
# seeded before looks existed: the owner's copies are never rewritten.
_BUILTIN_LOOKS = {
    "friendly_assistant": "scout",    # warm voice, chatty, bouncy
    "dry_tech_butler": "slab",        # low voice, dry humour, deliberate
    "kids_companion": "buddy",        # bright voice, simple words, bouncy
    "workshop_coach": "host",         # projected voice, theatrical, broad
    "quiet_mode": "orb",              # clear voice, sparse words, gliding
}

# U409: the way each built-in persona speaks. Filled in on reading a persona
# file written before directions existed, as U404 does for looks.
_BUILTIN_DIRECTIONS = {
    "friendly_assistant": "warm, natural, upbeat",
    "dry_tech_butler": "dry, unhurried, understated",
    "kids_companion": "warm, soft, playful",
    "workshop_coach": "confident, clear, energetic",
    "quiet_mode": "calm, quiet, plain",
}

#: U409: the same limit a scenario's direction has.
VOICE_DIRECTION_MAX = 300

_BUILTINS: list[dict] = [
    dict(id="friendly_assistant", display_name="Friendly Assistant",
         description="Warm, helpful default companion.",
         character_prompt="You are a warm, encouraging desk companion who helps with anything.",
         speaking_style="natural, upbeat, everyday language", humor_level="medium",
         verbosity="brief", interruptibility="wake_word", emotional_style="warm",
         voice_id="coral", voice_speed=1.0, robot_motion_style="normal",
         greeting_message="Hey! Goed je te zien — waar kan ik mee helpen?"),
    dict(id="dry_tech_butler", display_name="Dry Tech Butler",
         description="Impeccably competent, drily witty.",
         character_prompt="You are a precise, understated butler with deep technical knowledge. Never gush.",
         speaking_style="measured, formal but wry, short sentences", humor_level="low",
         verbosity="brief", interruptibility="wake_word", emotional_style="composed",
         voice_id="ash", voice_speed=0.95, robot_motion_style="calm",
         greeting_message="Goedendag. U wenst?"),
    dict(id="kids_companion", display_name="Kids Companion",
         description="Playful, safe, simple language for children.",
         character_prompt="You talk to children: simple words, short sentences, always kind, never scary. "
                          "Never discuss adult topics.",
         speaking_style="playful, simple, enthusiastic", humor_level="high",
         verbosity="brief", interruptibility="vad", emotional_style="cheerful",
         voice_id="nova", voice_speed=1.05, robot_motion_style="lively",
         greeting_message="Hoi hoi! Zullen we iets leuks doen?"),
    dict(id="workshop_coach", display_name="Workshop Coach",
         description="Energetic facilitator for demos and workshops.",
         character_prompt="You are an energetic workshop coach: activate people, give clear next steps, keep momentum.",
         speaking_style="energetic, direct, action-oriented", humor_level="medium",
         verbosity="normal", interruptibility="wake_word", emotional_style="energizing",
         # U203: a presentation persona is meant to chat along fluidly, and gives
         # up tools willingly for it — the natural home for the realtime engine.
         voice_engine="realtime",
         voice_id="verse", voice_speed=1.05, robot_motion_style="lively",
         greeting_message="Oké team, we gaan ervoor. Eerste vraag?"),
    dict(id="quiet_mode", display_name="Quiet Mode",
         description="Minimal speech, minimal motion.",
         character_prompt="Answer as briefly as possible. One sentence. No small talk.",
         speaking_style="minimal, soft", humor_level="none",
         verbosity="brief", interruptibility="off", emotional_style="neutral",
         voice_id="sage", voice_speed=0.95, robot_motion_style="still",
         greeting_message=""),
]


class CharacterStore:
    def __init__(self, directory: str | None = None) -> None:
        self._dir = Path(directory or os.environ.get("CHARACTERS_DIR", "./personas"))

    def _seed(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        for b in _BUILTINS:
            path = self._dir / f"{b['id']}.json"
            if not path.exists():
                seeded = CharacterPersona(**b)
                seeded.look = _BUILTIN_LOOKS.get(seeded.id, "")
                seeded.voice_direction = _BUILTIN_DIRECTIONS.get(seeded.id, "")
                path.write_text(json.dumps(asdict(seeded), indent=2,
                                           ensure_ascii=False), encoding="utf-8")

    def all(self) -> list[CharacterPersona]:
        self._seed()
        out: list[CharacterPersona] = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items()
                         if k in CharacterPersona.__dataclass_fields__}
                if known.get("id"):
                    c = CharacterPersona(**known)
                    if "look" not in data:        # U404: seeded before looks existed
                        c.look = _BUILTIN_LOOKS.get(c.id, "")
                    if "voice_direction" not in data:  # U409: before directions existed
                        c.voice_direction = _BUILTIN_DIRECTIONS.get(c.id, "")
                    out.append(c)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("character %s unreadable: %s", f.name, exc)
        return out

    def get(self, character_id: str) -> CharacterPersona | None:
        for c in self.all():
            if c.id == character_id:
                return c
        return None

    _EDITABLE = {"display_name", "description", "character_prompt",
                 "speaking_style", "humor_level", "verbosity",
                 "interruptibility", "emotional_style", "voice_id",
                 "voice_speed", "robot_motion_style", "greeting_message",
                 "fallback_message", "learned_traits", "language",
                 "voice_engine", "look", "voice_direction"}  # U203, U404, U409

    def update(self, character_id: str, fields: dict) -> CharacterPersona | None:
        """U85: owner edits a character (Robot panel). Unknown fields ignored."""
        current = self.get(character_id)
        if current is None:
            return None
        for k, v in fields.items():
            if k not in self._EDITABLE or v is None:
                continue
            # U203: an invalid engine would silently disable tools on every turn
            # (realtime) or worse. Ignore anything that is not a real choice.
            if k == "voice_engine" and str(v).strip().lower() not in (
                    "", "pipeline", "realtime", "live"):
                continue
            # U404: a look the console cannot draw would leave a blank avatar.
            if k == "look" and str(v).strip().lower() not in ("", *LOOKS):
                continue
            # U409: a note on delivery, not an essay — the scenario's limit.
            if k == "voice_direction" and len(str(v).strip()) > VOICE_DIRECTION_MAX:
                continue
            setattr(current, k, type(getattr(current, k))(v))
        (self._dir / f"{character_id}.json").write_text(
            json.dumps(asdict(current), indent=2, ensure_ascii=False),
            encoding="utf-8")
        return current

    def active(self) -> CharacterPersona | None:
        """The selected character (ACTIVE_CHARACTER env, read live)."""
        cid = os.environ.get("ACTIVE_CHARACTER", "").strip()
        return self.get(cid) if cid else None
