# The scenario format

**This is the authoritative reference for a co-presenter scenario.** Hand it to
whoever — or whatever — writes or regenerates one. The schema it describes is
[`shared_schemas/presentation/models.py`](../../packages/shared-schemas/src/shared_schemas/presentation/models.py);
if the two ever disagree, the model is right and this file is a bug.

Check a file before you need it:

```bash
python scripts/check_scenario.py my-talk.scenario.yaml
```

It prints what the talk will do — how many times he speaks, which keywords are
armed, which slides he appears on — or refuses with the same sentence the
Present panel would show. Exit code 0 or 1, so it fits in CI or a pre-flight
script.

---

## The shape

```yaml
title: "I Hired a Real Robot as My Junior Dev"   # optional
pptx: "AURA-Devoxx-2026-conference-talk.pptx"    # optional, for the wrong-deck warning
overlay: hidden                                   # optional: hidden | shown (default)
wander: on                                        # optional: on | off — does he look around?
follow_me: on                                     # optional: on | off — does he watch you?

beats:
  - id: the-fanfare        # required, unique
    trigger: slide:9       # manual (default) | slide:N | keyword:TEXT
    mode: speak            # speak (default) | improvise | chime_in | silent
    text: "Ta. Ta. Ta."    # speak: what he says, verbatim
    voice: onyx            # optional: a TTS voice for this beat
    speed: 0.85            # optional: 0.25–4.0
    pause: 7.0             # optional: seconds to wait before speaking
    gesture: nod           # optional
    persona: kids_companion  # optional: a character id
    overlay: hide          # optional: show | hide, from this beat onwards
    wander: off            # optional: on | off, from this beat onwards
    follow_me: off         # optional: on | off, from this beat onwards
    once: true             # optional: keyword beats fire once anyway; a slide beat
                           #   replays when you return to its slide unless this says true
```

**An unknown field is refused.** Not ignored — refused, naming itself. This is
deliberate and it is why this document exists: `voice:` and `speed:` once sat in
a shipped scenario through an entire rehearsal doing nothing, because unknown
keys used to be dropped silently, and the two-voice gag they were written for
came out in one voice (U360).

## Every field

### Scenario

| Field | Type | Default | What |
|---|---|---|---|
| `title` | string | `""` | Shown on the presenter HUD. |
| `pptx` | string | `""` | The deck's file name. Only used to warn you that the wrong deck is on screen — he never opens it. |
| `overlay` | `shown` \| `hidden` | `shown` | Where the projector overlay starts. `hidden` is for a talk where he should appear only at the moments you name. |
| `wander` | `on` \| `off` | not said | Whether he looks around where he stands — follows the people he sees, turns towards voices, moves his antennas — when the talk starts. Not said: he does not wander during the talk, whatever the mode says. |
| `follow_me` | `on` \| `off` | not said | Whether he keeps looking at the presenter when the talk starts. Not said: your own *Follow me* setting. |
| `beats` | list | `[]` | In file order. Order matters for `manual` beats. |

### Beat

| Field | Type | Default | What |
|---|---|---|---|
| `id` | string | **required** | Unique within the scenario. Appears in every error message, so make it readable. |
| `trigger` | string | `manual` | `manual`, `slide:N`, or `keyword:TEXT`. |
| `mode` | string | `speak` | `speak`, `improvise`, `chime_in`, `silent`. |
| `text` | string | `""` | **Required for `speak`.** Said verbatim. |
| `topic` | string | `""` | **Required for `improvise` and `chime_in`.** What to talk about. |
| `guardrails` | string | `""` | Extra constraints for the generated line. |
| `gesture` | string \| null | `null` | `wave`, `nod`, `tilt`, `shrug`, … |
| `engine` | `""` \| `pipeline` \| `realtime` | `""` | `pipeline` runs the full agentic loop — **required** if the line needs live data (calendar, a lookup). |
| `once` | bool | by trigger | Leave it out. A `keyword:` beat fires once however often the word is said; a `slide:` beat runs again every time you return to its slide. Write `once: true` on a slide beat only if returning must stay silent. |
| `overlay` | `""` \| `show` \| `hide` | `""` | Move the projector overlay from this beat onwards. Empty leaves it alone. |
| `wander` | `on` \| `off` | not said | From this beat onwards, does he look around. Not said leaves it as it was. |
| `follow_me` | `on` \| `off` | not said | From this beat onwards, does he watch the presenter. Not said leaves it as it was. |
| `persona` | character id | `""` | Which character speaks this beat — its voice, speed, (when improvising) its way of putting things, and its look on the projector while it speaks (U404). |
| `voice` | TTS voice | `""` | A voice for this beat alone. |
| `speed` | float | `0` | `0.25`–`4.0`. `0` means leave it alone. |
| `pause` | float | `0` | Seconds to wait **before** speaking. |

