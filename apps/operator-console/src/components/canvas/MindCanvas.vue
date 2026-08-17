<template>
  <canvas ref="cv" aria-label="Live view of what the assistant is processing"
          :style="{ display: 'block', width: '100%', height: height + 'px' }" />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useEventStore } from '../../stores/eventStore'
import { useModeStore } from '../../stores/modeStore'

/** The Mind — the brain actually working, drawn from the real event stream.
 *
 * Every node lights from a real bus event; nothing here is decorative. Eight
 * regions of diamond neurons sit inside a cortex silhouette, and each event
 * fires a spike train along a dashed axon fibre carrying its payload as a
 * capsule. Amber = the mode said *asks*, blue = perception, green = normal.
 * Idle drops to a dim resting hum.
 *
 * Rendering notes carried over from the prototype (they were bugs before they
 * were rules):
 *  - neurons are rejection-sampled against the SAME smoothed outline polygon
 *    the canvas draws, so no neuron can escape the cortex when coordinates
 *    change;
 *  - region labels are placed last and only where they fit, routing around
 *    the payload capsules already on screen.
 *
 * Honours prefers-reduced-motion: one calm frame per event, no rAF loop.
 */

const props = withDefaults(defineProps<{ height?: number; big?: boolean }>(), {
  height: 158,
  big: false,
})

const emit = defineEmits<{ (e: 'status', label: string): void }>()

const cv = ref<HTMLCanvasElement | null>(null)
const eventStore = useEventStore()
const modeStore = useModeStore()

// ── Region layout: frontal left, occipital right, cerebellum bottom-right ──
const MIND_NODES: Record<string, { label: string; x: number; y: number }> = {
  rules: { label: 'Rules', x: 0.20, y: 0.30 },
  voice: { label: 'Voice', x: 0.15, y: 0.60 },
  lang: { label: 'Language', x: 0.37, y: 0.47 },
  mem: { label: 'Memory', x: 0.55, y: 0.30 },
  body: { label: 'Body', x: 0.62, y: 0.60 },
  ears: { label: 'Hearing', x: 0.44, y: 0.76 },
  tools: { label: 'Tools', x: 0.78, y: 0.74 },
  eyes: { label: 'Vision', x: 0.85, y: 0.44 },
}
const CORTEX: [number, number][] = [
  [0.16, 0.30], [0.27, 0.14], [0.45, 0.07], [0.63, 0.09], [0.79, 0.17], [0.90, 0.32],
  [0.93, 0.48], [0.88, 0.62], [0.90, 0.76], [0.80, 0.86], [0.64, 0.86], [0.52, 0.90],
  [0.36, 0.88], [0.24, 0.78], [0.13, 0.64], [0.09, 0.46],
]
const ASPECT_H = 0.72 // design space 1.0 × 0.72 → a brain-like ~1.4 aspect
const SULCI: [number, number][][] = [
  [[0.24, 0.30], [0.36, 0.22], [0.46, 0.30]],
  [[0.30, 0.46], [0.44, 0.36], [0.58, 0.42]],
  [[0.20, 0.58], [0.36, 0.58], [0.48, 0.52]],
  [[0.52, 0.22], [0.64, 0.28], [0.72, 0.22]],
  [[0.60, 0.50], [0.72, 0.44], [0.84, 0.52]],
  [[0.44, 0.70], [0.58, 0.72], [0.70, 0.66]],
]
const MIND_EDGES: [string, string][] = [
  ['ears', 'lang'], ['eyes', 'mem'], ['eyes', 'lang'], ['mem', 'lang'], ['lang', 'rules'],
  ['lang', 'tools'], ['rules', 'tools'], ['lang', 'voice'], ['lang', 'body'], ['tools', 'lang'],
  ['mem', 'rules'],
]

// ── The real event stream → spikes ─────────────────────────────────────────
type Tone = 'ok' | 'warn' | 'info'
interface Spike { from: string; to: string; word: string; evt: string; tone: Tone; start: number }

