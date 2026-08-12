# Diagrams

The canonical drawings of this system. They are hand-authored SVG — not
generated, not exported from a tool — because a diagram whose whole job is to be
accurate is the wrong place for anything that draws plausible boxes.

| File | What it shows | Where it is used |
|---|---|---|
| `trust-boundary.svg` | The two hosts, and what each one is allowed to hold | README, ADR-008 |
| `one-turn.svg` | One conversational turn: two model rounds and the approval gate | README |
| `wiring.svg` | What listens on what: the two loopback processes, the console's one address, and the one-way Wi-Fi link | `docs/architecture/overview.md` |
| `media-paths.svg` | The three media paths — camera, microphone, speaker — and where each one is processed | `docs/architecture/overview.md` |
| `degradation-ladder.svg` | The heartbeat, and the four rungs the system falls through | `docs/architecture/overview.md` |
| `three-loops.svg` | Perception, conversation and maintenance on three different clocks | `docs/architecture/overview.md` |
| `knowledge-model.svg` | The four node types and the two edge types | ADR-008, `docs/architecture/overview.md` |
| `envelope-encryption.svg` | Passphrase → owner key → one key per person → records | README, ADR-008 |
| `delegation-bounds.svg` | What a delegated sub-agent may reach, and the three bounds on it | `docs/architecture/overview.md` |
| `hook-order.svg` | Where a hook sits relative to the approval gate and the tool | `docs/architecture/overview.md` |
| `build-loop.svg` | How a unit moves through the build loop, and where it stops to ask | `docs/agentic-plan.md` |

## Keeping them true

**A change to the shape of the system is not finished until the drawing matches
it.** This is a rule in the constitution
([`.specify/memory/constitution.md`](../../.specify/memory/constitution.md)),
not a suggestion here — a diagram that used to be right is worse than no diagram,
because it is believed.

Concretely, update the relevant file when you change:

- which process holds which data, or what crosses the network between the two
  hosts (`trust-boundary.svg`)
- the number of model rounds in a turn, or what the gate covers (`one-turn.svg`)
- a loop's cadence, or the states a conversation passes through
  (`three-loops.svg`)
- the node or edge types in the knowledge layer (`knowledge-model.svg`)
- the key hierarchy or what rotation touches (`envelope-encryption.svg`)
- a sub-agent's allowlist, round budget or depth limit
  (`delegation-bounds.svg`)
- where hooks fire relative to the gate (`hook-order.svg`)
- a port, a protocol, or which process may call which (`wiring.svg`)
- an audio or video format, endpoint, or where transcription and synthesis run
  (`media-paths.svg`)
- a heartbeat threshold, or what happens when a dependency stops answering
  (`degradation-ladder.svg`)

## House style

So a new drawing looks like it belongs:

| | |
|---|---|
| Ground | `#f4efe3` with a faint 24px grid at 35 % opacity |
| Panels | `#efe7d6`, ink `#34302b`, secondary text `#6f6659` |
| Frame | Double hairline in `#b8933f` |
| Accent | `#c0522d` — **once per drawing**, on the one thing that matters |
| Type | Consolas / ui-monospace, 19–22px body on a 1000-wide canvas |
| Canvas | 1000 wide, height to suit; lay out vertically rather than in wide rows |

That last row is not aesthetic. These are shown at about 690 px in a text
column, so a 13px label lands at roughly 7px and stops being readable. Draw at
1000 wide with 19–22px type, then look at the result rendered at 690 before
committing it.
