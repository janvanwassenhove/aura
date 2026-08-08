<template>
  <div class="graph-wrap">
    <canvas
      ref="canvas" class="graph-canvas"
      role="img" :aria-label="graphSummary"
      @mousemove="onMove" @mousedown="onDown" @mouseup="onUp" @mouseleave="onLeave"
      @wheel.prevent="onWheel"
    />
    <!-- U222 (1.1.1 / 2.1.1): the canvas is unreachable without a mouse, and a
         screen reader sees a blank box. This list holds the SAME nodes and the
         same open action, visually hidden but focusable — so the graph has a
         keyboard path and a text alternative without changing how it looks. -->
    <ul class="graph-a11y-list">
      <li v-for="n in openableNodes" :key="`${n.kind}:${n.id}`">
        <button type="button" @click="emit('open', n.kind, n.id)">
          {{ n.label }} ({{ n.kind }})
        </button>
      </li>
    </ul>
    <div v-if="hover" class="graph-tip" :style="{ left: hover.x + 14 + 'px', top: hover.y + 8 + 'px' }">
      <strong>{{ hover.label }}</strong><span class="tip-kind">{{ hover.kind }}</span>
    </div>
    <div class="graph-zoom">
      <button class="gz-btn" title="Zoom in" aria-label="Zoom in" @click="zoomBy(1.2)">+</button>
      <button class="gz-btn" title="Zoom out" aria-label="Zoom out" @click="zoomBy(1 / 1.2)">−</button>
      <button class="gz-btn" title="Reset zoom &amp; position" aria-label="Reset zoom and position" @click="resetView">⤢</button>
    </div>
    <p class="graph-legend">
      <span class="lg lg-person" /> person · <span class="lg lg-skill" /> skill ·
      <span class="lg lg-fact" /> fact · <span class="lg lg-topic" /> topic/source — drag to pan, scroll to zoom, click a node to open
    </p>
  </div>
</template>

<script setup lang="ts">
/** U75: Obsidian-style graph over the brain — people, skills and facts as a
 *  force-directed constellation. Pure canvas, no dependencies. */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { filterGraph } from '../lib/graphFilter'

interface GNode {
  id: string; label: string; kind: 'person' | 'skill' | 'fact' | 'topic'
  x: number; y: number; vx: number; vy: number; r: number
}
interface GEdge { a: number; b: number }

const props = defineProps<{
  people: { person_id: string; display_name: string }[]
  skills: { name: string; description: string; person: string; body: string }[]
  facts: { person_id: string; key: string; value: string }[]
  // U214: narrow the constellation to these person ids. Empty = everyone.
  onlyPeople?: string[]
}>()
const emit = defineEmits<{ (e: 'open', kind: string, id: string): void }>()

const canvas = ref<HTMLCanvasElement | null>(null)
// Mirrors of the canvas contents for assistive tech (kept in sync by buildGraph).
const graphSummary = ref('Knowledge graph')
const openableNodes = ref<{ id: string; label: string; kind: string }[]>([])
const hover = ref<{ x: number; y: number; label: string; kind: string } | null>(null)

let nodes: GNode[] = []
let edges: GEdge[] = []
let raf = 0
let ticks = 0

// U106: pan/zoom viewport. World→screen: sx = wx * scale + ox. Plain object
// (mutated each frame by the render loop — no reactivity needed).
const view = { scale: 1, ox: 0, oy: 0 }
let drag: { sx: number; sy: number; ox: number; oy: number; moved: boolean } | null = null

function seededRand(i: number): number {
  const x = Math.sin(i * 999 + 7) * 10000
  return x - Math.floor(x)
}

