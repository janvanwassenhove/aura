# Handoff: AURA Console (D2 — One Surface) + Setup Wizard

> **Start here:** `PROMPT.md` is written to be pasted straight into Claude Code. This README is the
> reference spec it points at.

## Overview

A full redesign of the AURA operator console — the Electron/Vue desktop app that drives Richie,
an embodied assistant running on a Reachy Mini robot. It replaces the current three-competing-
products console (robot remote + chat client + knowledge manager) with **one surface** whose
information volume is controlled by a density dial, and it makes **modes** (Home / Work / Present)
a first-class capability boundary rather than an invisible backend setting.

Also included: a **7-step first-run setup wizard**, replacing the shipping 6-step one.

Source of truth for the current app: `janvanwassenhove/aura`, branch `aura-autobuild`,
`apps/operator-console/`. See `github.md` in the project root.

### What changes, in one list

1. **Modes are first-class.** `Home / Work / Present` in the header, with a capability chip row
   directly beneath showing exactly what the current mode allows, what it asks about, and what it
   blocks. Chips are clickable (owner → the mode editor; non-owner → who can change it).
   `Quiet hours` is a *separate* toggle that composes with any mode — it is a speaking behaviour,
   not a capability scope.
2. **One surface, three densities.** `Calm / Standard / Full` replaces the two-surface
   Companion/Workbench split and the shipping app's dockable panels. Density changes how much of
   the *same* screen is exposed; it never changes what the robot may do. Density defaults per
   recognised person (kids → Calm, owner → Full).
3. **One navigation system.** A collapsible labelled rail (Talk, People, Skills, Robot, Present,
   Activity, Modes, Settings, About) replaces title-bar icon soup + five full-screen modals.
   Identical at every density.
4. **One status grammar.** A single health chip (Brain · Robot · Vault) that is quiet when all is
   well and names the specific problem when not. Replaces five different status vocabularies.
5. **Stop never moves.** Same place, same colour, every mode, every density.
6. **The Mind view.** A canvas visualisation of the brain actually working, driven by the real
   event stream.
7. **A real knowledge graph.** Obsidian-style: draggable nodes, pan, zoom, force layout,
   `[[wiki-link]]` targets as shared nodes.

## About the design files

The files in `designs/` are **design references written in HTML** — interactive prototypes showing
intended look and behaviour. They are **not production code to copy**.

The task is to **recreate these designs inside the existing `apps/operator-console` Vue 3 +
TypeScript + Pinia app**, using its established patterns:

- Single-file components in `src/components/`, Pinia stores in `src/stores/`
- Design tokens in `src/styles/tokens.css` — extend/replace this file with the token set below
- `lucide-vue-next` for icons (all icons in the prototype are Lucide paths)
- The existing brain HTTP client and event-stream plumbing stays as-is

The prototypes are built on an internal HTML component runtime (`support.js`, `.dc.html`). Ignore
that machinery entirely; read the markup and the values.

**Do not** port `support.js` or the `.dc.html` format into the app. It is bundled only so the
prototypes open and run in a browser for reference.

## Fidelity

**High-fidelity.** Final colours, typography, spacing, radii, copy, and interaction states.
Recreate pixel-accurately using the token values below. Where the prototype and this README
disagree, the prototype wins — read the inline styles.

Two things are intentionally schematic and need a real implementation decision:
- The camera feed is a CSS gradient placeholder; wire the real MJPEG/WebRTC stream.
- Recognition snapshots and the audience camera are gradient rectangles; wire real frames.

## Design tokens

Two themes. Light is warm paper, dark is deep evergreen. Set on `:root[data-aura-theme]`.

### Light

```
--bg:#f0efe9        --surface:#ffffff    --surface-2:#f7f6f2   --sunken:#e9e8e1   --hover:#eceae2
--line:#dcdad0      --line-strong:#b8b6aa
--ink:#1a2420       --ink-2:#43524a      --ink-3:#6b776f
--accent:#1f6f46    --accent-deep:#175236 --accent-wash:#e4efe7 --on-accent:#ffffff
--ok:#1f6f46        --ok-wash:#e4efe7
--warn:#9a6510      --warn-wash:#f7ecd6
--danger:#b3362a    --danger-wash:#f8e5e2
--info:#2f5d8a      --info-wash:#e3ecf5
--present:#6d4fa1   --present-wash:#ece5f6
```

### Dark

