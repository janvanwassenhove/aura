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

**Not yet wired (next unit) — needs on-device verification:** the API endpoints
to load/drive a scenario, feeding the presenter's live speech into `on_speech`
for keyword beats, routing the PowerPoint watcher into a running talk, and the
console **presenter view** (big subtitles, next-beat button, slide + camera).
The keyword-while-you-talk path also depends on echo cancellation that isn't
stable yet — treat it as experimental.