function buildGraph(w: number, h: number): void {
  nodes = []
  edges = []
  const idx = new Map<string, number>()
  const add = (id: string, label: string, kind: GNode['kind'], r: number): number => {
    const i = nodes.length
    nodes.push({
      id, label, kind, r,
      x: w / 2 + (seededRand(i) - 0.5) * w * 0.6,
      y: h / 2 + (seededRand(i + 77) - 0.5) * h * 0.6,
      vx: 0, vy: 0,
    })
    idx.set(`${kind}:${id.toLowerCase()}`, i)
    return i
  }
  // U214: narrow to the selected people (see lib/graphFilter). Topics are added
  // below only when a surviving fact links to them, so they filter themselves.
  const { people, skills, facts } = filterGraph(
    { people: props.people, skills: props.skills, facts: props.facts },
    props.onlyPeople ?? [],
  )

  for (const p of people) add(p.person_id, p.display_name, 'person', 16)
  for (const sk of skills) add(sk.name, sk.name, 'skill', 9)
  for (const f of facts) add(`${f.person_id}:${f.key}`, `${f.key}: ${f.value}`, 'fact', 4)

  const link = (ka: string, kb: string) => {
    const a = idx.get(ka), b = idx.get(kb)
    if (a !== undefined && b !== undefined) edges.push({ a, b })
  }
  for (const sk of skills) {
    if (sk.person) link(`skill:${sk.name}`, `person:${sk.person.toLowerCase()}`)
    // [[wikilinks]] in the body connect to people or other skills.
    for (const m of sk.body.matchAll(/\[\[([^\]]+)\]\]/g)) {
      const t = m[1].trim().toLowerCase()
      link(`skill:${sk.name}`, `person:${t}`)
      link(`skill:${sk.name}`, `skill:${t}`)
    }
  }
  for (const f of facts) link(`fact:${f.person_id}:${f.key}`.toLowerCase(), `person:${f.person_id.toLowerCase()}`)

  // U105: [[topics]] inside fact values become SHARED nodes — the same topic
  // (or source host, via provenance) across people/facts is one node, so the
  // mined information builds up visibly around each persona.
  for (const f of facts) {
    for (const m of f.value.matchAll(/\[\[([^\]]+)\]\]/g)) {
      const t = m[1].trim()
      const key = t.toLowerCase()
      // An existing person/skill with that name IS the node — link to it.
      if (idx.has(`person:${key}`)) { link(`fact:${f.person_id}:${f.key}`.toLowerCase(), `person:${key}`); continue }
      if (idx.has(`skill:${key}`)) { link(`fact:${f.person_id}:${f.key}`.toLowerCase(), `skill:${key}`); continue }
      if (!idx.has(`topic:${key}`)) add(t, t, 'topic', 7)
      link(`fact:${f.person_id}:${f.key}`.toLowerCase(), `topic:${key}`)
    }
  }
  // U222: publish a text view of what was just drawn.
  const counts: Record<string, number> = {}
  for (const n of nodes) counts[n.kind] = (counts[n.kind] ?? 0) + 1
  graphSummary.value = 'Knowledge graph: ' + (Object.entries(counts)
    .map(([k, v]) => `${v} ${k}${v === 1 ? '' : 's'}`).join(', ') || 'empty')
  openableNodes.value = nodes
    .filter(n => n.kind === 'person' || n.kind === 'skill')
    .map(n => ({ id: n.id, label: n.label, kind: n.kind }))

  ticks = 0
}

function step(w: number, h: number): void {
  // Repulsion
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j]
      let dx = a.x - b.x, dy = a.y - b.y
      let d2 = dx * dx + dy * dy
      if (d2 < 1) { dx = seededRand(i + j) - 0.5; dy = 0.5 - seededRand(j); d2 = 1 }
      const f = Math.min(1200 / d2, 4)
      const d = Math.sqrt(d2)
      a.vx += (dx / d) * f; a.vy += (dy / d) * f
      b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
    }
  }
  // Springs
  for (const e of edges) {
    const a = nodes[e.a], b = nodes[e.b]
    const dx = b.x - a.x, dy = b.y - a.y
    const d = Math.max(1, Math.hypot(dx, dy))
    const want = a.kind === 'fact' || b.kind === 'fact' ? 46 : 110
    const f = (d - want) * 0.02
    a.vx += (dx / d) * f; a.vy += (dy / d) * f
    b.vx -= (dx / d) * f; b.vy -= (dy / d) * f
  }
  // Gravity to center + integrate
  for (const n of nodes) {
    n.vx += (w / 2 - n.x) * 0.004
    n.vy += (h / 2 - n.y) * 0.004
    n.vx *= 0.82; n.vy *= 0.82
    n.x = Math.max(20, Math.min(w - 20, n.x + n.vx))
    n.y = Math.max(20, Math.min(h - 20, n.y + n.vy))
  }
}