function routeEvent(raw: Record<string, unknown>): Omit<Spike, 'start'> | null {
  const t = raw.event_type as string
  const s = (v: unknown, n = 22) => String(v ?? '').slice(0, n)
  switch (t) {
    case 'PersonRecognized':
      return { from: 'eyes', to: 'mem', tone: 'info', evt: t, word: `${s(raw.display_name || raw.person_id || 'unknown', 14)} · ${Number(raw.confidence ?? 0).toFixed(2)}` }
    case 'GestureDetected':
      return { from: 'eyes', to: 'lang', tone: 'info', evt: t, word: s(raw.gesture) }
    case 'TranscriptUpdated':
      return raw.is_final ? { from: 'ears', to: 'lang', tone: 'ok', evt: t, word: `“${s(raw.transcript, 18)}…”` } : null
    case 'IntentRecognized':
      return { from: 'lang', to: 'rules', tone: 'ok', evt: t, word: s(raw.tool_name || raw.intent) }
    case 'ToolCallRequested':
      return { from: 'rules', to: 'tools', tone: 'ok', evt: t, word: s(raw.tool_name) }
    case 'ToolCallSucceeded':
      return { from: 'tools', to: 'lang', tone: 'ok', evt: t, word: s(raw.tool_name) }
    case 'ToolCallFailed':
      return { from: 'tools', to: 'lang', tone: 'warn', evt: t, word: s(raw.error_code || raw.tool_name) }
    case 'ApprovalRequested':
      return { from: 'rules', to: 'voice', tone: 'warn', evt: `${t} · mode asks`, word: 'may I?' }
    case 'ApprovalGranted':
      return { from: 'voice', to: 'rules', tone: 'ok', evt: t, word: 'approved' }
    case 'ApprovalDenied':
      return { from: 'voice', to: 'rules', tone: 'warn', evt: t, word: 'denied' }
    case 'ResponseDrafted':
      return { from: 'lang', to: 'voice', tone: 'ok', evt: t, word: `“${s(raw.response_text, 16)}…”` }
    case 'MotionStarted':
      return { from: 'lang', to: 'body', tone: 'info', evt: t, word: s(raw.motion_id) }
    case 'SpeechPlaybackStarted':
    case 'SpeechStarted':
      return { from: 'voice', to: 'body', tone: 'ok', evt: t, word: 'speaking' }
    case 'MemoryRecalled':
      return { from: 'mem', to: 'lang', tone: 'info', evt: t, word: 'recall' }
    case 'AgentRoundStarted':
      return { from: 'lang', to: 'rules', tone: 'ok', evt: t, word: `round ${s(raw.round_no, 3)}` }
    default:
      return null
  }
}

const TRAVEL = 850
const LINGER = 900
let spikes: Spike[] = []
let lastSeenEventId: string | null = null
let lastStatus = ''

// ── Canvas machinery ───────────────────────────────────────────────────────
interface Cell { x: number; y: number; ph: number; s: number; d: number }
interface Cluster { cx: number; cy: number; R: number; cells: Cell[]; links: [number, number][] }
interface Brain {
  w: number; h: number
  clusters: Record<string, Cluster>
  fibers: { a: string; b: string; cx: number; cy: number }[]
}

let brain: Brain | null = null
let raf = 0
let t0 = performance.now()
let trace: number[] = new Array(140).fill(0)
const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888'
}