**Voices**: `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `onyx`, `nova`,
`sage`, `shimmer`, `verse`. A name outside this list is refused, by name.

## Triggers

- **`manual`** — fires when you press *Advance beat* in AURA. **Not** your
  slide clicker. Manual beats fire in the order they appear in the file.
- **`slide:N`** — fires when PowerPoint reaches slide N, using PowerPoint's own
  1-based numbering. Slide watching is Windows/macOS only; put anything that
  absolutely must not misfire on `manual`.
- **`keyword:TEXT`** — fires when *you* say TEXT while presenting.
  Case-insensitive substring match. Only `chime_in` may use this.

## Modes

| Mode | Needs | Does |
|---|---|---|
| `speak` | `text` | Says it verbatim. |
| `improvise` | `topic` | Generates one short line and says it. |
| `chime_in` | `topic` + a `keyword:` trigger | An armed improvise. |
| `silent` | — | Says nothing. Still fires, still moves the HUD, and can still move the overlay — which is the most useful thing a silent beat does. |

## Two voices in one line

`persona` sets a character for the whole beat. Inside `text`, hand the line over
mid-sentence:

```yaml
text: "Misschien. [persona:kids_companion]Of iets veel leukers![persona] De rest typ ik wel."
```

`[persona]` (or `[/persona]`) hands it back. The markers are never spoken, and a
malformed one is refused rather than read out loud. The pieces are synthesized
separately and joined into **one** utterance, so the change of character is not
also a change of volume.

**`voice` on the beat wins over all of it** — including the inline markers. A
line cannot be both "all in onyx" and "this bit in somebody else's voice".

## The things that bite

- **An unknown field stops the load.** Including a misspelt one: `voise: onyx`
  is refused, it does not fall through.
- **`chime_in` must use a `keyword:` trigger.** Nothing else can arm it.
- **A beat that needs live data must set `engine: pipeline`.** The realtime
  engine has no tool access.
- **`pause` is skipped in a rehearsal.** Walking the show is for reading the
  lines, not for waiting out a video.
- **The scenario decides *when* the overlay is visible, never *whether*.** You
  still switch it on in the Present panel; `overlay: show` does nothing if no
  overlay is up.
- **A slide is a place, not a moment.** Every time you arrive at a slide —
  forwards, backwards, or by jumping — its beats run again, unless a beat says
  `once: true`. The same slide reported twice in a row is not an arrival.
- **The overlay follows the slide you are on.** On any slide it is where the
  last `overlay:` beat at or before that slide put it, so jumping into the
  middle of a full-frame run leaves him off the screen even though that slide
  has no beat of its own. A keyword or manual beat can move it too; the next
  slide change decides again.
- **`wander` and `follow_me` follow the slide, like the overlay.** On any
  slide he is where the last beat at or before it put him, so going back or
  jumping puts him right. A keyword or manual beat can move them too; the next
  slide change decides again.
- **During a talk the scenario decides; afterwards, your settings.** `wander:
  on` makes him wander whatever the mode says — the scenario is your script
  for that talk. A scenario that says nothing about wandering keeps him still
  on stage. *End presentation* gives your own Follow me and the mode's
  wandering back.
- **Both on.** Wandering keeps the face tracker on, so while `wander` is on he
  follows whoever he sees whatever `follow_me` says: with someone in view only
  his antennas move; with nobody, he looks around and turns to voices. So
  `follow_me` matters once `wander` is off, and standing still needs both off.
  The tracker cannot tell the presenter from the audience — that is why the
  keynote stops wandering at slide 2, where follow-me alone keeps him on the
  face nearest to him: yours.
- **He moves as he speaks.** Every line — from his own speaker or the
  laptop's — keeps his antennas going and his head nodding with the words,
  laid over wherever he is looking, with his character's speaking gestures
  spread over the line; nothing in the scenario turns it on (U407, U408). A
  `gesture:` on a beat is different: it plays once the beat's line has been said.
  For a line to the room rather than to you, put `follow_me: off` on that beat:
  he faces forward and nods there.
- **Wandering never makes him speak.** On stage only the scenario speaks; while
  wandering he turns towards voices, nothing more. He never wanders asleep.
- **Two worked examples**: [`keynote.scenario.yaml`](keynote.scenario.yaml)
  and [`conference-talk.scenario.yaml`](conference-talk.scenario.yaml). Both are
  walked slide by slide in the tests, forwards and backwards, checking what the
  robot is told at every step.
- **The builder shows no control for `voice`, `speed` or `pause`**, but it
  carries them through a load-and-save untouched. `once` is carried the same way.
- **The projector shows who is speaking.** While a beat with `persona:` speaks,
  the overlay draws that persona's look — set per persona under Robot ›
  Persona › Edit › *Look*; the built-ins come with one (the butler is Slab, the
  kids companion Buddy, the workshop coach Host). A line in the talk's own
  voice, or a persona without a look, shows the character chosen in the header.
  A mid-line `[persona:x]` hand-over keeps the beat's look for the whole line.
- **A persona that names no character is still spoken**, in the presentation
  voice, and the Present panel says which id it could not find.

## If you are an assistant regenerating this file

1. **Never invent a field.** The table above is the whole list. If something
   needs a field that is not there, say so instead of writing it — it will be
   refused at load, and if it were not, it would do nothing at all, which is
   worse.
2. **Run `python scripts/check_scenario.py <file>` and paste the output.** It
   is the difference between "I generated a scenario" and "here is what this
   talk will do".
3. **Count the spoken beats and say the number.** Talks make promises about how
   often the robot speaks, and a generator that quietly adds one breaks a line
   the presenter says out loud.
4. **Keep the comments.** A generated scenario is read by a human under
   pressure, on a stage, and the comments are how they remember which presses
   are theirs.
5. **Slide numbers come from the deck**, not from you. If the deck changed,
   regenerate from the deck rather than adjusting numbers by hand.