const COLORS = { person: '#f0b429', skill: '#5cb8e4', fact: '#7ba7c9', topic: '#9d7be0' }

function draw(): void {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')!
  const { width: w, height: h } = c
  ctx.setTransform(1, 0, 0, 1, 0, 0)
  ctx.clearRect(0, 0, w, h)
  // U106: everything below is drawn in world coords; the viewport scales/pans it.
  ctx.setTransform(view.scale, 0, 0, view.scale, view.ox, view.oy)
  ctx.strokeStyle = 'rgba(120, 150, 180, 0.25)'
  ctx.lineWidth = 1
  for (const e of edges) {
    ctx.beginPath()
    ctx.moveTo(nodes[e.a].x, nodes[e.a].y)
    ctx.lineTo(nodes[e.b].x, nodes[e.b].y)
    ctx.stroke()
  }
  for (const n of nodes) {
    ctx.beginPath()
    ctx.fillStyle = COLORS[n.kind]
    ctx.shadowColor = COLORS[n.kind]
    ctx.shadowBlur = n.kind === 'fact' ? 4 : 14
    ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
    ctx.fill()
    ctx.shadowBlur = 0
    if (n.kind !== 'fact') {
      ctx.fillStyle = 'rgba(226, 232, 240, 0.85)'
      ctx.font = '11px sans-serif'
      // U120: keep labels inside the frame — right-align near the right edge,
      // left-align near the left, so text never spills past the canvas.
      const sx = n.x * view.scale + view.ox   // node x in screen space
      if (sx > w - 90) { ctx.textAlign = 'right'; ctx.fillText(n.label, n.x - n.r - 4, n.y + 4) }
      else if (sx < 90) { ctx.textAlign = 'left'; ctx.fillText(n.label, n.x + n.r + 4, n.y + 4) }
      else { ctx.textAlign = 'center'; ctx.fillText(n.label, n.x, n.y + n.r + 13) }
    }
  }
}

// U217: once the force sim has settled (ticks >= 260) the old loop kept
// repainting at 60 fps forever — and draw() sets shadowBlur per node, the most
// expensive canvas-2D primitive, so a docked graph left on-screen burned ~30-100%
// of a core doing nothing. Now the loop stops rescheduling once settled; any
// interaction (pan/zoom/hover/rebuild) calls redraw() to resume.
function loop(): void {
  const c = canvas.value
  if (!c) return
  if (ticks < 260) {
    step(c.width, c.height); ticks++
    draw()
    raf = requestAnimationFrame(loop)
  } else {
    draw()            // final frame, then idle
    raf = 0
  }
}

/** Repaint once (interaction), restarting the loop only if the sim is still
 *  running. Cheap when settled: a single draw(), no rAF churn. */
function redraw(): void {
  if (raf) return                       // a loop is already scheduling frames
  if (ticks < 260) { raf = requestAnimationFrame(loop) }
  else draw()
}

function nodeAt(sx: number, sy: number): GNode | null {
  // Screen → world before hit-testing, so picking follows pan/zoom.
  const wx = (sx - view.ox) / view.scale
  const wy = (sy - view.oy) / view.scale
  for (const n of nodes) {
    if (Math.hypot(n.x - wx, n.y - wy) <= n.r + 4) return n
  }
  return null
}

function onDown(ev: MouseEvent): void {
  const rect = canvas.value!.getBoundingClientRect()
  drag = { sx: ev.clientX - rect.left, sy: ev.clientY - rect.top, ox: view.ox, oy: view.oy, moved: false }
}

function onMove(ev: MouseEvent): void {
  const rect = canvas.value!.getBoundingClientRect()
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top
  if (drag) {  // panning
    const dx = mx - drag.sx, dy = my - drag.sy
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    view.ox = drag.ox + dx
    view.oy = drag.oy + dy
    hover.value = null
    canvas.value!.style.cursor = 'grabbing'
    redraw()
    return
  }
  const n = nodeAt(mx, my)
  hover.value = n ? { x: mx, y: my, label: n.label, kind: n.kind } : null
  canvas.value!.style.cursor = n ? 'pointer' : 'grab'
  redraw()
}

