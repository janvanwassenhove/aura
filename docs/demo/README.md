# Test presentation — "I Hired a Real Robot as My Junior Dev"

A co-presenter demo that exercises every beat type (U205). You keep PowerPoint;
the robot participates via a scenario.

## Files

| File | What |
|---|---|
| `robot-junior-dev.pptx` | 7-slide deck (regenerate with `build_robot_junior_dev_pptx.py`) |
| `robot-junior-dev.scenario.yaml` | the co-presenter script — beats, modes, triggers |
| `build_robot_junior_dev_pptx.py` | regenerates the deck: `uv run --with python-pptx python docs/demo/build_robot_junior_dev_pptx.py` |

## What each beat does

| Beat | Trigger | Mode | The robot… |
|---|---|---|---|
| `intro` | slide 1 | speak | says a fixed opening line + waves |
| `kids-java` | you say **"Java"** | chime_in | adds one remark about kids learning differently — in the **Kids Companion** voice (U349) |
| `thesis` | slide 4 | improvise | riffs on "software is a commodity, expertise isn't" + nods |
| `agent-factory` | you say **"agents"** | chime_in | one confident line about the agent fleet |
| `the-question` | slide 6 | silent | stays quiet — you own the uncomfortable question |
| `closing` | manual | speak | delivers the closing line, handing one clause to Kids Companion and taking it back (U349) |

`slide:N` uses PowerPoint's own 1-based numbering. `keyword:` fires when *you*
say the word while presenting. `manual` fires when you advance the beat by hand.

## Editing the scenario

It's plain YAML, validated by the `Scenario` model. Each beat needs:

- `speak` → `text` (spoken verbatim)
- `improvise` / `chime_in` → `topic` (+ optional `guardrails`)
- `chime_in` → must use a `keyword:` trigger
- optional `gesture` (e.g. `wave`, `nod`) and `engine` (`pipeline` / `realtime`)
- optional `persona` — the character that speaks the beat (U349)

### Who speaks a beat (U349)

`persona: <id>` names a character from **Robot → personas** (`dry_tech_butler`,
`kids_companion`, …). That character's own voice and speed speak the beat, and
when the beat improvises, its character note shapes the words too. Leave it out
and the beat uses the Present panel's Voice, exactly as before.

Inside a `speak` beat's text you can hand the line over mid-sentence:

```yaml
text: "Misschien. [persona:kids_companion]Of iets veel leukers![persona] De rest typ ik wel."
```

`[persona]` (or `[/persona]`) hands it back to the beat's own persona. The
markers are never spoken, and a malformed one is refused when you save rather
than read out on stage. The pieces are synthesized separately and joined into
**one** utterance, so the change of character is not also a change of volume —
see [ADR-012](../adr/ADR-012-a-line-is-one-utterance-however-many-voices-it-has.md).

A persona id that matches no character is still spoken, in the presentation
voice, and the Present panel says which id it could not find. The scenario
builder warns about unknown inline ids while you are still at a desk.

A beat that needs a live lookup (calendar, data) must set `engine: pipeline` —
the realtime engine has no tool access (U203).

## What's built and what's next

**Built and tested (this unit):** the beat model, the runner that fires beats on
manual / slide / keyword triggers and executes each mode, this test presentation
(the deck + scenario), and a PowerPoint slide-watcher for Windows.

**Wired live (U206):** the API (`POST /presentation/scenario|next|speech`,
`GET /presentation/status`, `DELETE /presentation/scenario`), the runner speaks
and gestures through the real robot and improvises via the LLM, the PowerPoint
watcher feeds `slide:N` beats, the voice loop feeds your speech to keyword
beats, and the console **presenter view** (the 🖥 icon in the title bar) shows
big subtitles, the current slide, armed keywords, a camera thumbnail and a
next-beat button.

## Running it

1. Open your `.pptx` and start the slideshow (F5).
2. In AURA, click the **presenter** icon in the title bar.
3. Paste your scenario YAML (e.g. this folder's `robot-junior-dev.scenario.yaml`)
   and press **Start presentation**.
4. Advance your slides as usual — `slide:N` beats fire; say a keyword — chime-in
   beats fire; press **Next beat** for the hand-advanced ones.

**Robust keyword listening (U209):** turn on **Keyword mic** in the presenter to
recognise keywords from THIS laptop's microphone instead of the robot's. The
laptop mic is near you, and recognition is paused whenever the laptop speaks, so
it can't trigger on its own voice — this sidesteps the robot's echo-cancellation
problem. (The robot's own mic still feeds keywords too; the laptop mic is the
dependable path for a real demo.)

**Laptop audio (U209):** turn on **Laptop audio** to have this laptop read the
robot's lines aloud through its speakers — useful in a room where the robot's
own speaker is small. It's the laptop's voice, not the robot's exact audio.

**Live data in a beat (U208):** set a beat's engine to **with tools**
(`engine: pipeline`) and it runs the full agentic loop — calendar, music, a
lookup — then speaks the result. Fast text beats leave engine on default.

**Not yet verified on the real robot + real PowerPoint end to end** — the API,
runner, watcher-degradation and presenter view are each tested (fakes / preview
/ dry-run), but the full live chain needs a run on the actual stack.
