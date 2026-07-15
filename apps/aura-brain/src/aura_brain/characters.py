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
from dataclasses import asdict, dataclass, field
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
    emotional_style: str = "warm"
    voice_provider: str = "openai"
    voice_id: str = ""                   # empty → global TTS voice
    voice_speed: float = 1.0
    voice_pitch: float = 1.0             # documented; OpenAI TTS has no pitch knob
    robot_motion_style: str = "normal"   # calm | normal | lively | still
    greeting_message: str = ""
    fallback_message: str = "Sorry, that didn't work — want me to try again?"

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
        return " ".join(p for p in parts if p.strip())


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
         character_prompt="You talk to children: simple words, short sentences, always kind, never scary. Never discuss adult topics.",
         speaking_style="playful, simple, enthusiastic", humor_level="high",
         verbosity="brief", interruptibility="vad", emotional_style="cheerful",
         voice_id="nova", voice_speed=1.05, robot_motion_style="lively",
         greeting_message="Hoi hoi! Zullen we iets leuks doen?"),
    dict(id="workshop_coach", display_name="Workshop Coach",
         description="Energetic facilitator for demos and workshops.",
         character_prompt="You are an energetic workshop coach: activate people, give clear next steps, keep momentum.",
         speaking_style="energetic, direct, action-oriented", humor_level="medium",
         verbosity="normal", interruptibility="wake_word", emotional_style="energizing",
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
                path.write_text(json.dumps(asdict(CharacterPersona(**b)), indent=2,
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
                    out.append(CharacterPersona(**known))
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("character %s unreadable: %s", f.name, exc)
        return out

    def get(self, character_id: str) -> CharacterPersona | None:
        for c in self.all():
            if c.id == character_id:
                return c
        return None

    def active(self) -> CharacterPersona | None:
        """The selected character (ACTIVE_CHARACTER env, read live)."""
        cid = os.environ.get("ACTIVE_CHARACTER", "").strip()
        return self.get(cid) if cid else None
