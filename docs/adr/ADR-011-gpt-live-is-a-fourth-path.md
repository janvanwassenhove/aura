# ADR-011: GPT-Live is a fourth speech path, not a model swap

**Status**: **Accepted — adopt as a fourth path; integration in progress** (2026-09-11).
The owner asked to pursue it ("moet beschikbaar zijn, bekijk hoe we kunnen gaan
gebruiken"); the sections *Why not now* below are therefore what the
integration has to solve, not reasons to wait.
**Date**: 2026-09-11
**Owner**: aura-brain / voice
**Related**: [ADR-005](ADR-005-voice-pipeline.md) (three speech paths),
[ADR-009](ADR-009-honest-state.md) (honest state),
[spec 017](../../.specify/specs/017-voice-and-language/spec.md), U321

---

## Context

Asked as *"voor voice gpt-live1 is now available, use this one for natural
voice"*. The obvious reading is a one-line change: pin `REALTIME_MODEL` to the
new model, the way `gpt-realtime-2` is pinned today.

Everything below was **measured on the owner's own key on 2026-09-11** before
anything was changed, with `gpt-realtime-2` run through the same script as a
control, so a failure could be attributed to the model and not to the test.

| Question | Measured answer |
|---|---|
| What is the exact id? | `gpt-live-1` — with a hyphen. `gpt-live1` does not exist. |
| Does it serve the Realtime API, in any of the three session shapes AURA sends? | **No.** `Model "gpt-live-1" is not supported in realtime mode.` The control passed all three. |
| Chat Completions? | **No.** `This is not a chat model.` |
| Responses? | 500. |
| What does it serve? | Only OpenAI's dedicated **Live API**, `v1/live/sessions` (per OpenAI's model page). |
| Does the installed SDK know it? | **No.** `openai` 2.33.0 has `.realtime`, no `.live`. |

So pinning it would not have given a more natural voice. It would have failed
every realtime turn, and the circuit breaker would have dropped each one to the
pipeline — the voice silently less natural, with nothing on screen saying why.

Worse, the model had **already** appeared in the account's model list, and the
Settings classifier — a substring test for `realtime` or `-audio` — sorted it as
`["chat", "vision"]`. The running app was offering it as a **Conversation
model**, which is exactly the U202 failure: every turn 404s into the echo
fallback. That part is a defect, and U321 fixes it regardless of this decision.

## What GPT-Live actually is

Per OpenAI's documentation on 2026-09-11 (guides *Getting started*, *Migrate
to GPT-Live*, *Delegation and tools*, *Managing sessions*):

* **Full duplex.** It listens and speaks at the same time and decides for
  itself when to talk. There is no manual turn control and no direct access to
  semantic VAD.
* **A different protocol.** `session.input_audio.append`,
  `session.output_audio.delta`, `session.input_transcript.delta`,
  `session.output_transcript.delta`. There is **no event marking the end of a
  response**; the client tracks playback itself.
* **Language and voice are configured in `session.instructions`** — prose, not
  a pinned field.
* **Tools are delegated.** With client delegation the session emits
  `session.delegation.created` (metadata only, not the task text); our
  application runs the work and answers with `session.commentary.append`
  (≤ 500 tokens per append). The docs are explicit that approvals are enforced
  in the application layer.
* **Billed per minute** — $0.05/min, per second, while the session is open;
  backend model usage separately. Whether silence is billed is not documented.
  Sessions end with `session.close`.

## Decision

1. **Do not pin `gpt-live-1` as the voice model.** Measured: it cannot serve
   that role.
2. **Make the platform say so.** The classifier no longer offers `gpt-live-*`
   (or `*-realtime-translate`, which connects and never answers) for any role,
   and the Settings guard refuses them with the reason — using the orchestrator's
   classifier instead of the second, weaker copy that let this through.
3. **Pursue GPT-Live as a fourth speech path** — not by swapping a model
   name, but as its own engine with its own client (from U322).

## Why it is worth coming back to

Every trade-off in ADR-005's three paths comes from one fact: the path that
sounds natural (the realtime session) cannot call tools, and the path that can
call tools (the pipeline) does not sound natural. GPT-Live's **client
delegation** is the first design that could have both — and it keeps the
architecture's hardest rule intact, because the tool still runs in **our**
orchestrator, behind **our** approval gate (constitution IV). That is a real
reason to build it, not a novelty.

