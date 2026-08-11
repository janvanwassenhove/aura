# Natural voice conversation

Moved out of the README, where it had grown into an implementation note in the
middle of a front page.

## The state machine

The conversation layer is a real state machine
(`apps/aura-brain/src/aura_brain/conversation_manager.py`):

```
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING
                        ↑                        │
                        └──── INTERRUPTED ←──────┘
```

INTERRUPTED is a first-class state, not an error path. If interruption is an
exception you catch, you get an assistant that stops badly; if it is a state you
pass through, you get one that can be cut off mid-word and pick up coherently.

Every transition is logged with the turn id and the three things you need to
reconstruct what happened: `tts_playing`, `llm_active` and `cancel_requested`.
Never the audio itself, and never secrets.

## Barge-in

Works end to end. While the robot speaks, the microphone keeps listening; an
interruption stops the robot's audio instantly (`POST /robot/audio/stop` →
playbin cut), cancels the in-flight LLM call and the speak task, and the
interrupting utterance becomes the new active turn — with one-shot context
telling the model its previous answer was cut off.

**Known limitation:** full-duplex acoustic echo cancellation while the robot is
speaking is still unstable in a live room. Barge-in works; AEC misfires.

## Characters

`personas/*.json`, seeded on first run: `friendly_assistant`, `dry_tech_butler`,
`kids_companion`, `workshop_coach`, `quiet_mode`.

A character sets the system prompt, verbosity and humour, voice + speed, motion
energy and interruptibility (`wake_word` | `vad` | `off`). Select it in Settings
(`ACTIVE_CHARACTER`); list them via `GET /setup/characters`.

## Settings that matter

| Setting | What it does |
|---|---|
| `VOICE_MODE` | `off` or `wake_word` |
| `WAKE_WORD` | The name it listens for |
| `ACTIVE_CHARACTER` | Persona, voice and motion energy |
| `BARGE_IN_FACTOR` | Interrupt sensitivity |
| `SESSION_MEMORY` | Whether a session carries context |
| `SPEAK_STREAMING` | Off gives the smoothest playback |

## Why the wake word is not enough on its own

A transcript that consists only of the wake word never reaches the model, and
neither does one that is mostly a repeat of the assistant's own previous answer.
Both guards exist because the robot found two ways to talk to itself: the
priming word surviving alone through the echo guard, and the transcriber handing
back the priming *instruction* as though someone had said it.

See `docs/conversation_diagnosis.md` for the full flow map.
