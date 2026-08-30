<template>
  <div class="ov" :class="{ presenter: mode === 'presenter' }">
    <!-- ═══ Presenter strip (top) — only when this screen is YOURS ═══ -->
    <div v-if="mode === 'presenter' && presentation.status.active" class="ov-cues">
      <div class="ov-cue-row">
        <span class="ov-dot" :class="slidesState" />
        <span class="ov-cue-strong">{{ slidesLine }}</span>
      </div>
      <div v-if="nextCue" class="ov-cue-row">
        <span class="ov-cue-label">next</span>
        <span>{{ nextCue }}</span>
      </div>
      <div v-for="w in presentation.status.deck_warnings ?? []" :key="w.kind" class="ov-warning">
        {{ w.message }}
      </div>
    </div>

    <!-- ═══ The audience layer: him, and what he says ═══ -->
    <div v-if="subtitleVisible" class="ov-subtitle-wrap">
      <div class="ov-subtitle">{{ presentation.subtitle }}</div>
    </div>

    <div class="ov-avatar" :title="character.name">
      <span v-html="character.art(avatarPx, act)" />
    </div>
  </div>
</template>

<script setup lang="ts">
/** U265: the presentation overlay — him on the projector, honestly.
 *
 * One page, two audiences, chosen by `#overlay?mode=`:
 *
 *   audience   the clean layer: the chosen character in a corner, animating on
 *              his REAL speech state, and subtitles of what he says. Subtitles
 *              are not decoration — a robot voice in a hall with bad acoustics
 *              is half intelligible, and this is the half that fixes it.
 *   presenter  the same, plus what only the presenter should see: slide state,
 *              the next cue, deck warnings. On a single-screen setup you would
 *              never show this to the room; on two screens it goes on YOUR
 *              display while `audience` goes to the beamer.
 *
 * It is the console app itself at a different hash — same origin, so the
 * character choice, the brain URL and the WS wiring all come for free, and
 * whatever window shows it (Electron's transparent click-through overlay, or
 * a plain browser window) is somebody else's concern.
 *
 * What he THINKS never renders here. Only what he says. A half-finished
 * thought on a projector in front of a room is a liability, not a feature.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useCharacterStore } from '../stores/characterStore'
import { useEventBusWs } from '../composables/useEventBusWs'
import { usePresentationStore } from '../stores/presentationStore'
import { usePresenterStore } from '../stores/presenterStore'

const presentation = usePresentationStore()
const presenter = usePresenterStore()
const characterStore = useCharacterStore()
const { connect } = useEventBusWs()

// U265: read LIVE on every hash change. A hash-only navigation does not
// reload the page, so reading once at setup left the overlay stuck in
// whatever mode it was first opened with — found when switching a window
// from presenter to audience changed the URL and nothing else.
function readHash(): { mode: 'audience' | 'presenter'; size: number } {
  const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
  return {
    mode: params.get('mode') === 'presenter' ? 'presenter' : 'audience',
    size: Math.max(48, Math.min(220, Number(params.get('size') ?? 120))),
  }
}
const mode = ref<'audience' | 'presenter'>(readHash().mode)
const avatarPx = ref(readHash().size)
function onHashChange(): void {
  const h = readHash()
  mode.value = h.mode
  avatarPx.value = h.size
}

const character = computed(() => characterStore.current)

// ── Speaking state ──────────────────────────────────────────────────────────
// The avatar mouths along for roughly as long as the line takes to say
// (~15 chars/s, the same rate the echo guard uses). robotStore's isSpeaking
// also feeds characterStore.act via the shared WS — this is the fallback for
// beats whose audio state never reaches us.
const speakUntil = ref(0)
const now = ref(Date.now())
let clock: ReturnType<typeof setInterval> | undefined

watch(() => presentation.subtitle, (text) => {
  if (text) speakUntil.value = Date.now() + Math.min(20_000, 1500 + text.length * 66)
})

const act = computed(() =>
  now.value < speakUntil.value ? 'speak' : characterStore.act)

// Subtitles linger a beat after speech so the room can finish reading, then go.
const subtitleVisible = computed(() =>
  !!presentation.subtitle && now.value < speakUntil.value + 2_500)

// ── Presenter extras ────────────────────────────────────────────────────────
const slidesState = computed(() => presentation.status.slides_state ?? 'off')
const slidesLine = computed(() => {
  const st = presentation.status
  if (st.slides_state === 'live') {
    const total = st.slide_total ? ` / ${st.slide_total}` : ''
    return `${st.deck || 'deck'} — slide ${st.slide}${total}`
  }
  if (st.slides_state === 'waiting') return 'waiting for your slideshow (F5 / Play)'
  return 'manual beats only'
})
const nextCue = computed(() => {
  const beat = presenter.nextBeat
  return beat ? `${beat.cue} — ${beat.say || beat.do || beat.id}` : ''
})

// ── Lifecycle ───────────────────────────────────────────────────────────────
let poll: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  connect()
  presentation.fetchStatus()
  poll = setInterval(() => presentation.fetchStatus(), 1_500)
  clock = setInterval(() => { now.value = Date.now() }, 250)
  window.addEventListener('hashchange', onHashChange)
  // The window behind this page is transparent; the page must be too, or the
  // "overlay" is a white sheet over the slides.
  document.documentElement.style.background = 'transparent'
  document.body.style.background = 'transparent'
})
onUnmounted(() => {
  clearInterval(poll); clearInterval(clock)
  window.removeEventListener('hashchange', onHashChange)
})
</script>

<style scoped>
.ov {
  position: fixed; inset: 0; overflow: hidden;
  background: transparent; pointer-events: none;
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}

/* ── Avatar: bottom-right, unobtrusive, breathing on a real state ── */
.ov-avatar {
  position: absolute; right: 28px; bottom: 24px;
  filter: drop-shadow(0 3px 10px rgba(0, 0, 0, 0.45));
}

/* ── Subtitles: the cinema convention, because everyone already knows it ── */
.ov-subtitle-wrap {
  position: absolute; left: 0; right: 0; bottom: 34px;
  display: flex; justify-content: center; padding: 0 12vw;
}
.ov-subtitle {
  max-width: 68ch;
  background: rgba(10, 14, 12, 0.82);
  color: #f4f3ee;
  font-size: clamp(18px, 2.6vh, 30px);
  line-height: 1.35; text-align: center;
  padding: 10px 22px; border-radius: 12px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}

/* ── Presenter strip: top-left, dense, never meant for the room ── */
.ov-cues {
  position: absolute; top: 18px; left: 18px; max-width: 46ch;
  background: rgba(10, 14, 12, 0.86); color: #e9e7df;
  border-radius: 12px; padding: 12px 16px;
  font-size: 14px; line-height: 1.45;
  display: flex; flex-direction: column; gap: 6px;
}
.ov-cue-row { display: flex; align-items: center; gap: 8px; }
.ov-cue-strong { font-weight: 600; }
.ov-cue-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; opacity: 0.6;
}
.ov-dot { width: 9px; height: 9px; border-radius: 50%; background: #8a8578; flex-shrink: 0; }
.ov-dot.live { background: #4ade80; }
.ov-dot.waiting { background: #fbbf24; }
.ov-warning {
  border-top: 1px solid rgba(255, 255, 255, 0.15); padding-top: 6px;
  color: #fcd34d; font-size: 12.5px;
}
</style>
