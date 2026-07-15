# Conversation flow — diagnosis (U84)

Doel: natuurlijke, lag-arme spraakconversatie met echte barge-in. Dit document
brengt de bestaande flow in kaart vóór de refactor (kleinste veilige ingreep:
alleen de conversatie/audio-laag).

## Huidige flow (gemeten in de code)

```
 mic ──► RobotClient.listen(4s)  POST /robot/listen — VASTE 4s-opname, half-duplex
             │ (HTTP, WAV terug)
             ▼
 VoiceLoop (aura-brain/voice_loop.py)
   • peak-gate (VOICE_SPEECH_PEAK) → stilte overslaan
   • OpenAI Whisper API (volledige window; geen streaming-STT)
   • wake-word / follow-up-venster / music-guard / keten-cap
             ▼
 OrchestratorPipeline.orchestrate()  — agentic loop (U57)
   • openai_chat per ronde, NIET gestreamd naar de spraaklaag
   • geen cancel-token: een gestarte LLM-call loopt altijd af
             ▼
 ResponseDrafted event ──► _embody_reply (main.py)
   • gebaar (embodiment_plan per modus)
   • TTS: volledige zin → b64 → POST /robot/speak
             ▼
 robot-runtime play_audio → GStreamer playbin (U83)
   • speelt end-to-end, BLOKKEERT met motion_lock tot klaar
   • geen stop-endpoint: eenmaal gestart is spraak NIET te onderbreken
```

## Wat werkt

- Wake-word-start, follow-up-vensters, echo-/muziek-guards (U47/U67/U69).
- Volledige, luide zinnen (U80–U83: playbin + ALSA-max).
- Volgen tijdens spreken (U81), persona-stemmen (U65), gebaren per modus (U51).
- Skills/kennis-injectie per persoon.

## Wat kapot/onnatuurlijk is

1. **Barge-in stopt de spraak niet.** De VoiceLoop kan een onderbreking
   *detecteren* (wake-word tijdens spreken, U73) maar er is geen enkel
   mechanisme om de lopende TTS-playback op de robot te stoppen, noch om de
   lopende LLM-generatie te annuleren. De robot praat gewoon uit.
2. **Geen state machine.** Toestand ligt verspreid over VoiceLoop-velden
   (_speaking_until, _followup_until, _music_until), pipeline-flags en
   impliciete timing. Geen turn-id's, geen cancellation-tokens, geen
   INTERRUPTED-status, nauwelijks te loggen/debuggen.
3. **Half-duplex mic met vaste vensters.** listen(4s) betekent tot 4s
   detectievertraging + de opname kan midden in een zin knippen. Tijdens
   TTS wordt alleen in korte barge-vensters geluisterd.
4. **Latency-opbouw**: 4s-window (gem. ~2s wachten) + Whisper-upload (~1s) +
   LLM (1.5–5s, gpt-5.1) + TTS-synthese volledige zin (~1–3s) + HTTP-hop +
   playbin-opstart (~0.5s). First-audio ligt daardoor op ~5–10s.
   Sentence-streaming (U54) bestaat maar staat uit omdat losse playbin-chunks
   hoorbaar hakten (U83).
5. **Interruptie-context ontbreekt.** Na een (gewenste) onderbreking weet de
   LLM niet dat zijn vorige antwoord is afgekapt — hij herpakt onhandig.
6. **Persona's zijn modi**, geen karakters: work/home/presentation sturen
   toolsets/gebaren/stem, maar er is geen JSON-gedreven karakterlaag
   (verbosity, humor, interruptibility, begroeting, …).

## Waarom barge-in niet goed werkt (wortel)

- Robot-side: `play_audio` blokkeert (bewust, U83) en er is **geen
  stop-audio-endpoint**; playbin is wel stopbaar (`playbin.set_state(NULL)`).
- Brain-side: `_embody_reply` is een fire-and-forget subscriber zonder handle;
  niets kán hem annuleren. De agentic loop heeft een stop-ná-ronde
  (request_stop) maar geen echte LLM-call-cancel.
- Loudness alleen kan gebruiker niet van speaker-echo onderscheiden (speaker
  zit naast de mic, U73) → onderbreken vereist het wake-word in het transcript
  (default), met een instelbare VAD-only modus als opt-in.

## Kleinste veilige refactor — welke bestanden

| Laag | Bestand | Wijziging |
|---|---|---|
| state machine | **nieuw** `aura_brain/conversation_manager.py` | states, turn-id's, cancel-tokens, gestructureerde logging, persona |
| robot audio | `robot_runtime/adapters/reachy.py` | `stop_audio()` (abort-flag + playbin→NULL); play-lus abortbaar |
| robot API | `robot_runtime/routes.py` | `POST /robot/audio/stop` |
| brain↔robot | `aura_brain/robot_client.py` | `stop_audio()` |
| spraak | `aura_brain/main.py` (_embody_reply) | speak-task geregistreerd bij de manager → cancelbaar; INTERRUPTED-context naar de volgende beurt |
| mic-lus | `aura_brain/voice_loop.py` | via de manager: barge → `manager.interrupt()`; instelbare gevoeligheid |
| LLM | `orchestrator/pipeline.py` | cancel-event per turn; loop breekt óók midden-ronde af |
| karakter | **nieuw** `personas/*.json` + `aura_brain/characters.py` | JSON-karakterlaag (5 persona's) bovenop de bestaande modi |
| settings | `aura_brain/setup_api.py` | active character, interrupt-sensitivity, session-memory |

Bewust NIET aangeraakt: agentic loop-semantiek, skills, kennis, console-flow,
robot-lifecycle (stop_event/offline-lus) — die werken.
