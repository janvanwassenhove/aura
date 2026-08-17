<template>
  <canvas
    ref="cv" aria-label="Knowledge graph — drag nodes, drag the background to pan, scroll to zoom"
    style="display: block; width: 100%; height: 100%; cursor: grab"
  />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { PersonDetail } from '../../stores/knowledgeStore'

/** Obsidian-style knowledge graph, drawn from one person's REAL profile.
 *
 * Drag a node (pinned while held), drag the background to pan, wheel to zoom
 * 0.25×–4×. Force layout: repulsion + springs + damping. Node types: person
 * accent, fact info, skill present, topic warn. `[[topics]]` are SHARED nodes —
 * the same target across facts is one node, and a target that names a person
 * is a person node.
 *
 * Camera rules inherited from the prototype's bug-fixes, not its bugs:
 *  - keep auto-fitting while the simulation still has kinetic energy, with the
 *    glow halos AND the labels inside the bounding box;
 *  - hand the camera to the user permanently on their first drag or zoom;
 *    `reset()` restores auto-fit.
 */

const props = defineProps<{
  detail: PersonDetail | null
  peopleIds: string[]
}>()

const emit = defineEmits<{ (e: 'open-person', id: string): void }>()

interface GNode {
  id: string; label: string; kind: 'person' | 'fact' | 'skill' | 'topic'
  r: number; x: number; y: number; vx: number; vy: number; fixed?: boolean
  personId?: string
}
interface Graph { pid: string; nodes: GNode[]; links: [number, number, number][] }

const cv = ref<HTMLCanvasElement | null>(null)
let graph: Graph | null = null
let view = { z: 1, px: 0, py: 0, fit: false, w: 0, h: 0, userMoved: false }
let drag: { node: GNode; dx: number; dy: number } | null = null
let pan: { x: number; y: number; px: number; py: number } | null = null
let hover: GNode | null = null
let raf = 0
const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

function buildGraph(): Graph | null {
  const d = props.detail
  if (!d) return null
  const pid = d.person.person_id
  if (graph && graph.pid === pid && graph.nodes.length) return graph
  let seed = 99
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  const nodes: GNode[] = []
  const links: [number, number, number][] = []
  const add = (id: string, label: string, kind: GNode['kind'], r: number, personId?: string) => {
    const a = rnd() * 6.28, rad = 60 + rnd() * 130
    nodes.push({ id, label, kind, r, x: Math.cos(a) * rad, y: Math.sin(a) * rad, vx: 0, vy: 0, personId })
    return nodes.length - 1
  }
  const root = add(pid, d.person.display_name, 'person', 22, pid)
  const topicIdx: Record<string, number> = {}
  for (const f of d.facts) {
    const refs = [...f.value.matchAll(/\[\[([^\]]+)\]\]/g)].map(m => m[1])
    const clean = f.value.replace(/\[\[([^\]]+)\]\]/g, '$1')
    const i = add(`f${f.fact_id}`, `${f.key}: ${clean}`, 'fact', 9)
    links.push([root, i, 1])
    // [[topics]] are SHARED nodes — one node per target, whatever mentions it.
    for (const name of refs) {
      if (topicIdx[name] === undefined) {
        const isPerson = props.peopleIds.includes(name)
        topicIdx[name] = add(`t${name}`, name, isPerson ? 'person' : 'topic', isPerson ? 14 : 11, isPerson ? name : undefined)
      }
      links.push([i, topicIdx[name], 0.9])
    }
  }
  for (const sk of d.skills ?? []) {
    const i = add(`s${sk.name}`, sk.name, 'skill', 12)
    links.push([root, i, 1])
  }
  for (const sig of d.signals.slice(0, 8)) {
    const i = add(`g${sig.signal_id}`, `${sig.kind}: ${sig.value}`.slice(0, 40), 'topic', 8)
    links.push([root, i, 0.7])
  }
  // Cross-links so it reads as a web, not a star.
  for (let i = 1; i < nodes.length; i++) {
    if (rnd() > 0.72 && nodes.length > 2) links.push([i, 1 + Math.floor(rnd() * (nodes.length - 1)), 0.4])
  }
  graph = { pid, nodes, links }
  view = { z: 1, px: 0, py: 0, fit: false, w: 0, h: 0, userMoved: false }
  return graph
}

watch(() => props.detail?.person.person_id, () => { graph = null })

function reset(): void {
  graph = null
  view = { z: 1, px: 0, py: 0, fit: false, w: 0, h: 0, userMoved: false }
}
defineExpose({ reset })

function toWorld(e: PointerEvent | WheelEvent) {
  const el = cv.value!
  const r = el.getBoundingClientRect()
  return {
    x: (e.clientX - r.left - r.width / 2 - view.px) / view.z,
    y: (e.clientY - r.top - r.height / 2 - view.py) / view.z,
  }
}