function ensureBrain(w: number, h: number, small: boolean): Brain {
  if (brain && brain.w === w && brain.h === h) return brain
  let seed = 20260816
  const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  const pad = small ? 14 : 22
  const reserve = small ? 12 : 34 // bottom band belongs to the activity trace
  // One uniform scale for both axes, centred — proportions survive any canvas.
  const availW = w - pad * 2, availH = h - reserve - pad * 1.4
  const s0 = Math.min(availW, availH / ASPECT_H)
  const ox = (w - s0) / 2
  const oy = pad * 0.7 + (availH - s0 * ASPECT_H) / 2
  const X = (nx: number) => ox + nx * s0
  const Y = (ny: number) => oy + ny * s0 * ASPECT_H
  // The same smoothed outline the canvas draws, as a testable polygon.
  const P = CORTEX.map(([nx, ny]) => ({ x: X(nx), y: Y(ny) }))
  const poly: { x: number; y: number }[] = []
  for (let i = 0; i < P.length; i++) {
    const cur = P[i], nxt = P[(i + 1) % P.length]
    const prev = P[(i - 1 + P.length) % P.length]
    const start = { x: (prev.x + cur.x) / 2, y: (prev.y + cur.y) / 2 }
    const end = { x: (cur.x + nxt.x) / 2, y: (cur.y + nxt.y) / 2 }
    for (let k = 0; k < 8; k++) {
      const tt = k / 8, u = 1 - tt
      poly.push({
        x: u * u * start.x + 2 * u * tt * cur.x + tt * tt * end.x,
        y: u * u * start.y + 2 * u * tt * cur.y + tt * tt * end.y,
      })
    }
  }
  const cxAll = poly.reduce((a, p) => a + p.x, 0) / poly.length
  const cyAll = poly.reduce((a, p) => a + p.y, 0) / poly.length
  const inside = (px: number, py: number) => {
    let hit = false
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      if ((poly[i].y > py) !== (poly[j].y > py) &&
          px < (poly[j].x - poly[i].x) * (py - poly[i].y) / (poly[j].y - poly[i].y) + poly[i].x) hit = !hit
    }
    return hit
  }
  const clusters: Record<string, Cluster> = {}
  for (const [id, n] of Object.entries(MIND_NODES)) {
    let cx = X(n.x), cy = Y(n.y)
    const R = Math.max(7, s0 * (small ? 0.075 : 0.062))
    // Pull a centre that sits too close to the rim back toward the middle.
    let guard = 0
    while (guard++ < 40 && !(inside(cx - R * 0.6, cy) && inside(cx + R * 0.6, cy) && inside(cx, cy - R * 0.6) && inside(cx, cy + R * 0.6))) {
      cx += (cxAll - cx) * 0.08; cy += (cyAll - cy) * 0.08
    }
    const count = small ? 7 : 14
    const cells: Cell[] = []
    let tries = 0
    while (cells.length < count && tries++ < count * 30) {
      const a = rnd() * Math.PI * 2, rr = Math.sqrt(rnd()) * R
      const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr * 0.85
      if (!inside(x, y)) continue // no neuron outside the cortex — ever
      cells.push({ x, y, ph: rnd() * 6.28, s: (small ? 0.9 : 1.1) + rnd() * 1.2, d: rnd() })
    }
    while (cells.length < count) cells.push({ x: cx, y: cy, ph: rnd() * 6.28, s: small ? 1 : 1.3, d: rnd() })
    const links: [number, number][] = []
    for (let i = 0; i < cells.length; i++) links.push([i, (i + 1 + Math.floor(rnd() * 2)) % cells.length])
    clusters[id] = { cx, cy, R, cells, links }
  }
  const fibers = MIND_EDGES.map(([a, b]) => {
    const A2 = clusters[a], B2 = clusters[b]
    const mx = (A2.cx + B2.cx) / 2, my = (A2.cy + B2.cy) / 2
    const dx = B2.cx - A2.cx, dy = B2.cy - A2.cy
    const bend = 0.1 + rnd() * 0.14
    return { a, b, cx: mx - dy * bend, cy: my + dx * bend }
  })
  brain = { w, h, clusters, fibers }
  return brain
}

function ingestEvents(): void {
  // events[0] is newest; walk until the last one we saw.
  const now = performance.now()
  const fresh: Spike[] = []
  for (const e of eventStore.events) {
    if (e.id === lastSeenEventId) break
    const routed = routeEvent(e.payload)
    if (routed) fresh.push({ ...routed, start: now + fresh.length * 180 })
  }
  if (eventStore.events.length) lastSeenEventId = eventStore.events[0].id
  if (fresh.length) spikes.push(...fresh.reverse())
  spikes = spikes.filter(s => now - s.start < TRAVEL + LINGER).slice(-14)
}

