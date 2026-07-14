<template>
  <div class="graph-wrap">
    <canvas ref="canvas" class="graph-canvas" @mousemove="onMove" @click="onClick" />
    <div v-if="hover" class="graph-tip" :style="{ left: hover.x + 14 + 'px', top: hover.y + 8 + 'px' }">
      <strong>{{ hover.label }}</strong><span class="tip-kind">{{ hover.kind }}</span>
    </div>
    <p class="graph-legend">
      <span class="lg lg-person" /> person · <span class="lg lg-skill" /> skill ·
      <span class="lg lg-fact" /> fact — click a node to open it
    </p>
  </div>
</template>

<script setup lang="ts">
/** U75: Obsidian-style graph over the brain — people, skills and facts as a
 *  force-directed constellation. Pure canvas, no dependencies. */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface GNode {
  id: string; label: string; kind: 'person' | 'skill' | 'fact'
  x: number; y: number; vx: number; vy: number; r: number
}
interface GEdge { a: number; b: number }

const props = defineProps<{
  people: { person_id: string; display_name: string }[]
  skills: { name: string; description: string; person: string; body: string }[]
  facts: { person_id: string; key: string; value: string }[]
}>()
const emit = defineEmits<{ (e: 'open', kind: string, id: string): void }>()

const canvas = ref<HTMLCanvasElement | null>(null)
const hover = ref<{ x: number; y: number; label: string; kind: string } | null>(null)

let nodes: GNode[] = []
let edges: GEdge[] = []
let raf = 0
let ticks = 0

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
  for (const p of props.people) add(p.person_id, p.display_name, 'person', 16)
  for (const sk of props.skills) add(sk.name, sk.name, 'skill', 9)
  for (const f of props.facts) add(`${f.person_id}:${f.key}`, `${f.key}: ${f.value}`, 'fact', 4)

  const link = (ka: string, kb: string) => {
    const a = idx.get(ka), b = idx.get(kb)
    if (a !== undefined && b !== undefined) edges.push({ a, b })
  }
  for (const sk of props.skills) {
    if (sk.person) link(`skill:${sk.name}`, `person:${sk.person.toLowerCase()}`)
    // [[wikilinks]] in the body connect to people or other skills.
    for (const m of sk.body.matchAll(/\[\[([^\]]+)\]\]/g)) {
      const t = m[1].trim().toLowerCase()
      link(`skill:${sk.name}`, `person:${t}`)
      link(`skill:${sk.name}`, `skill:${t}`)
    }
  }
  for (const f of props.facts) link(`fact:${f.person_id}:${f.key}`.toLowerCase(), `person:${f.person_id.toLowerCase()}`)
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

const COLORS = { person: '#f0b429', skill: '#5cb8e4', fact: '#7ba7c9' }

function draw(): void {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d')!
  const { width: w, height: h } = c
  ctx.clearRect(0, 0, w, h)
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
      ctx.textAlign = 'center'
      ctx.fillText(n.label, n.x, n.y + n.r + 13)
    }
  }
}

function loop(): void {
  const c = canvas.value
  if (!c) return
  if (ticks < 260) { step(c.width, c.height); ticks++ }
  draw()
  raf = requestAnimationFrame(loop)
}

function nodeAt(mx: number, my: number): GNode | null {
  for (const n of nodes) {
    if (Math.hypot(n.x - mx, n.y - my) <= n.r + 4) return n
  }
  return null
}

function onMove(ev: MouseEvent): void {
  const rect = canvas.value!.getBoundingClientRect()
  const n = nodeAt(ev.clientX - rect.left, ev.clientY - rect.top)
  hover.value = n ? { x: ev.clientX - rect.left, y: ev.clientY - rect.top, label: n.label, kind: n.kind } : null
  canvas.value!.style.cursor = n ? 'pointer' : 'default'
}

function onClick(ev: MouseEvent): void {
  const rect = canvas.value!.getBoundingClientRect()
  const n = nodeAt(ev.clientX - rect.left, ev.clientY - rect.top)
  if (n && n.kind !== 'fact') emit('open', n.kind, n.kind === 'person' ? n.id : n.id)
}

function resize(): void {
  const c = canvas.value
  if (!c || !c.parentElement) return
  c.width = c.parentElement.clientWidth
  c.height = Math.max(360, c.parentElement.clientHeight - 30)
  buildGraph(c.width, c.height)
}

watch(() => [props.people, props.skills, props.facts], resize, { deep: true })
onMounted(() => { resize(); loop(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) })
</script>

<style scoped>
.graph-wrap { position: relative; width: 100%; height: 100%; min-height: 380px; }
.graph-canvas {
  width: 100%; height: calc(100% - 26px); display: block;
  background: radial-gradient(ellipse at center, #23272e 0%, #1a1d22 100%);
  border-radius: var(--radius-lg);
}
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
</style>