function onPointerDown(e: PointerEvent): void {
  const el = cv.value
  if (!el || !graph) return
  const p = toWorld(e)
  el.setPointerCapture(e.pointerId)
  view.userMoved = true // the camera is theirs from here on
  const hit = [...graph.nodes].reverse().find(n => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 6)
  if (hit) { drag = { node: hit, dx: hit.x - p.x, dy: hit.y - p.y }; hit.fixed = true }
  else pan = { x: e.clientX, y: e.clientY, px: view.px, py: view.py }
  el.style.cursor = 'grabbing'
}
function onPointerMove(e: PointerEvent): void {
  if (!graph) return
  if (drag) {
    const p = toWorld(e)
    drag.node.x = p.x + drag.dx; drag.node.y = p.y + drag.dy
    drag.node.vx = 0; drag.node.vy = 0
  } else if (pan) {
    view.px = pan.px + (e.clientX - pan.x)
    view.py = pan.py + (e.clientY - pan.y)
  } else {
    const p = toWorld(e)
    hover = [...graph.nodes].reverse().find(n => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 6) ?? null
    if (cv.value) cv.value.style.cursor = hover ? 'pointer' : 'grab'
  }
}
function onPointerUp(e: PointerEvent): void {
  // A click (no drag movement) on a person node navigates.
  if (drag && hover && drag.node === hover && hover.kind === 'person' && hover.personId) {
    emit('open-person', hover.personId)
  }
  if (drag) drag.node.fixed = false
  drag = null; pan = null
  if (cv.value) cv.value.style.cursor = 'grab'
}
function onWheel(e: WheelEvent): void {
  e.preventDefault()
  view.userMoved = true
  const f = Math.exp(-e.deltaY * 0.0016)
  view.z = Math.max(0.25, Math.min(4, view.z * f))
}