```
--bg:#0e1512        --surface:#17201b    --surface-2:#1c2721   --sunken:#0b110e   --hover:#233029
--line:#2b3830      --line-strong:#465548
--ink:#e6ece7       --ink-2:#a9b8ae      --ink-3:#7c8b81
--accent:#4fae7c    --accent-deep:#7fd3a8 --accent-wash:#1c2f25 --on-accent:#0b1710
--ok:#4fae7c        --ok-wash:#1c2f25
--warn:#d9a441      --warn-wash:#33270f
--danger:#e0655a    --danger-wash:#361511
--info:#7fa9d4      --info-wash:#16283a
--present:#a98fd6   --present-wash:#261d38
```

Semantic rule: **one accent** (AURA green). `--present` purple is reserved as a *semantic signal*
for Present mode, never a user preference. The shipping app's four-accent picker is removed.

### Typography

- UI: **IBM Plex Sans** — 400 / 500 / 600 / 700
- Numeric, technical, code, ids, timings: **IBM Plex Mono** — 400 / 500 / 600

Scale actually used (px): `9.5 · 10.5 · 11 · 11.5 · 12 · 12.5 · 13 · 13.5 · 14 · 14.5 · 15 · 16 · 19 · 20 · 22`
Section labels: 10.5px mono, weight 700, `letter-spacing:0.1em`, uppercase, `--ink-3`.
Body copy: 13–14.5px, `line-height:1.5–1.6`, `max-width:58–64ch`.

### Spacing, radii, shadows

- Spacing: 4 · 5 · 6 · 7 · 9 · 12 · 14 · 16 · 18 · 22 · 26 (px)
- Radii: **9–11px** controls, **14px** cards, **999px** pills. Nothing else.
- Shadows: none. Separation is done with `--line` borders and `--surface` vs `--sunken`.

## Screens / views

### Shell (always present)

**Header**, 52px, `--surface`, 1px `--line` bottom border, `padding:0 14px 0 16px`, `gap:16px`:

- Richie mark (26px inline SVG) + `AURA` 15px/700 + `RICHIE · REACHY MINI` 10px mono `--ink-3`
- **Mode switcher** — 3 segments in a `--sunken` pill group, `border-radius:10px`, `padding:3px`.
  Active segment: `--accent` fill (`--present` for Present), white text, `border-radius:8px`,
  `padding:6px 16px`, 13px/600. Visually the heaviest control in the header — its consequence is
  the highest.
- **Quiet hours** toggle — separate from the mode group.
- **Density dial** — `Calm / Standard / Full`, same pill-group shape but *smaller and lighter* than
  the mode group. Icons with tooltips.
- **Identity chip** — who is talking (see Identity below).
- **Health chip** — one chip, silent when fine.
- **Stop** — `padding:7px 14px`, transparent fill, `1.5px solid --danger`, 13px/700,
  hover inverts to solid `--danger` + white. Never hidden, never moves.

**Update banner** (conditional, directly under the header): `--info-wash`, 9px/16px padding,
download icon, "Version 1.5.0 is downloaded and ready — installing takes about ten seconds and
keeps your memory and settings.", `Install & restart` (solid `--info`) + `Later` (ghost).

**Capability chip row**, under the header, `--surface-2` (or `--present-wash` in Present mode):
mode name in 10.5px mono uppercase, then one chip per tool group:

| State | Style |
|---|---|
| allows | `--ok-wash` bg, `--ok` text, transparent border |
| asks | `--warn-wash` bg, `--warn` text, label suffixed `· asks` |
| blocked | transparent bg, `--ink-3` text, `1px dashed --line-strong`, `text-decoration:line-through` |

All chips 11.5px/600, `padding:2px 10px`, `border-radius:999px`. Row ends with a clickable
"Edit boundaries →" affordance.

**Rail**, left, collapsible (64px icons-only ⇄ 190px labelled). Items: Talk, People, Skills,
Robot, Present, Activity, Modes; Settings and About pinned to the bottom. Active item:
`--accent-wash` bg, `--accent` icon+label, `border-radius:10px`.

### Talk

Two columns: context cards (300px) + conversation (flex, `min-width:320px`).

- **Presence card** — camera 16:9 (`max-height:190px`), LIVE pill, "Sees Jan 92%" pill,
  Follow/Manual segmented control; below: state dot + "Awake & idle" + `richie · home` in mono;
  Mic / Notify / Sleep toggle row; volume slider; briefing time; persona select + Edit.
