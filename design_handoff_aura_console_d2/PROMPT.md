# Build brief — paste this into Claude Code

> Copy everything below the line into Claude Code as your opening message, with this folder
> available in the working directory. It is written to be self-sufficient.

---

## Task

Implement the AURA console redesign in `apps/operator-console`. Everything you need is in the
`design_handoff_aura_console_d2/` folder in this repo:

- `README.md` — the full spec: design tokens for both themes, every view described component by
  component, interaction behaviour, and a state table mapped onto the existing Pinia stores.
  **Read this first and in full.**
- `designs/AURA Console (D2 - One Surface).dc.html` — the main design. Open it in a browser; it has
  working navigation, theme and mode switches, and three density levels.
- `designs/AURA Setup Wizard.dc.html` — the 7-step first-run wizard, same deal.
- `reviews/Coverage Review.dc.html` — a capability audit mapping every feature of the current
  console to its home in the new one. **Use this as the build checklist.**
- `reviews/UX Review.dc.html` — why the redesign looks like this: eight findings against the current
  console, each with the code evidence behind it.
- `screenshots/` — reference stills of every view, light and dark.

The HTML files are **design references, not code to copy**. They run on a prototype runtime
(`support.js`, `.dc.html`) that must not be ported. Read the markup and the literal values, then
rebuild in Vue 3 + TypeScript + Pinia using the app's existing patterns: SFCs in `src/components/`,
stores in `src/stores/`, `lucide-vue-next` for icons, tokens in `src/styles/tokens.css`.

## Ground rules

1. **Preserve every existing capability.** The redesign is a re-organisation, not a feature cut.
   `reviews/Coverage Review.dc.html` lists all of them and where each one now lives. Two things are
   deliberately dropped: dockable resizable panels (the density dial replaces them) and custom
   frameless window controls (use native OS chrome).
2. **This is high-fidelity.** Match the token values exactly. Where this brief and the prototype
   disagree, the prototype wins — read its inline styles.
3. **Do not invent new colours.** One accent (AURA green). `--present` purple is a semantic signal
   for Present mode only, never a user preference. The current four-accent picker is removed.
4. **Never hand-write a value that can be derived.** Counts, sub-lines, beat positions and capability
   summaries must come from the data. The prototype was corrected several times for exactly this.

## Do these first, in this order

**1. Tokens, fonts, shell.**
Replace `tokens.css` with the two-theme token set from the README (light = warm paper, dark = deep
evergreen). Self-host IBM Plex Sans + IBM Plex Mono — this is a desktop app that must work offline.
Then build the shell: 52px header, capability chip row, collapsible labelled rail, single health
chip, always-visible Stop.

**2. Wire modes to the policy backend. This is the highest-value change in the whole project.**
`MODE_TOOL_MAP` already exists in `shared-policies` and governs what the robot may do, per mode —
along with per-mode personas and TTS voices. But **nothing in the current console ever calls
`POST /robot/mode`**: mode surfaces only as a 9px tinted dot in the Robot State panel and a word in
the title bar, and per-mode voices are configurable only by editing `TTS_VOICE_WORK` /
`TTS_VOICE_HOME` env vars. So:

- Put `Home / Work / Present` in the header as the visually heaviest control on screen.
- Render the capability chip row beneath it from the actual policy: `allows` (green wash), `asks`
  (amber wash, label suffixed `· asks`), `blocked` (dashed border, struck through).
- Make the chips clickable: owner → the mode editor; anyone else → an explanation of who can change
  it. Never render a rule with no route to its source.
- Move per-mode persona, voice and memory-writing behaviour out of env vars into the settings store
  so the Modes editor can write them.
- `Quiet hours` is a **separate** toggle that composes with any mode. It is a speaking behaviour, not
  a capability scope — do not model it as a fourth mode.

**3. Talk, People, Robot.**
Talk: presence card + conversation, tool badges that expand to the real sent/returned payloads,
approvals that name the rule that caused them. People: owner-scoped (only the owner sees everyone
and can add/forget); Profile / Memory / Sources / Skills tabs; `[[wiki-links]]` substituted inline
as clickable references, never left as literal brackets. Robot: camera capped at 190px so the
action library and persona editor are reachable without scrolling.

**4. Modes editor, Settings consolidation, About.**
Settings absorbs the separate Capabilities modal — permissions are settings. About becomes its own
view, not a settings row.

**5. The setup wizard.**
Seven steps. Step 2 must keep its honest empty state: explain *why* no robot was found, list the
three preconditions in failure-likelihood order, and present "Continue without a robot" as a
visually equal choice rather than a skip link. Step 3 shows the corrected sync command
(`aura sync --target robot --profile default`) beside the wrong one from the manual, struck through.

**6. Activity + the two canvases, last or in parallel.**
The Mind visualisation and the knowledge graph are self-contained canvas components; treat them as
two isolated units. Both honour `prefers-reduced-motion`. Two implementation notes that were bugs
in the prototype before they were fixed — inherit the fixes, not the bugs:
- Mind: rejection-sample every neuron against the *same* outline polygon that gets drawn, so no
  neuron can escape the cortex when coordinates change.
- Graph: keep re-fitting the camera while the force simulation still has kinetic energy, and include
  glow halos and labels in the bounding box. Hand the camera to the user permanently on their first
  drag or zoom; `Reset` restores auto-fit.

## Non-negotiables

- Mode stays visually heavier than density. Affordance tracks consequence: one governs what a robot
  may do in someone's house, the other only changes how much detail is on screen.
- Stop is always visible, in the same place, in every mode and at every density.
- Density changes information volume only — never what the robot may do.
- With no face visible but someone typing, ask who is typing. Misattributed memory is worse than no
  memory. Unknown face and empty room get different copy. Guest states plainly that nothing is
  saved, and there is always a visible way to switch person or drop back to Guest.
- One word per concept: **Mode**, and **allows / asks / blocked** — in the UI, the config keys and
  the docs, identically.

## When you are done

Walk `reviews/Coverage Review.dc.html` row by row and confirm each capability has a real home in
the running app. Report anything you could not place rather than quietly dropping it.