## What the integration has to solve

Each of these is a known failure of this project, not a hypothetical — so
each is a requirement on the integration, not a reason to wait:

1. **Full duplex on a robot without echo cancellation.** U156 made full duplex
   opt-in and off by default precisely because, without the robot's WebRTC AEC
   path, the server hears Richie's own voice. The self-hearing loops of U67,
   U92, U148 and U258 all came from that. GPT-Live is full duplex by design.
2. **Language cannot be pinned.** U287 and U289 exist because asking the model
   for Dutch in its instructions did nothing about how the audio was *heard* —
   Dutch came back as German, then Spanish. GPT-Live offers only the
   instruction route. The owner's most recent request on voice was to fix
   language "voor eens en altijd"; this would reopen it.
3. **No end-of-response event.** Barge-in, the echo guard and the seed mute
   (U148, U163) key off response completion today and would need rework.
4. **The SDK does not have it.** A raw WebSocket client, or an SDK upgrade — and
   `openai` is not declared in `aura-brain`'s own `pyproject.toml`, which is the
   `uv sync` pruning trap that has already cost four units.
5. **Per-minute billing** makes the session lifecycle a cost control, not just
   a resource one.

## What would change this decision

* Full duplex verified on the physical robot with its AEC path on, in a real
  room, without self-hearing — the U156 experiment finished.
* A Dutch household conversation, with television on, holding its language
  under instruction-only pinning — tested, not assumed.
* SDK support, declared as a direct dependency.

When those hold, GPT-Live becomes a fourth selectable engine alongside the
three in ADR-005, with the delegation handler calling the orchestrator's
existing agentic loop.

## The companion model: `gpt-live-transcribe`

Asked in the same breath: *"kunnen we gpt-live-transcribe ook gebruiken?
andere doeleinden misschien?"*

Measured on a 6.7 s Dutch sentence, **fed in real time** (200 ms per 200 ms,
like the microphone), n = 3 interleaved, inside a `gpt-realtime-2` session:

| Transcriber | First word, from start of speech | Final, after end of speech |
|---|---|---|
| `gpt-4o-mini-transcribe` (today) | 7.40 s — only once you stop | 1.06 s |
| `gpt-live-transcribe` | 1.27 s | 1.09 s |
| `gpt-live-transcribe`, `delay: minimal` | **0.49 s** — while you are still talking | 1.12 s |
| `gpt-live-transcribe`, `delay: low`, keywords | 0.74 s | 1.28 s |

An earlier measurement that fed the whole clip at once reported it as 2.6 s and
"slower"; that measured the one thing a streaming model is not built for, and
was wrong. Accuracy was equal. Only the live model accepts `keywords`
(`gpt-4o-mini-transcribe` rejects the field).

Where it can and cannot run in AURA:

* **Not the pipeline.** `POST /v1/audio/transcriptions` answers 404 for it.
  Because STT_MODEL is shared by both paths, setting it there would have made
  Richie deaf on the pipeline; U321 makes the pipeline ignore a realtime-only
  transcriber, loudly, once.
* **Inside the realtime session, yes** — opt-in through a new
  `REALTIME_STT_MODEL`.
* **Not the default yet**, because the session publishes only the *completed*
  transcript. The 0.5 s first word would be thrown away; today the only gain
  is keyword hints.

Uses worth building next, in order of value:

1. **Presentation keyword beats.** `keyword:Java` fires when the word is
   *said* (spec 011). Streaming deltas plus the armed keywords as hints would
   fire it half a second into the word instead of after the sentence.
2. **Live captions of what the person said**, by publishing deltas as
   non-final `TranscriptUpdated`.
3. **Keyword hints** for the assistant's name and the household's names — the
   names Whisper kept dropping (U87, U275). Those names already reach OpenAI in
   the turn context (U293); adding them as hints is not a new disclosure, but
   it is a new place they are sent, and should be stated when built.

## Alternatives considered

* **Pin `gpt-live-1` as `REALTIME_MODEL`.** Rejected: measured to fail.
* **Wait for all five problems to solve themselves.** Rejected at the
  owner's request; they become the integration's acceptance criteria instead.
* **Make `gpt-live-transcribe` the session default.** Rejected until the deltas
  are rendered — paying for streaming nobody sees.