- **Conversation** — user bubbles `--accent` fill, `border-radius:16px 16px 5px 16px`, right-aligned,
  `max-width:78%`. Assistant bubbles `--surface-2` + `--line` border,
  `border-radius:5px 16px 16px 16px`, preceded by the 24px Richie mark.
- **Tool badge** — 10.5px mono chip in `--ok-wash`. **Clickable**: expands to a `--sunken` panel
  showing `Sent` and `Returned` JSON payloads, timing, the rule that allowed the call, and a Copy
  action. Closed by default; only rendered above Calm density.
- **Approval gate** — inline in the transcript, `--warn` bordered. Names the rule that caused the
  ask ("Home mode normally blocks mail, so he is asking"), links to that rule, and offers
  Allow once / Allow and remember / Deny.
- **Composer** — textarea + mic + teach + Send. Teach hidden at Calm.

### People

Rail (260px) + detail. **Owner-scoped**: only the owner sees everyone and can add; everyone else
sees only themselves, loses "+ Add a person", search, the role dropdown (becomes a read-only
"set by the owner" chip), Permissions and Forget.

- **Unknown visitors** queue (owner only) — `--warn` bordered box in the rail: thumbnail, when and
  where seen, `Tag as…` select (tagging absorbs the guest profile), Dismiss.
- **Person header** — 48px avatar, name, role pill, derived sub-line
  (`Face known · 6 facts · 12 memories · encrypted on this laptop` — *derive this, never hard-code it*),
  then Teach face / Add a fact / Open graph / Permissions / Consent select / Forget.
- **Tabs** — Profile · Memory · Sources · Skills.
  - *Profile*: "Recently seen" snapshot strip (hidden when no face is enrolled) with a ✕ per
    snapshot that re-files a wrong match; then facts as a `minmax(200px,1fr)` grid. Facts render
    `[[targets]]` **substituted inline** as underlined clickable references — never as literal
    brackets, never as an appended chip.
  - *Memory*: editable textarea + Save / Clear all, with a real empty state.
  - *Sources*: per-person URLs with health dots, add, "Read them now", plus Import a chat export
    and Export the brain (JSON).
  - *Skills*: skills bound to this person.
- **Graph** — canvas. Small in the aside, plus a full-width Graph view. Drag nodes (pinned while
  held), drag background to pan, wheel to zoom 0.25×–4×. Force layout: repulsion + springs +
  damping. Node types: person `--accent`, fact `--info`, skill `--present`, topic `--warn`; glow
  halo, orbiting ring on person nodes, hover highlights that node's links, pulses travel edges.
  Auto-fits while the simulation still has kinetic energy, then hands the camera to the user
  permanently on first interaction (`Reset` restores auto-fit).

### Skills

