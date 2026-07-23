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
| `kids-java` | you say **"Java"** | chime_in | adds one remark about kids learning differently |
| `thesis` | slide 4 | improvise | riffs on "software is a commodity, expertise isn't" + nods |
| `agent-factory` | you say **"agents"** | chime_in | one confident line about the agent fleet |
| `the-question` | slide 6 | silent | stays quiet — you own the uncomfortable question |
| `closing` | manual | speak | delivers the closing line |

`slide:N` uses PowerPoint's own 1-based numbering. `keyword:` fires when *you*
say the word while presenting. `manual` fires when you advance the beat by hand.

## Editing the scenario

It's plain YAML, validated by the `Scenario` model. Each beat needs:

- `speak` → `text` (spoken verbatim)
- `improvise` / `chime_in` → `topic` (+ optional `guardrails`)
- `chime_in` → must use a `keyword:` trigger
- optional `gesture` (e.g. `wave`, `nod`) and `engine` (`pipeline` / `realtime`)

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

**Still experimental:** keyword beats fire from what the robot's mic hears while
you talk, so they depend on echo cancellation that isn't fully stable — the
robot may occasionally react to its own voice. `improvise` uses the LLM for a
spoken line (no tools); a beat needing live data should be a `speak` beat.

**Not yet verified on the real robot + real PowerPoint end to end** — the API,
runner, watcher-degradation and presenter view are each tested (fakes / preview
/ dry-run), but the full live chain needs a run on the actual stack.