function draw(): void {
  const el = cv.value
  if (!el || !el.clientWidth) return
  ingestEvents()
  const idle = modeStore.quiet
  const now = performance.now()
  const elapsed = now - t0
  const secs = elapsed / 1000

  const C = {
    ink: css('--ink'), ink2: css('--ink-2'), ink3: css('--ink-3'),
    line: css('--line'), lineStrong: css('--line-strong'), surface: css('--surface'),
    sunken: css('--sunken'), accentWash: css('--accent-wash'),
    ok: css('--accent'), warn: css('--warn'), info: css('--info'),
  }

  const dpr = Math.min(devicePixelRatio || 1, 2)
  const w = el.clientWidth, h = el.clientHeight
  if (el.width !== w * dpr || el.height !== h * dpr) { el.width = w * dpr; el.height = h * dpr; brain = null }
  const g = el.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)
  const small = h < 170
  const B = ensureBrain(w, h, small)
  const blockers: { x0: number; y0: number; x1: number; y1: number }[] = []

  // Which regions are lit right now, and the current event label.
  const lit: Record<string, number> = {}
  let current: Spike | null = null
  for (const e of spikes) {
    const age = now - e.start
    if (age >= -120 && age <= TRAVEL + LINGER) {
      const p = Math.max(0, Math.min(1, age / TRAVEL))
      lit[e.from] = Math.max(lit[e.from] || 0, 1 - p * 0.7)
      if (p > 0.55) lit[e.to] = Math.max(lit[e.to] || 0, Math.min(1, (p - 0.55) / 0.3) * (1 - Math.max(0, (age - TRAVEL) / LINGER)))
      if (age >= 0 && age < TRAVEL + 400) current = e
    }
  }
  const status = idle
    ? 'Quiet hours — he is listening, not acting.'
    : current ? `${current.evt} · ${current.word}` : 'Waiting for something to happen'
  if (status !== lastStatus) { lastStatus = status; emit('status', status) }

  // ── cortex silhouette ──
  const pad = small ? 14 : 22
  const reserve = small ? 12 : 34
  const availW = w - pad * 2, availH = h - reserve - pad * 1.4
  const s0 = Math.min(availW, availH / ASPECT_H)
  const ox = (w - s0) / 2
  const oy = pad * 0.7 + (availH - s0 * ASPECT_H) / 2
  const X = (nx: number) => ox + nx * s0
  const Y = (ny: number) => oy + ny * s0 * ASPECT_H

  g.beginPath()
  const P = CORTEX.map(([nx, ny]) => ({ x: X(nx), y: Y(ny) }))
  g.moveTo((P[0].x + P[P.length - 1].x) / 2, (P[0].y + P[P.length - 1].y) / 2)
  for (let i = 0; i < P.length; i++) {
    const cur = P[i], nxt = P[(i + 1) % P.length]
    g.quadraticCurveTo(cur.x, cur.y, (cur.x + nxt.x) / 2, (cur.y + nxt.y) / 2)
  }
  g.closePath()
  // Holographic interior: gradient core, scan lines, contour rings, sweep.
  g.save(); g.clip()
  const bx0 = X(0.09), bx1 = X(0.93), by0 = Y(0.06), by1 = Y(0.94)
  const core = g.createRadialGradient((bx0 + bx1) / 2, (by0 + by1) / 2, 4, (bx0 + bx1) / 2, (by0 + by1) / 2, (bx1 - bx0) * 0.6)
  core.addColorStop(0, C.accentWash); core.addColorStop(1, C.sunken)
  g.fillStyle = core; g.globalAlpha = idle ? 0.55 : 0.9
  g.fillRect(bx0 - 8, by0 - 8, bx1 - bx0 + 16, by1 - by0 + 16); g.globalAlpha = 1
  g.strokeStyle = C.ok; g.globalAlpha = 0.09; g.lineWidth = 1
  for (let yy = by0; yy < by1; yy += small ? 4 : 5) { g.beginPath(); g.moveTo(bx0 - 8, yy); g.lineTo(bx1 + 8, yy); g.stroke() }
  // Contour rings, like an isoline scan of the tissue.
  g.globalAlpha = 0.14; g.lineWidth = 1
  for (let r = 0.12; r < 0.62; r += 0.11) {
    g.beginPath()
    for (let a2 = 0; a2 <= 6.3; a2 += 0.25) {
      const rr = r * (1 + 0.13 * Math.sin(a2 * 3 + r * 9))
      const xx = X(0.5 + rr * Math.cos(a2)), yy = Y(0.5 + rr * 1.25 * Math.sin(a2))
      a2 ? g.lineTo(xx, yy) : g.moveTo(xx, yy)
    }
    g.closePath(); g.stroke()
  }
  if (!idle && !reduced) {
    const sweepY = by0 + ((elapsed / 3400) % 1) * (by1 - by0)
    const sw = g.createLinearGradient(0, sweepY - 26, 0, sweepY + 4)
    sw.addColorStop(0, 'transparent'); sw.addColorStop(1, C.ok)
    g.globalAlpha = 0.16; g.fillStyle = sw; g.fillRect(bx0 - 8, sweepY - 26, bx1 - bx0 + 16, 30)
    g.globalAlpha = 0.4; g.strokeStyle = C.ok; g.lineWidth = 1
    g.beginPath(); g.moveTo(bx0 - 8, sweepY); g.lineTo(bx1 + 8, sweepY); g.stroke()
  }
  g.globalAlpha = 1; g.restore()
  // Glowing rim.
  g.save()
  g.shadowColor = C.ok; g.shadowBlur = small ? 8 : 16
  g.strokeStyle = C.ok; g.globalAlpha = idle ? 0.5 : 0.85; g.lineWidth = small ? 1.4 : 1.8; g.stroke()
  g.shadowBlur = 0; g.globalAlpha = 1; g.restore()
  // Cerebellum: its own lobe, tucked under the occipital pole.
  g.beginPath()
  g.moveTo(X(0.62), Y(0.80))
  g.quadraticCurveTo(X(0.78), Y(0.78), X(0.86), Y(0.86))
  g.quadraticCurveTo(X(0.78), Y(0.97), X(0.60), Y(0.92))
  g.quadraticCurveTo(X(0.56), Y(0.86), X(0.62), Y(0.80))
  g.fillStyle = C.sunken; g.globalAlpha = idle ? 0.5 : 0.75; g.fill(); g.globalAlpha = 1
  g.strokeStyle = C.ink3; g.globalAlpha = 0.5; g.lineWidth = 1.5; g.stroke(); g.globalAlpha = 1
  // Brain stem, anchored inside the temporal underside.
  g.beginPath(); g.moveTo(X(0.60), Y(0.86)); g.quadraticCurveTo(X(0.58), Y(0.97), X(0.66), Y(1.02))
  g.lineWidth = small ? 4 : 7; g.strokeStyle = C.sunken; g.lineCap = 'round'; g.stroke()
  g.strokeStyle = C.lineStrong || C.line; g.globalAlpha = 0.55; g.stroke(); g.globalAlpha = 1
  // Sulci — a light ridge beside the dark fold, so the folds actually read.
  for (const s2 of SULCI) {
    g.save(); g.translate(0, small ? 1.6 : 2.4)
    g.beginPath(); g.moveTo(X(s2[0][0]), Y(s2[0][1]))
    g.quadraticCurveTo(X(s2[1][0]), Y(s2[1][1]), X(s2[2][0]), Y(s2[2][1]))
    g.lineWidth = small ? 1.6 : 2.4; g.strokeStyle = C.surface; g.globalAlpha = 0.85; g.stroke()
    g.restore()
    g.beginPath(); g.moveTo(X(s2[0][0]), Y(s2[0][1]))
    g.quadraticCurveTo(X(s2[1][0]), Y(s2[1][1]), X(s2[2][0]), Y(s2[2][1]))
    g.lineWidth = small ? 1.5 : 2.2; g.strokeStyle = C.ink3; g.globalAlpha = 0.55; g.stroke()
  }
  // Cerebellum folds — same treatment, tighter.
  for (let i = 0; i < 4; i++) {
    const yy = 0.83 + i * 0.032
    g.beginPath(); g.moveTo(X(0.60), Y(yy)); g.quadraticCurveTo(X(0.72), Y(yy - 0.02), X(0.84), Y(yy))
    g.lineWidth = small ? 1.1 : 1.6; g.strokeStyle = C.ink3; g.globalAlpha = 0.5; g.stroke()
  }
  g.globalAlpha = 1

  // ── axon fibres between regions ──
  g.lineCap = 'round'
  for (const f of B.fibers) {
    const A2 = B.clusters[f.a], B2 = B.clusters[f.b]
    g.strokeStyle = C.ok; g.lineWidth = 0.8; g.globalAlpha = idle ? 0.14 : 0.26
    g.setLineDash([3, 4]); g.lineDashOffset = reduced ? 0 : -(elapsed / 60) % 7
    g.beginPath(); g.moveTo(A2.cx, A2.cy); g.quadraticCurveTo(f.cx, f.cy, B2.cx, B2.cy); g.stroke()
    g.setLineDash([])
  }
  g.globalAlpha = 1

  // ── dendrites inside each region ──
  for (const id of Object.keys(B.clusters)) {
    const cl = B.clusters[id]
    g.strokeStyle = C.line; g.lineWidth = 0.7; g.globalAlpha = 0.7
    g.beginPath()
    for (const [i, j] of cl.links) { g.moveTo(cl.cells[i].x, cl.cells[i].y); g.lineTo(cl.cells[j].x, cl.cells[j].y) }
    g.stroke(); g.globalAlpha = 1
  }

  // ── resting neurons: faintly alive, brighter where a region fires ──
  for (const id of Object.keys(B.clusters)) {
    const cl = B.clusters[id]
    const l = idle ? 0 : (lit[id] || 0)
    for (const c of cl.cells) {
      const twinkle = idle ? 0.12 : 0.22 + 0.18 * (0.5 + 0.5 * Math.sin(secs * (1.1 + c.d) + c.ph))
      // Firing sweeps outward from the centre of the region.
      const dist = Math.hypot(c.x - cl.cx, c.y - cl.cy) / (cl.R || 1)
      const wave = l > 0.02 ? Math.max(0, 1 - Math.abs(dist - (1 - l) * 1.4) * 2.2) * l : 0
      const a = Math.min(1, twinkle + wave)
      if (wave > 0.05) {
        const grd = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.s * 6)
        grd.addColorStop(0, C.ok); grd.addColorStop(1, 'transparent')
        g.globalAlpha = wave * 0.5; g.fillStyle = grd
        g.beginPath(); g.arc(c.x, c.y, c.s * 6, 0, Math.PI * 2); g.fill()
      }
      g.globalAlpha = a
      g.fillStyle = wave > 0.05 ? C.ok : C.ink3
      const rr2 = c.s * (1 + wave * 0.8)
      g.beginPath()
      g.moveTo(c.x, c.y - rr2 * 1.35); g.lineTo(c.x + rr2, c.y); g.lineTo(c.x, c.y + rr2 * 1.35); g.lineTo(c.x - rr2, c.y)
      g.closePath(); g.fill()
      if (wave > 0.3) { g.strokeStyle = C.ok; g.lineWidth = 0.8; g.globalAlpha = wave * 0.6; g.beginPath(); g.arc(c.x, c.y, rr2 * 3.2, 0, Math.PI * 2); g.stroke() }
    }
    g.globalAlpha = 1
  }

  // ── signals: a spike train down the fibre, carrying the real payload ──
  const qp = (t2: number, p0: { x: number; y: number }, c: { x: number; y: number }, p1: { x: number; y: number }) => {
    const u = 1 - t2
    return { x: u * u * p0.x + 2 * u * t2 * c.x + t2 * t2 * p1.x, y: u * u * p0.y + 2 * u * t2 * c.y + t2 * t2 * p1.y }
  }
  if (!idle) {
    for (const e of spikes) {
      const age = now - e.start
      if (age < 0 || age > TRAVEL) continue
      const p = age / TRAVEL
      const ease = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2
      const f = B.fibers.find(fb => (fb.a === e.from && fb.b === e.to) || (fb.a === e.to && fb.b === e.from))
      const A2 = B.clusters[e.from], B2 = B.clusters[e.to]
      if (!A2 || !B2) continue
      const ctrl = f ? { x: f.cx, y: f.cy } : { x: (A2.cx + B2.cx) / 2, y: (A2.cy + B2.cy) / 2 }
      const from = { x: A2.cx, y: A2.cy }, to = { x: B2.cx, y: B2.cy }
      const col = e.tone === 'warn' ? C.warn : e.tone === 'info' ? C.info : C.ok

      // Myelin glow along the travelled part.
      g.strokeStyle = col; g.lineWidth = 2.4; g.globalAlpha = 0.18
      g.beginPath(); g.moveTo(from.x, from.y)
      for (let k = 1; k <= 18; k++) { const q = qp((k / 18) * ease, from, ctrl, to); g.lineTo(q.x, q.y) }
      g.stroke(); g.globalAlpha = 1

      // Spike train — head plus trailing depolarisations.
      for (let s2 = 0; s2 < 5; s2++) {
        const tt = ease - s2 * 0.055
        if (tt <= 0) continue
        const q = qp(tt, from, ctrl, to)
        const fade = (1 - s2 / 5) * (p > 0.92 ? (1 - p) / 0.08 : 1)
        const r = (s2 === 0 ? 3.6 : 2.2) * (small ? 0.8 : 1)
        if (s2 === 0) {
          const grd = g.createRadialGradient(q.x, q.y, 0, q.x, q.y, r * 5)
          grd.addColorStop(0, col); grd.addColorStop(1, 'transparent')
          g.globalAlpha = 0.45 * fade; g.fillStyle = grd
          g.beginPath(); g.arc(q.x, q.y, r * 5, 0, Math.PI * 2); g.fill()
        }
        g.globalAlpha = fade; g.fillStyle = col
        g.beginPath(); g.arc(q.x, q.y, r, 0, Math.PI * 2); g.fill()
      }
      g.globalAlpha = 1

      // The thought itself, riding the spike.
      if (!reduced && !small) {
        const q = qp(ease, from, ctrl, to)
        g.font = `600 10px ${getComputedStyle(document.documentElement).getPropertyValue('--font-mono') || 'monospace'}`
        const tw = g.measureText(e.word).width
        const fade = p < 0.12 ? p / 0.12 : p > 0.86 ? (1 - p) / 0.14 : 1
        g.globalAlpha = fade
        g.fillStyle = C.surface
        g.beginPath(); g.roundRect(q.x - tw / 2 - 6, q.y - 21, tw + 12, 15, 7.5); g.fill()
        g.strokeStyle = col; g.lineWidth = 1; g.stroke()
        g.fillStyle = C.ink; g.textAlign = 'center'
        g.fillText(e.word, q.x, q.y - 10)
        g.globalAlpha = 1
        blockers.push({ x0: q.x - tw / 2 - 6, y0: q.y - 21, x1: q.x + tw / 2 + 6, y1: q.y - 6 })
      }
    }
  }

  // ── region labels: placed last, and only where they actually fit ──
  g.textAlign = 'center'
  const placed: { x0: number; y0: number; x1: number; y1: number }[] = []
  const hits = (b: { x0: number; y0: number; x1: number; y1: number }) =>
    [...blockers, ...placed].some(o => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0)
  const fs = small ? 9 : 10.5
  const order = Object.keys(B.clusters).sort((a, b) => (lit[b] || 0) - (lit[a] || 0))
  for (const id of order) {
    const cl = B.clusters[id]
    const l = idle ? 0 : (lit[id] || 0)
    // A small canvas only names what is firing — eight labels never fit.
    if (small && l < 0.08) continue
    g.font = `${l > 0.15 ? 600 : 400} ${fs}px ${getComputedStyle(document.documentElement).getPropertyValue('--font-ui') || 'sans-serif'}`
    const txt = MIND_NODES[id].label
    const tw = g.measureText(txt).width
    const gap = cl.R + (small ? 8 : 11)
    const spots = [
      { x: cl.cx, y: cl.cy + gap + fs * 0.4 },
      { x: cl.cx, y: cl.cy - gap },
      { x: cl.cx + cl.R + tw / 2 + 6, y: cl.cy + fs * 0.35 },
      { x: cl.cx - cl.R - tw / 2 - 6, y: cl.cy + fs * 0.35 },
    ]
    let spot: { c: { x: number; y: number }; box: { x0: number; y0: number; x1: number; y1: number } } | null = null
    for (const c of spots) {
      const box = { x0: c.x - tw / 2 - 2, y0: c.y - fs, x1: c.x + tw / 2 + 2, y1: c.y + 3 }
      if (box.x0 < 2 || box.x1 > w - 2 || box.y0 < 2 || box.y1 > h - (small ? 2 : 30)) continue
      if (hits(box)) continue
      spot = { c, box }; break
    }
    if (!spot) continue
    placed.push(spot.box)
    g.fillStyle = l > 0.15 ? C.ink : C.ink3
    g.fillText(txt, spot.c.x, spot.c.y)
  }

  // ── activity trace, big canvas only ──
  if (!small && props.big) {
    const energy = Object.values(lit).reduce((a2, b2) => a2 + b2, 0) / 4
    trace.push(idle ? 0.02 : Math.min(1, energy))
    if (trace.length > 140) trace.shift()
    const bh = 26, by = h - 2
    g.strokeStyle = C.ok; g.lineWidth = 1.2; g.globalAlpha = 0.6
    g.beginPath()
    trace.forEach((v, i) => {
      const x = (i / (trace.length - 1)) * w
      const jitter = idle || reduced ? 0 : Math.sin(i * 1.7 + secs * 4) * v * 3
      const y = by - v * bh - jitter
      i ? g.lineTo(x, y) : g.moveTo(x, y)
    })
    g.stroke(); g.globalAlpha = 1
  }
}

function frame(): void {
  draw()
  raf = requestAnimationFrame(frame)
}

onMounted(() => {
  t0 = performance.now()
  if (reduced) {
    // One calm frame, then only when something happens.
    draw()
    const timer = setInterval(draw, 1000)
    onUnmounted(() => clearInterval(timer))
  } else {
    raf = requestAnimationFrame(frame)
  }
})
onUnmounted(() => cancelAnimationFrame(raf))
</script>