function onUp(ev: MouseEvent): void {
  // A press that didn't move is a click — open the node under it.
  if (drag && !drag.moved) {
    const rect = canvas.value!.getBoundingClientRect()
    const n = nodeAt(ev.clientX - rect.left, ev.clientY - rect.top)
    if (n && n.kind !== 'fact' && n.kind !== 'topic') emit('open', n.kind, n.id)
  }
  drag = null
}

function onLeave(): void {
  drag = null
  hover.value = null
}

function zoomAt(sx: number, sy: number, factor: number): void {
  const newScale = Math.max(0.2, Math.min(4, view.scale * factor))
  // Keep the world point under (sx,sy) fixed while scaling.
  view.ox = sx - (sx - view.ox) * (newScale / view.scale)
  view.oy = sy - (sy - view.oy) * (newScale / view.scale)
  view.scale = newScale
  redraw()
}

function onWheel(ev: WheelEvent): void {
  const rect = canvas.value!.getBoundingClientRect()
  zoomAt(ev.clientX - rect.left, ev.clientY - rect.top, ev.deltaY < 0 ? 1.1 : 1 / 1.1)
}

function zoomBy(factor: number): void {
  const c = canvas.value
  if (c) zoomAt(c.width / 2, c.height / 2, factor)  // zoom toward the centre
}

function resetView(): void {
  view.scale = 1
  view.ox = 0
  view.oy = 0
  redraw()
}

function resize(): void {
  const c = canvas.value
  if (!c || !c.parentElement) return
  c.width = c.parentElement.clientWidth
  c.height = Math.max(360, c.parentElement.clientHeight - 30)
  buildGraph(c.width, c.height)   // resets ticks → 0
  redraw()                        // restart the sim loop for the fresh layout
}

watch(() => [props.people, props.skills, props.facts, props.onlyPeople], resize, { deep: true })
onMounted(() => { resize(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) })
</script>

<style scoped>
.graph-wrap { position: relative; width: 100%; height: 100%; min-height: 380px; }
.graph-a11y-list {
  position: absolute; width: 1px; height: 1px; margin: -1px;
  padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
.graph-a11y-list:focus-within {
  position: static; width: auto; height: auto; margin: 0; clip: auto;
  white-space: normal; background: var(--surface); padding: 0.4rem;
  border-radius: var(--radius-md); max-height: 40%; overflow: auto;
}
.graph-canvas {
  width: 100%; height: calc(100% - 26px); display: block;
  background: radial-gradient(ellipse at center, #23272e 0%, #1a1d22 100%);
  border-radius: var(--radius-lg);
  cursor: grab;
}
.graph-zoom {
  position: absolute; top: 0.5rem; right: 0.5rem; z-index: 6;
  display: flex; flex-direction: column; gap: 0.25rem;
}
.gz-btn {
  width: 26px; height: 26px; display: grid; place-items: center;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); color: var(--text); cursor: pointer;
  font-size: 0.95rem; line-height: 1; padding: 0;
}
.gz-btn:hover { background: var(--surface-2); }
.graph-tip {
  position: absolute; pointer-events: none; z-index: 5;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); padding: 0.3rem 0.55rem; font-size: 0.72rem;
  box-shadow: var(--shadow-modal); display: flex; gap: 0.4rem; align-items: baseline;
  max-width: 18rem;
}
.tip-kind { color: var(--text-faint); font-size: 0.65rem; }
.graph-legend { margin: 0.35rem 0 0; font-size: 0.7rem; color: var(--text-faint); }
.lg { display: inline-block; width: 9px; height: 9px; border-radius: 50%; vertical-align: baseline; }
.lg-person { background: #f0b429; }
.lg-skill { background: #5cb8e4; }
.lg-fact { background: #7ba7c9; width: 6px; height: 6px; }
.lg-topic { background: #9d7be0; }
</style>