Card grid + an **editor** (opens from "+ New skill" or a card's edit): name, who may use it,
which modes, trigger chips, the procedure body in a monospace textarea (plain instructions, not
code), required connectors, `Test it now`, `Save skill`.

### Robot

Camera 16:9 capped at 190px (left) beside "Ask him to…" (right) so the action library is visible
without scrolling; Character (with animated preview) below; Connection last.

- Body toggles, volume, briefing time, persona select + **Edit** → the 7-field persona editor:
  display name, voice, speaking rate, verbosity, humour, gesture style, wake response, plus a
  free-text "how he should sound", `Hear a sample`, `Delete persona`.
- **Characters** — Richie plus KITT / TARS / Baymax / R2-D2 / Marvin / EVE style personalities,
  each with its own idle + speaking animation preview.
- **Connection** — mDNS/refused/timeout diagnosis, address field, network scan. Keep the shipping
  app's honest error copy; it is the best thing in the current UI.

### Present

Scenario picker, beats list (slide and keyword cues, say/do per beat), YAML import, presenter
settings aside. While presenting, a **live HUD**: `--present` header with beat counter, audience
camera, "Saying now", the gesture line, "Next cue", transport (previous / skip / pause), and
Laptop audio / Laptop mic / Camera off toggles.

**One beat index drives everything** — the run bar, HUD counter, saying-now, gesture line, next
cue, and the highlighted row all derive from a single `beatIdx`. Do not let these diverge.

### Activity

The Mind canvas plus a faceted log: Events · Motion · App log · Approvals, with a filter.

**Mind rendering** (canvas, `requestAnimationFrame`, honours `prefers-reduced-motion`):
brain-shaped cortex silhouette with sulci (dark fold + light highlight offset beneath), a
cerebellum lobe with its own folds, a stem anchored under the temporal underside; holographic
interior (radial core glow, scan lines, isoline contour rings, a sweeping read-out bar while
working, neon rim). Eight regions — Hearing, Vision, Memory, Language, Rules, Tools, Voice, Body —
each a cluster of diamond neurons with a dendrite web, **rejection-sampled against the same
outline polygon that is drawn** so no neuron can ever escape the cortex. Events fire spike trains
along animated dashed axon fibres, carrying the real payload as a capsule; the receiving cluster
fires outward in a wave. Amber = mode said *asks*, blue = perception, green = normal flow. Idle
drops to a dim resting hum. A live activity trace runs along the bottom of the large canvas.

### Modes

The editor: per mode, per tool group, `allows / asks / blocked`; per-mode persona, voice and
memory-writing behaviour (these were env-var-only in the shipping app); and an "Apps he may drive"
chip list, shown only when the mode does not block screen control.

### Settings

Sectioned, one home for every knob: Intelligence (provider, key status, four model roles,
conversation engine + `Test realtime access`), Connections (per-connector status with device-code
sign-in, Test, Reconnect, Disconnect), Capabilities, Privacy & permissions (vault, remembered
decisions), Voice & wake word, Appearance.

### About

Its own view, **not** a settings row: Richie art, `AURA`, "Adaptive Unified Robotic Assistant",
`version 2.0.77`, the embodied-assistant description, the four-word acronym breakdown
(Adaptive / Unified / Robotic / Assistant), link cards (mityjohn.com — blog & projects by
mITy.John; GitHub — source & releases), then Check for updates / Restart the brain / Run setup
again / Diagnostics. Footer: "Made by Jan Van Wassenhove · built with the Reachy Mini SDK".

### Setup wizard — 7 steps

250px stepper aside (jump freely between steps) + step body + footer (Back · note · Skip/Later ·
Continue). Skip appears on steps 1, 4 and 5; `Later` on step 6; steps 2 and 3 carry their own
deliberate inline alternative instead of a duplicate footer Skip.

1. **Meet your assistant** — name (max 24), reply language (auto / NL / EN / FR), what setup needs.
2. **Find the robot** — mDNS scan; when nothing is found, an *honest* empty state that explains
   why, lists three preconditions in failure-likelihood order (booted → same network, not guest
   wifi → is the robot even running the AURA service yet), offers a manual address + Test, and
   presents **"Continue without a robot" as a visually equal choice**, not a skip link.
3. **Install on the robot** — four described actions, each tagged `needs approval` or `safe`;
   the **corrected** sync command (`aura sync --target robot --profile default`) shown beside the
   wrong one from the manual, struck through; self-update on by default.
4. **Choose a brain** — OpenAI / OpenRouter / Gemini cards, key field, already-set state, and the
   free-model hint for people without a key.
5. **Hands-free voice** — wake-word switch + editable wake word.
6. **Create yourself** — you as a person with role `owner`, optional face enrolment (four photos →
   fingerprint, photos discarded), and the vault passphrase (min 8, error state,
   already-encrypted state).
7. **Learn the panels** — five things about the console, then done. Ends recommending Home mode
   with mail set to "asks first".

## Interactions & behaviour

- **Density** changes information volume only: Calm hides tool badges, the teach button, turn
  metadata, provenance, the log strip and the mono detail; Full shows everything. Type sizes and
  paddings scale slightly with density (see `calm`/`full` conditionals in the prototype).
- **Identity**: with a recognised face, the chip shows who. With **no face visible** but someone
  typing, an identity bar asks "Who is typing?" — because misattributed memory is worse than no
  memory. Unknown face and empty room get *different* copy. Guest openly states nothing is saved.
  The person card stays the persistent identity control: reassign or drop to Guest at any time,
  and auto-drop to Guest after a period with no face.
- **Approvals** explain themselves by naming the causing rule, and the reason changes per mode.
- Animations: `breathe` ~4.6s idle on the Richie mark; canvas work in rAF; everything honours
  `prefers-reduced-motion`.
- Hover: controls gain `--accent` border/text; rows gain `--surface-2`.
- Focus: keep the shipping app's `:focus-visible` treatment.

## State

Extend the existing Pinia stores rather than inventing parallel state.

| State | Where it belongs | Notes |
|---|---|---|
| `mode` | new `modeStore` (or `robotStore`) | home / work / present. **Drives the backend policy** — `MODE_TOOL_MAP` already exists in `shared-policies`. Wire the switcher to `POST /robot/mode`; nothing in the shipping console calls it today. |
| `quiet` | `prefsStore` | independent of mode |
| `density` | `prefsStore` | calm / standard / full, plus a per-person default |
| `view` | `navStore` | replaces `layoutStore` docking state |
| `railCollapsed` | `prefsStore` | |
| `speaker` | `knowledgeStore` | recognised or manually chosen; null = ask |
| `person`, `personTab` | `knowledgeStore` | selected person + Profile/Memory/Sources/Skills |
| `beatIdx`, `rehearsing` | new `presenterStore` | single source for the run bar and HUD |
| graph camera + node positions | component-local | not persisted |
| `toolOpen`, `personaEditorOpen`, `skillEditorOpen`, `updateDismissed` | component-local | |

Per-mode persona, voice and TTS behaviour must move from env vars
(`TTS_VOICE_WORK` / `TTS_VOICE_HOME` / …) into the settings store so the Modes editor can write them.

## Assets

- **Icons** — Lucide, already a dependency (`lucide-vue-next`). Every icon in the prototype is a
  Lucide path; match by shape.
- **Richie mark** — inline SVG in the prototypes (64×64 viewBox: two antennas with tips, rounded
  body, two eyes with highlights). Reuse the existing `RichieAvatar.vue` and give it the antenna
  variant.
- **Fonts** — IBM Plex Sans + IBM Plex Mono. Self-host or vendor them; do not depend on a CDN in a
  desktop app that must work offline.
- **Camera / snapshots** — placeholders only; wire real streams.

## Files in this bundle

```
PROMPT.md                                   paste this into Claude Code to start the build
designs/
  AURA Console (D2 - One Surface).dc.html   the main design — all views, both themes, all densities
  AURA Setup Wizard.dc.html                 the 7-step first-run wizard
  support.js                                prototype runtime — reference only, do NOT port
reviews/
  UX Review.dc.html                         the original assessment of the shipping console:
                                            8 findings with code evidence, and why D2 looks like this
  UX Review - D Unified.dc.html             critique of the intermediate direction, incl. the reasoning
                                            that led to one-surface-plus-density
  Coverage Review.dc.html                   capability audit: every feature in the shipping console
                                            mapped to its home in D2. Use this as the build checklist.
  AURA Console (Current).dc.html            faithful recreation of today's console, for before/after
screenshots/
  01-talk-light.png            Talk view, light theme, Standard density
  02-people-light.png          People — owner scope, unknown visitors, snapshots, consent
  03-robot-light.png           Robot — camera, body toggles, actions, character, connection
  04-activity-mind-light.png   Activity + the Mind canvas
  05-modes-light.png           Modes editor — per-group allows/asks/blocked, allowed apps
  06-present-light.png         Present — scenario, beats, presenter HUD
  07-settings-light.png        Settings — consolidated sections
  08-about-light.png           About — acronym, links, maintenance actions
  09-talk-dark.png             Talk view, dark theme
  10-activity-mind-dark.png    Activity, dark theme
  11..17-wizard-*.png          the seven wizard steps in order
```

> Screenshot caveat: the capture re-renders the DOM, so the two `<canvas>` surfaces (the Mind
> visualisation and the knowledge graph) come out blank in the stills. Open the HTML designs in a
> browser to see them animate — that is the only accurate reference for both.

Open any file directly in a browser. Both design files expose theme (and starting mode / starting
step) switches so you can inspect every state.

## Suggested order of work

1. Tokens + fonts + the shell (header, capability row, rail, health chip, Stop).
2. Wire the mode switcher to the existing policy backend — this is the highest-value change and
   the backend already supports it.
3. Talk, then People (owner scoping matters here), then Robot.
4. Modes editor, Settings consolidation, About.
5. The setup wizard.
6. Activity + the Mind canvas, and the graph canvas. These are self-contained and can be done last
   or in parallel; treat them as two isolated canvas components.

## Non-negotiables from the design review

- Mode must remain visually heavier than density. Affordance tracks consequence.
- Stop is always visible, in the same place, in every mode and density.
- Never render a rule with no route to its source.
- Never show a count that is written by hand — derive it from the data.
- One word per concept: **Mode**, and **allows / asks / blocked**. Use these in the UI, the config
  keys, and the docs identically.
