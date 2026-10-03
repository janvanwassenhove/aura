"""U393: whether he should be wandering right now, and what he may say while he does.

Asked for as (translated): *"can we add a 'wandering' mode — the robot wanders
around, following people, moving the antennas, moving towards sound or
people"*, with an option for whether he may make sound. Agreed with three
conditions: a switch next to follow-me; "review that this cannot conflict with
other settings and modes"; and when someone speaks to him while he wanders, he
looks at them but only speaks if his wander sound allows it.

The robot decides HOW to wander (`robot_runtime.wander`) and refuses to while
asleep. This module decides WHETHER, in one place:

- the active mode's behaviour (U397: `wander` and `wander_sound` per mode, set
  in Modes — a Stand wanders and talks, the others stand still until the
  owner says otherwise). It was a switch in Settings until the owner asked,
  translated, why a fair should need a trip to Settings;
- paused while a presentation runs — on stage only the scenario moves and
  speaks (U334). U394 lets a scenario turn it on;
- re-asserted on every change that could matter: the switch, a scenario
  loading or ending, waking up, and the robot coming back — the robot does
  not remember it across its own restart.

His wander sound (the mode's `wander_sound`), three levels:

- `silent` — the default, and what anything unrecognised means, because a
  typo must never be the reason he starts talking. He looks; he makes no sound.
- `emotions` (U395) — sounds instead of words: an emotion from Pollen's
  library (a movement with its own sound — a giggle, a hmm) now and then of
  his own accord, and as his answer when someone speaks to him. The words stay
  in the console.
- `talk` — he answers in words, and makes the odd emotion of his own accord.

Emotions he makes of his own accord stop for Quiet (he never starts, U256) and
on stage (only the scenario makes sound, U334). Answering with one is not
starting, so Quiet leaves that alone — the line U256 drew for words.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SILENT, EMOTIONS, TALK = "silent", "emotions", "talk"
SOUNDS = (SILENT, EMOTIONS, TALK)

_last: dict = {"robot": None, "note": "", "follow_me_overridden": False, "bound": None}

# U395: a reply's mood as an emotion from Pollen's library — short ones, so
# the answer does not outlast the question.
_MOOD_EMOTION = {
    "happy": "cheerful1",          # 2.8 s, a little whistle
    "excited": "enthusiastic2",    # 3.4 s
    "apologetic": "oops1",         # 2.5 s
    "curious": "inquiring2",       # 2.6 s
    "attentive": "thoughtful2",    # 5.5 s, looks up, thinking
    "neutral": "understanding2",   # 2.6 s, a nod and a hmm
}
_LAUGH = ("haha", "hihi", "hehe", "lol", "grappig", "funny", "\U0001f602", "\U0001f923")

# U398: how long each one sounds, measured from the library on the robot, so
# the voice loop can treat his own giggle as his own voice (not as "AURA").
EMOTION_SECONDS = {
    "laughing2": 2.9, "cheerful1": 2.8, "enthusiastic2": 3.4, "oops1": 2.5,
    "inquiring2": 2.6, "thoughtful2": 5.5, "understanding2": 2.6,
    "welcoming1": 3.5, "grateful1": 2.5,
}

# U398: what the chat says he did — the words he did not say stay unsaid.
_GLOSS = {
    "laughing2": "laughs", "cheerful1": "whistles happily", "enthusiastic2": "cheers",
    "oops1": "oops", "inquiring2": "tilts his head", "thoughtful2": "thinks about it",
    "understanding2": "nods — hmm", "welcoming1": "welcomes you", "grateful1": "thanks you",
}

# U398: what a visitor said, by what it is — matched as whole words, because
# "hi" is inside "this" and "dag" inside "vandaag".
_GREETING = ("hallo", "hoi", "hey", "hi", "hello", "goedemorgen", "goedemiddag",
             "goedenavond", "bonjour", "salut", "welkom")
_THANKS = ("dank", "bedankt", "dankjewel", "dankuwel", "merci", "thanks", "thank")
_QUESTION_WORDS = ("wie", "wat", "waar", "waarom", "hoe", "wanneer", "welke", "kan", "kun",
                   "ben", "who", "what", "where", "why", "how", "when", "which", "can",
                   "could", "are", "do", "does")


def _behaviour() -> dict:
    """The active mode's behaviour row (U397). Unreadable is "not wandering"
    — a broken policy is never the reason he starts moving or talking."""
    try:
        from orchestrator import mode_policy  # noqa: PLC0415

        return mode_policy.behaviour(mode_policy.active())
    except Exception:  # noqa: BLE001
        return {}


def wanted() -> bool:
    """What the owner set for the mode he is in."""
    return str(_behaviour().get("wander", "off")).strip().lower() == "on"


def _stage() -> dict | None:
    """U394: what the running talk asks of his body, or None when no talk runs.
    Each value is None where the scenario does not say."""
    try:
        from aura_brain import presentation_api  # noqa: PLC0415

        if presentation_api.is_active():
            return presentation_api.stage_robot()
    except Exception:  # noqa: BLE001 — a missing presentation module pauses nothing
        pass
    return None


def paused_reason() -> str | None:
    """Why it is not in force although the owner wants it, or None."""
    stage = _stage()
    if stage is not None and stage.get("wander") is not True:
        return "presentation"
    return None


def effective() -> bool:
    """Whether he should be wandering right now.

    During a talk the scenario decides — it is the owner's own script for
    that talk, so `wander: on` there makes him wander even with the switch
    off, and a scenario that says nothing pauses it (U334). Otherwise, the
    switch.
    """
    stage = _stage()
    if stage is not None:
        return stage.get("wander") is True
    return wanted()


def owner_follow_me() -> bool:
    return os.environ.get("HEAD_TRACKING", "true").strip().lower() == "true"


def sound() -> str:
    value = str(_behaviour().get("wander_sound", SILENT)).strip().lower()
    return value if value in SOUNDS else SILENT


def silences_speech() -> bool:
    """While wandering silently, replies are not spoken: someone who speaks to
    him gets looked at (the robot turns to the voice), and the answer shows in
    the console as text. U395: with emotions, the answer is an emotion."""
    return effective() and sound() in (SILENT, EMOTIONS)


def _quiet() -> bool:
    """Quiet (U256). Unreadable is not quiet — the U332 rule, from hush."""
    try:
        from orchestrator import mode_policy  # noqa: PLC0415

        return bool(mode_policy.quiet())
    except Exception:  # noqa: BLE001
        return False


def spontaneous_emotions() -> bool:
    """U395: whether he may make an emotion of his own accord while he wanders."""
    if _stage() is not None:
        return False
    return effective() and sound() in (EMOTIONS, TALK) and not _quiet()


def emotion_for_heard(heard: str) -> str:
    """U398: the emotion that answers what a visitor SAID — a greeting, thanks,
    laughter, a question — without composing a reply nobody will hear."""
    import re  # noqa: PLC0415

    t = (heard or "").lower()
    words = re.findall(r"[a-zà-ÿ']+", t)
    if any(cue in t for cue in _LAUGH):
        return "laughing2"
    if any(w in _GREETING for w in words):
        return "welcoming1"
    if any(w in _THANKS or w.startswith("dank") for w in words):
        return "grateful1"
    if t.rstrip().endswith("?") or (words and words[0] in _QUESTION_WORDS):
        return "thoughtful2"
    from aura_brain.mood import detect_mood  # noqa: PLC0415

    mood = detect_mood(heard)
    if mood in ("excited",):
        return "enthusiastic2"
    if mood == "happy":
        return "cheerful1"
    return "understanding2"


def emotion_seconds(name: str) -> float:
    return EMOTION_SECONDS.get(name, 4.0)


def describe(name: str) -> str:
    """What the chat shows in place of an answer."""
    return f"*{_GLOSS.get(name, 'reacts')}* ({name})"


def answers_with_emotion() -> bool:
    """U398: whether a heard question gets an emotion instead of an answer."""
    return effective() and sound() == EMOTIONS and _stage() is None


async def react_to_heard(robot, heard: str) -> str | None:
    """Answer what a visitor said with an emotion. Never raises."""
    if robot is None or not answers_with_emotion():
        return None
    return await _play(robot, emotion_for_heard(heard))


def emotion_for(text: str) -> str:
    """The emotion that answers a reply: laughter first, then its mood."""
    t = (text or "").lower()
    if any(cue in t for cue in _LAUGH):
        return "laughing2"
    from aura_brain.mood import detect_mood  # noqa: PLC0415

    return _MOOD_EMOTION.get(detect_mood(text), "understanding2")


async def react(robot: Any, text: str) -> str | None:
    """In emotions mode, answer with an emotion instead of the words.

    Returns the emotion played, or None when this is not the moment — not
    wandering, another sound level, a talk on stage, or the robot could not.
    Never raises.
    """
    if robot is None or _stage() is not None or not effective() or sound() != EMOTIONS:
        return None
    return await _play(robot, emotion_for(text))


async def _play(robot, name: str) -> str | None:
    """Play one emotion; the name when it played, None when the robot could
    not. Never raises."""
    try:
        import httpx  # noqa: PLC0415

        try:
            await robot.play_emotion(name)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in (404, 501):
                _last["note"] = "the robot needs an update for emotion sounds"
                logger.info("wander: %s", _last["note"])
            return None
        except (httpx.HTTPError, OSError) as exc:
            logger.debug("emotion %s not played: %s", name, exc)
            return None
    except Exception as exc:  # noqa: BLE001 — never break the reply path
        logger.debug("emotion %s not played: %s", name, exc)
        return None
    return name


async def apply(robot: Any) -> dict:
    """Tell the robot what is in force. Never raises: a robot that is away or
    too old to wander is a state to report, not an error."""
    if robot is None:
        return status()
    want = effective()
    emote = spontaneous_emotions()
    try:
        import httpx  # noqa: PLC0415

        try:
            _last["robot"] = await robot.set_wander(want, emotions=emote)
            _last["note"] = ""
            if (want and emote and isinstance(_last["robot"], dict)
                    and "emotions" not in _last["robot"]):
                # The Pi is older than the app: it wanders, without them.
                _last["note"] = "the robot needs an update for emotion sounds"
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            _last["robot"] = None
            _last["note"] = ("the robot needs an update to wander"
                             if code in (404, 501) else f"the robot refused it (HTTP {code})")
        except (httpx.HTTPError, OSError) as exc:
            _last["robot"] = None
            _last["note"] = "could not reach the robot to tell it"
            logger.debug("wander apply failed: %s", exc)
    except Exception as exc:  # noqa: BLE001 — never break the caller
        _last["note"] = f"could not apply: {exc}"
    if _last["note"]:
        logger.info("wander: %s", _last["note"])
    await _apply_follow_me(robot)
    return status()


async def _apply_follow_me(robot: Any) -> None:
    """U394: a scenario may set follow-me for the talk; when the talk ends —
    or the scenario stops saying — the owner's own setting comes back."""
    stage = _stage()
    want = stage.get("follow_me") if stage is not None else None
    try:
        if want is not None:
            await robot.set_tracking(want)
            _last["follow_me_overridden"] = True
        elif _last["follow_me_overridden"]:
            await robot.set_tracking(owner_follow_me())
            _last["follow_me_overridden"] = False
    except Exception as exc:  # noqa: BLE001 — the same "never raises" as above
        logger.debug("follow-me apply failed: %s", exc)


