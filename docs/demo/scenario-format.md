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
    once: true             # chime_in: fire at most once (default true)
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
| `once` | bool | `true` | `chime_in`: fire at most once however often the word is said. |
| `overlay` | `""` \| `show` \| `hide` | `""` | Move the projector overlay from this beat onwards. Empty leaves it alone. |
| `persona` | character id | `""` | Which character speaks this beat — its voice, speed, and (when improvising) its way of putting things. |
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
- **The builder shows no control for `voice`, `speed` or `pause`**, but it
  carries them through a load-and-save untouched.
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
