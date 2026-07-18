"""Hands-free voice loop (U47): wake-word start + follow-up conversation.

Runs continuously on the robot's microphone. Behaviour is driven by env so the
Settings panel can change it live:

  VOICE_MODE = off | wake_word      (off → the loop idles; use the mic button)
  WAKE_WORD  = the word that starts a conversation (default: the assistant name)

Flow:
  1. Capture a short window from the robot mic. If it's near-silence (raw peak
     below a threshold) skip it — no transcription cost.
  2. Otherwise transcribe. If we're inside a FOLLOW-UP window (just after the
     robot spoke) the speech is taken as a reply — no wake word needed, so you
     can just answer. Outside that window the wake word must appear; the command
     is whatever follows it (or the next utterance if the wake word was alone).
  3. Run the pipeline turn; the reply is spoken on the robot (embodiment). Each
     spoken reply — including a recognition greeting — opens a fresh follow-up
     window, so a greeting naturally turns into a conversation.

Echo guard: while the robot is speaking its own reply, the loop waits (estimated
from the reply length) so it doesn't transcribe its own voice.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Whisper hallucinates set phrases from silence/noise. Reject these outright.
_HALLUCINATIONS = {
    "you", "thank you", "thank you.", "thanks", "thanks for watching",
    "thanks for watching!", "bye", "bye.", "okay", "ok", ".", "..", "...",
    "sous-titres réalisés par la communauté d'amara.org", "amara.org",
    "untertitel", "untertitelung", "字幕", "字幕by", "so", "yeah", "the",
    "merci", "merci d'avoir regardé", "bedankt voor het kijken",
}

# Accented Latin letters we still treat as "Latin" for the script check.
_LATIN_EXTRA = set("àâäáãéèêëíìîïóòôöõúùûüçñ’'-")


def _within_edits(a: str, b: str, maxd: int) -> bool:
    """True when levenshtein(a, b) <= maxd. Tiny DP, no dependency."""
    la, lb = len(a), len(b)
    if abs(la - lb) > maxd:
        return False
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            best = min(best, cur[j])
        if best > maxd:
            return False
        prev = cur
    return prev[lb] <= maxd


def wake_word_index(text: str, wake: str) -> int:
    """U85: fuzzy wake-word position in ``text`` (-1 if absent).

    Whisper spells names creatively — "Richie" arrives as "Ritchie", "Richy",
    "richie," etc. Match per token, punctuation-stripped, allowing edit
    distance 1 for words of 4+ chars.
    """
    if not wake:
        return -1
    lower = text.lower()
    exact = lower.find(wake)
    if exact >= 0:
        return exact
    pos = 0
    for raw in lower.split():
        token = raw.strip(".,!?;:'\"()-")
        # Longer names tolerate 2 edits ("Richy"/"Ritchie" → "richie"); short
        # ones only 1, so we don't over-match common words.
        maxd = 2 if len(wake) >= 5 else 1
        prefix = wake[:4]
        shared_prefix = len(wake) >= 4 and token.startswith(prefix)
        if len(wake) >= 4 and len(token) >= 3 and (
            _within_edits(token, wake, maxd) or shared_prefix
        ):
            return lower.find(raw, pos)
        pos = lower.find(raw, pos) + len(raw)
    return -1


def is_plausible_command(text: str) -> bool:
    """Guard against Whisper hallucinations on ambient noise/silence.

    Rejects empty/very short strings, known hallucination phrases, and — for
    Latin-script languages — transcripts that are mostly non-Latin (e.g. the
    stray Cyrillic 'Бурын' hallucinated from room noise).
    """
    t = (text or "").strip()
    if len(t) < 3:
        return False
    if t.lower() in _HALLUCINATIONS:
        return False
    lang = os.environ.get("ASSISTANT_LANGUAGE", "auto").lower()
    if lang in ("auto", "en", "nl", "fr"):
        letters = [c for c in t if c.isalpha()]
        if letters:
            latin = sum(1 for c in letters if c.isascii() or c.lower() in _LATIN_EXTRA)
            if latin / len(letters) < 0.6:
                return False
    return True


class VoiceLoop:
    def __init__(
        self,
        robot: Any,          # RobotClient (needs .listen() -> (wav, peak))
        pipeline: Any,       # OrchestratorPipeline
        bus: Any,
        session_id: str = "default",
        default_wake_word: str = "aura",
        window_s: float = 4.0,
        followup_s: float = 9.0,
        speech_peak: float = 0.03,
        manager=None,  # ConversationManager | None (U84)
    ) -> None:
        self._manager = manager
        self._robot = robot
        self._pipeline = pipeline
        self._bus = bus
        self._session_id = session_id
        self._default_wake = default_wake_word
        self._window_s_default = window_s
        self._followup_s_default = followup_s
        self._speech_peak_default = float(speech_peak)
        self._task: asyncio.Task | None = None
        self._followup_until = 0.0
        self._speaking_until = 0.0
        # U54: barge-in — while the robot talks, a clearly louder voice (the
        # user is closer to the mic than the robot's own speaker echo) cuts the
        # wait and is handled as a reply immediately.
        self._barge_factor = float(os.environ.get("BARGE_IN_FACTOR", "3.0"))
        # U67: follow-up windows may CHAIN at most this many turns without the
        # wake word. Music/TV near the mic otherwise becomes a self-sustaining
        # conversation: lyrics enter a follow-up window, the reply opens the
        # next window, and so on forever (the 'Nordmeer' incident).
        self._max_followup_chain = int(os.environ.get("FOLLOWUP_CHAIN_MAX", "2"))
        self._followup_chain = 0
        # U69: while AURA itself just started music, the mic hears lyrics —
        # suspend follow-up windows entirely; only the wake word counts.
        self._music_guard_s = float(os.environ.get("MUSIC_GUARD_S", "180"))
        self._music_until = 0.0
        # U128: local wake-word — detect "Richie" on-device instead of
        # transcribing every window over the network. None → keep the existing
        # transcribe-then-fuzzy path (graceful fallback).
        try:
            from aura_brain.wakeword import build_detector
            self._wake_detector = build_detector()
        except Exception as exc:  # noqa: BLE001 — never block startup on this
            logger.debug("wake detector unavailable: %s", exc)
            self._wake_detector = None

    def note_music_started(self) -> None:
        """Called when a music tool ran: lyrics are about to hit the mic.
        Follow-up windows are suspended for MUSIC_GUARD_S; wake-word commands
        keep working (lyrics rarely contain the robot's name)."""
        self._music_until = time.monotonic() + self._music_guard_s
        self._followup_until = 0.0
        logger.info("music guard active for %.0fs — wake word required", self._music_guard_s)

    @property
    def _barge_in(self) -> bool:
        return os.environ.get("BARGE_IN", "true").lower() == "true"

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())
            logger.info("VoiceLoop started (wake word default=%r)", self._default_wake)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    _last_reply: str = ""

    @property
    def _followup_s(self) -> float:
        # U92: env override if set (live-tunable), else the constructor value.
        # Production creates the loop with followup_s=0 → wake word required
        # every turn (reliable); tests pass an explicit value.
        raw = os.environ.get("FOLLOWUP_S")
        if raw is None:
            return self._followup_s_default
        try:
            return float(raw)
        except ValueError:
            return self._followup_s_default

    @property
    def _followup_peak_factor(self) -> float:
        # U91: follow-up utterances must be this much louder than the silence
        # gate (deliberate speech), so ambient noise can't become a command.
        try:
            return float(os.environ.get("FOLLOWUP_PEAK_FACTOR", "1.6"))
        except ValueError:
            return 1.6

    def _strip_wake_word(self, command: str) -> str:
        """U96: remove a leading/whole wake word from the command so a bare or
        echoed 'Richie' collapses to empty (→ ignored, not a turn)."""
        idx = wake_word_index(command, self._wake)
        if idx < 0:
            return command
        rest = command[idx:]
        parts = rest.split(None, 1)
        return (parts[1] if len(parts) > 1 else "").strip(" ,.!?-").strip()

    def _is_echo_of_last_reply(self, text: str) -> bool:
        """True when the transcript is largely the robot's own last reply
        bouncing back through the mic (word-overlap heuristic)."""
        if not self._last_reply or len(text) < 8:
            return False
        a = {w for w in text.lower().split() if len(w) > 3}
        b = {w for w in self._last_reply.lower().split() if len(w) > 3}
        if not a:
            return False
        return len(a & b) / len(a) >= 0.6

    def note_spoken(self, text: str) -> None:
        self._last_reply = (text or "")[:200]
        """Called when the robot speaks: guard against echo + open a follow-up
        window so the user can reply without the wake word. The follow-up
        chain is capped (U67) — after a few wake-word-less turns the wake word
        is required again, so ambient audio can't talk to itself forever."""
        now = time.monotonic()
        speak_s = min(12.0, 1.0 + len(text or "") / 15.0)  # ~15 chars/sec
        self._speaking_until = now + speak_s
        # U92: FOLLOWUP_S=0 (default) → the wake word is required EVERY turn.
        # That stops room noise / Whisper gibberish from being taken as replies
        # in a no-wake-word window (the "phantom conversations"). Set FOLLOWUP_S
        # to e.g. 8 to re-enable natural "just answer" follow-ups.
        followup_s = self._followup_s
        if followup_s <= 0 or now < self._music_until:
            self._followup_until = 0.0  # wake word required
        elif self._followup_chain < self._max_followup_chain:
            self._followup_until = self._speaking_until + followup_s
        else:
            self._followup_until = 0.0  # chain exhausted → wake word required

    # -- config (read live so the Settings toggle applies) -------------

    @property
    def _mode(self) -> str:
        return os.environ.get("VOICE_MODE", "off").lower()

    @property
    def _wake(self) -> str:
        return os.environ.get("WAKE_WORD", self._default_wake).strip().lower()

    @property
    def _window_s(self) -> float:
        # U89: read live so mic window (latency vs cut-off) is tunable.
        try:
            return float(os.environ.get("VOICE_WINDOW_S", self._window_s_default))
        except ValueError:
            return self._window_s_default

    @property
    def _speech_peak(self) -> float:
        # U86: read live so Settings can tune mic sensitivity without a restart.
        try:
            return float(os.environ.get("VOICE_SPEECH_PEAK", self._speech_peak_default))
        except ValueError:
            return self._speech_peak_default

    # -- main loop -----------------------------------------------------

    async def _run(self) -> None:
        from aura_brain import voice

        while True:
            try:
                if self._mode != "wake_word":
                    await asyncio.sleep(1.5)
                    continue

                now = time.monotonic()
                in_barge = False
                if now < self._speaking_until:  # robot is talking
                    if not self._barge_in:
                        await asyncio.sleep(self._speaking_until - now)
                        continue
                    # U54: barge-in — keep listening in short windows; only a
                    # clearly-louder voice counts (filters the robot's own echo).
                    wav, peak = await self._robot.listen(min(2.0, self._window_s))
                    if peak < self._speech_peak * self._barge_factor:
                        continue
                    # U73: the robot's speaker sits next to its own mic — loudness
                    # alone can't separate the user from self-echo. A barge-in
                    # must contain the WAKE WORD ("Richie, stop"); anything else
                    # during our own speech is treated as echo and ignored.
                    # U84: interruptibility per character — wake_word (default:
                    # transcript must contain the wake word; self-echo never
                    # says its own name), vad (loudness + plausibility is
                    # enough), off (never interrupt).
                    mode = "wake_word"
                    if self._manager is not None and self._manager.character is not None:
                        mode = self._manager.character.interruptibility or "wake_word"
                    if mode == "off":
                        continue
                    barge_text = (await voice.transcribe(wav, filename="robot.wav") or "").strip()
                    if mode != "vad" and wake_word_index(barge_text, self._wake) < 0:
                        logger.debug("barge ignored (no wake word): %r", barge_text[:60])
                        continue
                    if mode == "vad" and not is_plausible_command(barge_text):
                        continue  # debounce: echo/noise without real content
                    # THE barge-in: cut TTS + LLM through the state machine.
                    if self._manager is not None:
                        await self._manager.interrupt(self._last_reply)
                    try:
                        await self._robot.stop_audio()
                    except Exception:  # noqa: BLE001 — robot offline
                        pass
                    self._speaking_until = 0.0  # user interrupted → stop waiting
                    self._followup_until = time.monotonic() + self._followup_s
                    in_barge = True
                    text = barge_text
                else:
                    wav, peak = await self._robot.listen(self._window_s)
                    if peak < self._speech_peak:
                        continue  # silence — cheap skip, no STT

                in_followup = in_barge or time.monotonic() < self._followup_until
                # U128: LOCAL wake gate — outside a follow-up window, detect the
                # wake word on-device before spending a network STT call. No
                # detector (or a follow-up window) → keep the old transcribe path.
                wake_confirmed = False
                if not in_followup and self._wake_detector is not None:
                    try:
                        wake_confirmed = await asyncio.to_thread(self._wake_detector.detect, wav)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("wake detect failed, falling back to STT: %s", exc)
                        wake_confirmed = True  # let STT+fuzzy decide instead
                    if not wake_confirmed:
                        continue  # no wake word heard → skip STT entirely
                # U91: a follow-up window accepts speech WITHOUT the wake word,
                # so ambient noise/TV/echo can hallucinate a "command". Require
                # a deliberately-louder utterance there (the user actually
                # replying), so room noise near the gate doesn't slip through.
                if in_followup and not in_barge:
                    if peak < self._speech_peak * self._followup_peak_factor:
                        continue

                if not in_barge:
                    text = (await voice.transcribe(wav, filename="robot.wav") or "").strip()
                if not is_plausible_command(text):
                    if text:
                        logger.debug("voice loop ignored implausible transcript: %r", text)
                    continue
                # U91: reject a transcript that is (fuzzily) the robot's OWN
                # last reply echoing back through the mic in a follow-up window.
                if in_followup and not in_barge and self._is_echo_of_last_reply(text):
                    logger.debug("voice loop ignored self-echo in follow-up: %r", text[:60])
                    continue

                # U128: a local-confirmed wake means the wake word WAS said even
                # if STT dropped it — treat the transcript as command-bearing
                # (strip a leading wake token if it did transcribe).
                command = self._extract_command(text, in_followup or wake_confirmed)
                if command is None:
                    continue
                # U67: track the wake-word-less chain. Hearing the wake word
                # (transcribed OR locally detected, U128) resets it — a real
                # user re-engaging restores full flow.
                if wake_confirmed or wake_word_index(text, self._wake) >= 0:
                    self._followup_chain = 0
                elif in_followup:
                    self._followup_chain += 1

                # U93: bare wake word ("Richie" with nothing after it) — listen
                # ONE more window for the actual command. If it's silent or
                # gibberish, do NOTHING (no generic "how can I help" reply that
                # made phantom turns). Only start a turn once we have a real
                # command.
                if not command:
                    command = await self._capture_command()
                    if not is_plausible_command(command):
                        continue

                # U96: a command that is ONLY the wake word (Whisper echoes the
                # STT name-prompt as "Richie" on noise/robot-echo) must NEVER be
                # sent to the LLM — that produced the endless "You: Richie" →
                # generic-reply loop. Strip the wake word; if nothing real
                # remains, stay silent.
                command = self._strip_wake_word(command)
                if len(command.strip()) < 2:
                    logger.debug("voice loop ignored bare/echoed wake word")
                    continue

                # NOW this is a real user turn: re-arm cancel tokens and inject
                # the interruption note as OWNER GUIDANCE (a system message,
                # never prepended to the visible command).
                if self._manager is not None:
                    self._manager.begin_turn("voice")
                    self._pipeline.set_cancel_event(self._session_id,
                                                    self._manager.llm_cancel)
                    note = self._manager.consume_interruption_note()
                    if note and hasattr(self._pipeline, "steer"):
                        self._pipeline.steer(self._session_id, note)
                    self._manager.thinking()

                # U129/U133: once we have a REAL turn, run it through Realtime
                # (audio→audio) when that engine is selected; on any failure
                # (or when the engine is 'pipeline') fall back to the classic
                # transcribe→LLM→TTS handler so Richie always replies.
                if not await self._realtime_turn(wav):
                    await self._handle(command)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # the loop must never die
                logger.debug("voice loop tick failed: %s", exc)
                await asyncio.sleep(1.0)

    def _extract_command(self, text: str, in_followup: bool) -> str | None:
        """Return the command text, '' if only the wake word was said, or None
        if this utterance should be ignored."""
        if in_followup:
            return text
        wake = self._wake
        idx = wake_word_index(text, wake)
        if idx >= 0:
            # cut after the (possibly misspelled) wake token
            rest = text[idx:]
            first = rest.split(None, 1)
            return (first[1] if len(first) > 1 else "").lstrip(" ,.!?-").strip()
        return None  # no wake word, not in follow-up → ignore

    async def _capture_command(self) -> str:
        from aura_brain import voice

        wav, peak = await self._robot.listen(self._window_s)
        if peak < self._speech_peak:
            return ""
        return (await voice.transcribe(wav, filename="robot.wav") or "").strip()

    async def _realtime_turn(self, wav: bytes) -> bool:
        """U129: run one spoken turn through the OpenAI Realtime API and play
        the audio reply. Returns True if handled; False (or on ANY error) means
        'not handled' → the caller falls back to the classic pipeline."""
        from aura_brain import realtime_voice

        # U133: circuit breaker — after repeated failures (e.g. no realtime
        # entitlement, wrong model) stop trying so we don't add the timeout
        # latency to every turn; the pipeline handles the whole session.
        if getattr(self, "_realtime_broken", False) or not realtime_voice.realtime_enabled():
            return False
        try:
            pcm = realtime_voice.wav_to_pcm24k(wav)
            if not pcm:
                return False
            character = getattr(self._manager, "character", None) if self._manager else None
            instructions = getattr(character, "character_prompt", "") or ""
            voice_id = getattr(character, "voice_id", "") or "alloy"
            transcript, audio_out = await realtime_voice.run_realtime_turn(
                pcm, instructions=instructions, voice=voice_id)
            if not audio_out:
                return False
            import base64

            from shared_schemas.events.audio import TranscriptUpdated
            await self._bus.publish(TranscriptUpdated(
                session_id=self._session_id, transcript=transcript, is_final=True))
            await self._robot.speak(transcript, audio_b64=base64.b64encode(audio_out).decode())
            self.note_spoken(transcript)
            logger.info("realtime turn done (%d chars, ~$%.4f total)",
                        len(transcript), realtime_voice.METER.spent_usd())
            self._realtime_fails = 0
            return True
        except Exception as exc:  # noqa: BLE001 — realtime is best-effort
            self._realtime_fails = getattr(self, "_realtime_fails", 0) + 1
            if self._realtime_fails >= 2:
                self._realtime_broken = True
                logger.warning(
                    "realtime failed %d× (%s) — disabling Realtime for this "
                    "session; using the pipeline. Switch the engine back to "
                    "Pipeline in Settings, or restart to retry.",
                    self._realtime_fails, exc)
            else:
                logger.warning("realtime turn failed, using pipeline: %s", exc)
            return False

    async def _handle(self, command: str) -> None:
        from shared_schemas.events.audio import TranscriptUpdated

        await self._bus.publish(TranscriptUpdated(
            session_id=self._session_id, transcript=command, is_final=True,
        ))
        logger.info("VoiceLoop heard: %r", command)
        await self._pipeline.orchestrate(command, self._session_id)
        # The reply's ResponseDrafted → note_spoken opens the follow-up window.