def status() -> dict:
    return {
        "wanted": wanted(),
        "effective": effective(),
        "paused": paused_reason() if wanted() else None,
        "sound": sound(),
        "emotions": spontaneous_emotions(),
        "robot": _last["robot"],
        "note": _last["note"],
    }


def bind(robot: Any) -> None:
    """The robot that `reapply` tells — set once, at startup."""
    _last["bound"] = robot


async def reapply() -> dict:
    """Tell the bound robot again: something it depends on changed."""
    return await apply(_last["bound"])


def mode_changed(_mode: str) -> None:
    """A `mode_policy` listener (U397): switching to a Stand, or changing a
    mode's wandering in Modes, has to reach the robot now — one click in the
    header, not a wake-up later."""
    _tell_soon()


def quiet_changed(_on: bool) -> None:
    """A `mode_policy` listener. Spontaneous emotions live on the robot and
    Quiet lives here; a switch the robot never hears about would change the
    header and nothing else (U366's lesson)."""
    _tell_soon()


def _tell_soon() -> None:
    import asyncio  # noqa: PLC0415

    try:
        asyncio.get_running_loop().create_task(reapply())
    except RuntimeError:
        pass                              # no loop running: nobody to tell


def forget() -> None:
    """Tests: drop what the last apply learned."""
    _last["robot"], _last["note"] = None, ""
    _last["follow_me_overridden"] = False
    _last["bound"] = None