function draw(): void {
  const el = cv.value
  if (!el || !el.clientWidth) return
  const G = buildGraph()
  if (!G) return

  // Relaxation step: repulsion + spring, damped.
  if (!reduced || !view.fit) {
    for (const n of G.nodes) {
      if (n.fixed) continue
      let fx = -n.x * 0.0016, fy = -n.y * 0.0016
      for (const m of G.nodes) {
        if (m === n) continue
        const dx = n.x - m.x, dy = n.y - m.y
        const d2 = Math.max(120, dx * dx + dy * dy)
        const f = 2600 / d2
        fx += dx * f * 0.02; fy += dy * f * 0.02
      }
      n.vx = (n.vx + fx) * 0.86; n.vy = (n.vy + fy) * 0.86
    }
    for (const [a, b, w2] of G.links) {
      const A2 = G.nodes[a], B2 = G.nodes[b]
      if (!A2 || !B2) continue
      const dx = B2.x - A2.x, dy = B2.y - A2.y
      const dist = Math.max(1, Math.hypot(dx, dy))
      const rest = 108 + A2.r + B2.r
      const f = ((dist - rest) / dist) * 0.012 * w2
      if (!A2.fixed) { A2.vx += dx * f; A2.vy += dy * f }
      if (!B2.fixed) { B2.vx -= dx * f; B2.vy -= dy * f }
    }
    for (const n of G.nodes) { if (!n.fixed) { n.x += n.vx; n.y += n.vy } }
  }

  const C = {
    ink: css('--ink'), ink2: css('--ink-2'), ink3: css('--ink-3'),
    line: css('--line'), surface: css('--surface'),
    accent: css('--accent'), info: css('--info'), warn: css('--warn'), present: css('--present'),
  }
  const colOf: Record<GNode['kind'], string> = { person: C.accent, fact: C.info, skill: C.present, topic: C.warn }
  const t = performance.now() / 1000

  const dpr = Math.min(devicePixelRatio || 1, 2)
  const w = el.clientWidth, h = el.clientHeight
  if (el.width !== w * dpr || el.height !== h * dpr) { el.width = w * dpr; el.height = h * dpr }

  // Keep fitting while the simulation is still moving; stop for good once the
  // user takes the camera. Halos and labels count toward the bounding box.
  const energy = G.nodes.reduce((a, n) => a + Math.abs(n.vx) + Math.abs(n.vy), 0)
  if ((!view.userMoved && (energy > 0.4 || !view.fit)) || view.w !== w || view.h !== h) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    for (const n of G.nodes) {
      const halo = n.r * 2.6
      x0 = Math.min(x0, n.x - halo); x1 = Math.max(x1, n.x + halo)
      y0 = Math.min(y0, n.y - halo); y1 = Math.max(y1, n.y + n.r + 18) // label sits below
    }
    const m = 34
    const z = Math.max(0.25, Math.min(2.2, Math.min((w - m * 2) / Math.max(1, x1 - x0), (h - m * 2) / Math.max(1, y1 - y0))))
    view.z = z
    view.px = -((x0 + x1) / 2) * z
    view.py = -((y0 + y1) / 2) * z
    view.fit = true; view.w = w; view.h = h
  }

  const g = el.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)
  const smallG = w < 380

  // Grid backdrop.
  g.strokeStyle = C.line; g.globalAlpha = 0.5; g.lineWidth = 1
  const step = 34 * view.z
  const offx = (w / 2 + view.px) % step, offy = (h / 2 + view.py) % step
  for (let x = offx; x < w; x += step) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke() }
  for (let y = offy; y < h; y += step) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke() }
  g.globalAlpha = 1

  g.save()
  g.translate(w / 2 + view.px, h / 2 + view.py); g.scale(view.z, view.z)

  // Links, with a travelling glow so the web feels alive.
  for (const [a, b] of G.links) {
    const A2 = G.nodes[a], B2 = G.nodes[b]
    if (!A2 || !B2) continue
    const near = hover && (A2 === hover || B2 === hover)
    g.strokeStyle = near ? colOf[A2.kind] : C.ink3
    g.globalAlpha = near ? 0.8 : 0.22
    g.lineWidth = (near ? 1.6 : 1) / view.z
    g.beginPath(); g.moveTo(A2.x, A2.y); g.lineTo(B2.x, B2.y); g.stroke()
    if (!reduced) {
      const p = ((t * 0.22 + (a + b) * 0.13) % 1)
      g.globalAlpha = near ? 0.9 : 0.32
      g.fillStyle = colOf[B2.kind] || C.accent
      g.beginPath(); g.arc(A2.x + (B2.x - A2.x) * p, A2.y + (B2.y - A2.y) * p, 1.8 / view.z, 0, 6.3); g.fill()
    }
  }
  g.globalAlpha = 1

  // Nodes.
  for (const n of G.nodes) {
    const col = colOf[n.kind] || C.accent
    const hovered = hover === n
    const pulse = reduced ? 1 : 1 + 0.04 * Math.sin(t * 1.6 + n.x * 0.01)
    const r = n.r * pulse
    const grd = g.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 2.6)
    grd.addColorStop(0, col); grd.addColorStop(1, 'transparent')
    g.globalAlpha = hovered ? 0.35 : 0.18; g.fillStyle = grd
    g.beginPath(); g.arc(n.x, n.y, r * 2.6, 0, 6.3); g.fill(); g.globalAlpha = 1
    g.fillStyle = n.kind === 'person' ? col : C.surface
    g.strokeStyle = col; g.lineWidth = (hovered ? 2.4 : 1.6) / view.z
    g.beginPath(); g.arc(n.x, n.y, r, 0, 6.3); g.fill(); g.stroke()
    if (n.kind === 'person' && !reduced) {
      g.strokeStyle = col; g.globalAlpha = 0.5; g.lineWidth = 1 / view.z
      g.beginPath(); g.arc(n.x, n.y, r + 7, 0.4 + t * 0.6, 2.4 + t * 0.6); g.stroke()
      g.beginPath(); g.arc(n.x, n.y, r + 7, 3.6 + t * 0.6, 5.6 + t * 0.6); g.stroke()
      g.globalAlpha = 1
    }
    if (view.z > 0.5 && (!smallG || n.r > 9 || hovered)) {
      const label = n.label.length > 26 && !hovered ? n.label.slice(0, 25) + '…' : n.label
      g.font = `${n.kind === 'person' ? 600 : 400} ${(smallG ? 9 : 11) / view.z}px ${css('--font-ui') || 'sans-serif'}`
      g.textAlign = 'center'
      g.fillStyle = hovered ? C.ink : C.ink2
      g.fillText(label, n.x, n.y + r + (smallG ? 10 : 13) / view.z)
    }
  }
  g.restore()
}

function frame(): void {
  draw()
  raf = requestAnimationFrame(frame)
}

onMounted(() => {
  const el = cv.value!
  el.addEventListener('pointerdown', onPointerDown)
  el.addEventListener('pointermove', onPointerMove)
  el.addEventListener('pointerup', onPointerUp)
  el.addEventListener('pointercancel', onPointerUp)
  el.addEventListener('pointerleave', () => { hover = null })
  el.addEventListener('wheel', onWheel, { passive: false })
  if (reduced) {
    // Settle the layout without animating: run the sim to rest, then draw once
    // per second (the graph still updates when the data changes).
    for (let i = 0; i < 300; i++) draw()
    const timer = setInterval(draw, 1000)
    onUnmounted(() => clearInterval(timer))
  } else {
    raf = requestAnimationFrame(frame)
  }
})
onUnmounted(() => cancelAnimationFrame(raf))
</script>
