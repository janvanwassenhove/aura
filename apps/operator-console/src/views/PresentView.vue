<template>
  <main class="present">
    <div class="present-main">
      <div class="present-inner">
        <div class="present-head">
          <h2>Presentations</h2>
          <span class="spacer" />
          <button class="d2-ghost-btn" @click="builderOpen = !builderOpen">{{ builderOpen ? 'Close builder' : 'New scenario' }}</button>
          <button class="d2-ghost-btn" @click="pickYaml">Import YAML</button>
          <input ref="yamlInput" type="file" accept=".yaml,.yml" class="hidden-input" @change="importYaml">
        </div>

        <!-- U263: how this works, in the order you have to do it. The trap
             it removes: nothing said the slideshow has to be RUNNING for
             slide cues to exist, and starting the scenario first used to
             cost every cue for the whole talk, silently. -->
        <!-- They stay up until he is actually FOLLOWING a deck: while the
             status says "waiting", step 2 is precisely what the reader needs.
             They disappear the moment they have been completed. -->
        <ol v-if="!slidesLive" class="how-steps">
          <li :class="{ done: !!presentation.status.title }">
            <strong>Write the scenario</strong> - beats with a cue each:
            <code>manual</code>, <code>slide:4</code> or <code>keyword:Java</code>.
            Use <em>New scenario</em>, or import a YAML file.
          </li>
          <li :class="{ done: slidesLive }">
            <strong>Open your deck and start the slideshow</strong> - actually
            presenting it (F5 in PowerPoint, Play in Keynote), not just having
            the file open. He follows the running show; a deck sitting in edit
            mode gives him nothing to follow.
          </li>
          <li>
            <strong>Then press Run.</strong> He watches from that moment on, and
            keeps waiting if the show is not up yet - so this order is a
            recommendation now, not a trap.
          </li>
          <li>
            <strong>Click through your deck as usual.</strong> He reads the slide
            NUMBER, so any way of advancing works - clicker, arrows, jumping
            ahead. Animations inside one slide do not change the number, so they
            cannot carry a cue.
          </li>
        </ol>

        <!-- Run bar: running a scenario IS switching to Present mode -->
        <div class="run-bar" :class="{ live: presenting }">
          <div class="run-text">
            <div class="run-title">{{ presenting ? `Presenting — ${presentation.status.title ?? 'scenario'}` : (presentation.status.title ?? 'No scenario loaded') }}</div>
            <div class="run-sub">
              <template v-if="presenting">
                {{ presenter.rehearsing
                  ? `Rehearsal: beat ${presenter.beatIdx + 1} of ${presenter.total || '?'} — beats fire, but nothing is sent.`
                  : `Beat ${presenter.beatIdx + 1} of ${presenter.total || '?'}${armedNote}` }}
              </template>
              <template v-else>
                Running a scenario switches him to Present mode and locks mail, dev tools and screen control.
              </template>
            </div>
          </div>
          <button v-if="presenting" class="d2-ghost-btn" @click="presenter.rehearsing = !presenter.rehearsing">
            {{ presenter.rehearsing ? 'Stop rehearsal' : 'Rehearse' }}
          </button>
          <button class="run-btn" :class="{ end: presenting }" :disabled="presentation.busy" @click="toggleRun">
            {{ presenting ? 'End presentation' : 'Run presentation' }}
          </button>
        </div>
        <p v-if="presentation.error" class="present-error">{{ presentation.error }}</p>

        <!-- ═══ Live HUD — everything below derives from ONE beatIdx ═══ -->
        <section v-if="presenting" class="hud">
          <div class="hud-bar">
            <span class="hud-dot" />
            <strong class="hud-live">Live</strong>
            <span class="spacer" />
            <span class="mono hud-counter">beat {{ presenter.beatIdx + 1 }} of {{ presenter.total || '?' }}{{ presenter.rehearsing ? ' · rehearsing' : elapsed ? ` · ${elapsed} elapsed` : '' }}</span>
          </div>
          <div class="hud-body">
            <div v-if="!cameraOff" class="hud-cam">
              <img v-if="camera.frameSrc.value" :src="camera.frameSrc.value" alt="Audience camera" class="hud-cam-img">
              <span class="mono hud-cam-tag">audience</span>
            </div>
            <div class="hud-text">
              <div class="mono hud-label">Saying now</div>
              <p class="hud-saying">{{ presentation.subtitle || presenter.currentBeat?.say || '—' }}</p>
              <p class="hud-doing">{{ presenter.currentBeat?.do || '' }}</p>
              <div class="mono hud-label">Next cue</div>
              <p class="hud-next">{{ presenter.nextBeat ? presenter.nextBeat.cue : 'the end — he bows and hands back to you' }}</p>
            </div>
            <div class="hud-transport">
              <button class="d2-ghost-btn" title="Fire the next beat now" :disabled="presentation.busy" @click="presentation.next()">Advance beat ⏭</button>
              <button class="d2-ghost-btn" title="Cut him off mid-word" @click="pauseRobot">Pause the robot</button>
            </div>
          </div>
          <div class="hud-toggles">
            <button class="d2-mini-toggle" :class="{ on: laptopAudio }" :disabled="!audioSupported"
                    title="Read his lines through this laptop instead of the robot"
                    @click="laptopAudio = !laptopAudio">Laptop audio</button>
            <button class="d2-mini-toggle" :class="{ on: laptopMic }" :disabled="!micSupported"
                    title="Use the laptop microphone for audience keywords"
                    @click="toggleLaptopMic">Laptop mic</button>
            <button class="d2-mini-toggle" :class="{ on: cameraOff }" title="Hide the camera preview"
                    @click="cameraOff = !cameraOff">Camera off</button>
          </div>
        </section>

        <!-- ═══ Builder / beats ═══ -->
        <!-- The one thing a presenter needs at a glance before walking on. -->
        <div v-if="presentation.status.active" class="slides-status" :class="slidesClass">
          <span class="slides-dot" />
          <div class="slides-text">
            <strong>{{ slidesHeadline }}</strong>
            <span class="slides-sub">{{ slidesDetail }}</span>
          </div>
        </div>
        <div v-for="w in (presentation.status.deck_warnings ?? [])" :key="w.kind" class="deck-warning">
          {{ w.message }}
        </div>

        <!-- U264: the reason it did not start belongs where the eyes are —
             next to the button that was just pressed, not at the top of a page
             the builder has scrolled off. -->
        <p v-if="builderOpen && presentation.error" class="present-error builder-error">
          {{ presentation.error }}
        </p>
        <ScenarioBuilder v-if="builderOpen" class="builder" @start="startScenario" />

        <template v-if="presenter.beats.length && !builderOpen">
          <div class="beats-head">
            <h3 class="d2-h3">Beats</h3>
            <span class="spacer" />
            <span class="beats-note">Slide beats fire when you advance the deck · keyword beats when you say the word</span>
          </div>
          <div
            v-for="(b, i) in presenter.beats" :key="b.id"
            class="beat-row" :class="{ current: presenting && i === presenter.beatIdx }"
          >
            <span class="mono beat-cue">{{ b.cue }}</span>
            <div class="beat-text">
              <div class="beat-say">{{ b.say || '—' }}</div>
              <div class="beat-do">{{ b.do }}</div>
            </div>
            <span class="beat-kind" :class="b.kind">{{ b.kind }}</span>
          </div>
        </template>
      </div>
    </div>

    <!-- ═══ Presenter settings aside ═══ -->
    <aside class="present-aside">
      <h3 class="d2-h3">While presenting</h3>
      <p class="aside-lead">Present mode locks mail, dev tools and screen control automatically — those beats cannot fire even if a slide asks for them.</p>
      <div class="aside-field">
        <div class="aside-k">Persona</div>
        <select v-model="presentBehaviourPersona" class="d2-field" aria-label="Presenter persona" @change="saveAsideBehaviour('persona', presentBehaviourPersona)">
          <option v-for="c in personas" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div class="aside-field">
        <div class="aside-k">Voice</div>
        <select v-model="presentBehaviourVoice" class="d2-field" aria-label="Presenter voice" @change="saveAsideBehaviour('voice', presentBehaviourVoice)">
          <option v-for="v in TTS_VOICES" :key="v" :value="v">{{ v }}</option>
        </select>
      </div>
      <div class="aside-field">
        <div class="aside-k">Slide source</div>
          <div class="aside-v">{{ slidesHeadline }}</div>
      </div>
      <div class="aside-field">
        <div class="aside-k">Armed keywords</div>
        <div class="aside-v">{{ (presentation.status.armed_keywords ?? []).join(' · ') || 'none right now' }}</div>
      </div>
    </aside>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ScenarioBuilder from '../components/ScenarioBuilder.vue'
import { BRAIN_URL } from '../lib/endpoints'
import { useCameraFeed } from '../composables/useCameraFeed'
import {
  cancelLaptopSpeech, createMic, laptopAudioSupported, laptopMicSupported, speakOnLaptop,
  type MicController,
} from '../composables/usePresenterAudio'
import { useModeStore } from '../stores/modeStore'
import { usePresentationStore } from '../stores/presentationStore'
import { usePresenterStore } from '../stores/presenterStore'

const modeStore = useModeStore()
const presentation = usePresentationStore()
const presenter = usePresenterStore()
const camera = useCameraFeed()

const TTS_VOICES = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse']

const presenting = computed(() => presentation.status.active)

// U263: where the slideshow stands, in words a presenter can act on. Three
// states, deliberately distinct: "waiting" used to be indistinguishable from
// "no slide cues at all", and that confusion cost a whole talk's worth of cues.
const slidesLive = computed(() => presentation.status.slides_state === 'live')
const slidesClass = computed(() => presentation.status.slides_state ?? 'off')

const slidesHeadline = computed(() => {
  const st = presentation.status
  if (st.slides_state === 'live') {
    return `Following ${st.slides_app === 'keynote' ? 'Keynote' : 'PowerPoint'}`
  }
  if (st.slides_state === 'waiting') return 'Waiting for your slideshow'
  return 'Manual - advance with the beat button'
})

const slidesDetail = computed(() => {
  const st = presentation.status
  if (st.slides_state === 'live') {
    const where = st.slide_total ? `slide ${st.slide} of ${st.slide_total}` : `slide ${st.slide}`
    return `${st.deck || 'your deck'} - ${where}`
  }
  if (st.slides_state === 'waiting') {
    return 'Start presenting your deck (F5 in PowerPoint, Play in Keynote) and '
      + 'he picks it up on his own. Keyword and manual beats already work.'
  }
  return 'No slide cues - keyword and manual beats still work.'
})
const armedNote = computed(() => {
  const armed = presentation.status.armed_keywords ?? []
  return armed.length ? ` · waiting for “${armed[0]}”` : ' · waiting for you to advance'
})

const builderOpen = ref(false)

// ── Run / end ──────────────────────────────────────────────────────────────
let modeBefore: 'home' | 'work' = 'home'
async function startScenario(scenario: object): Promise<void> {
  // U264: do NOT close the builder yet. It sits behind a v-if, so closing it
  // DESTROYS it and every beat typed into it — and closing before the load
  // was accepted meant a validation error (an empty `text` on a speak beat is
  // the easy one) wiped the work and left "No scenario loaded" behind, with
  // the reason scrolled off above. Reported as: "wanneer ik start presentation
  // klik verdwijnt alles".
  const beats = ((scenario as { beats?: { id: string; mode: string; text?: string; motion?: string; trigger?: Record<string, unknown> }[] }).beats ?? [])
  presenter.setBeats(beats.map((b, i) => ({
    id: b.id ?? `beat-${i + 1}`,
    cue: cueOf(b, i),
    kind: b.trigger && 'keyword' in (b.trigger ?? {}) ? 'keyword' : 'slide',
    say: b.text ?? '',
    do: b.motion ?? b.mode ?? '',
  })))
  const ok = await presentation.startScenario(scenario)
  if (ok) {
    builderOpen.value = false          // only now: the work is safely loaded
    modeBefore = modeStore.mode === 'present' ? 'home' : modeStore.mode
    await modeStore.setMode('present')
  }
}
function cueOf(b: { trigger?: Record<string, unknown> }, i: number): string {
  const t = b.trigger ?? {}
  if ('keyword' in t) return `“${t.keyword}”`
  if ('slide' in t) return `Slide ${t.slide}`
  return `Beat ${i + 1}`
}
async function toggleRun(): Promise<void> {
  if (presenting.value) {
    await presentation.stop()
    presenter.rehearsing = false
    await modeStore.setMode(modeBefore)
  } else if (presenter.beats.length) {
    // Re-run the loaded beats.
    builderOpen.value = false
    const ok = await presentation.startScenario({ title: presentation.status.title ?? 'Scenario', beats: presenter.beats.map(b => ({ id: b.id, mode: 'speak', text: b.say })) })
    if (ok) await modeStore.setMode('present')
  } else {
    builderOpen.value = true
  }
}
async function pauseRobot(): Promise<void> {
  await fetch(`${BRAIN_URL}/voice/panic`, { method: 'POST' }).catch(() => {})
}

// ── YAML import ────────────────────────────────────────────────────────────
const yamlInput = ref<HTMLInputElement | null>(null)
function pickYaml(): void { yamlInput.value?.click() }
async function importYaml(e: Event): Promise<void> {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const text = await file.text()
  const ok = await presentation.start(text)
  if (ok) await modeStore.setMode('present')
}

// ── Elapsed clock while live ───────────────────────────────────────────────
const elapsed = ref('')
let startedAt = 0
let clockTimer: ReturnType<typeof setInterval> | undefined
watch(presenting, (live) => {
  if (live) {
    startedAt = Date.now()
    clockTimer = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt) / 1000)
      elapsed.value = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
    }, 1000)
  } else {
    clearInterval(clockTimer)
    elapsed.value = ''
  }
})

// ── Laptop audio / mic (U209) ──────────────────────────────────────────────
const audioSupported = laptopAudioSupported()
const micSupported = laptopMicSupported()
const laptopAudio = ref(false)
const laptopMic = ref(false)
const cameraOff = ref(false)
let mic: MicController | null = null
watch(() => presentation.subtitle, (line) => {
  if (laptopAudio.value && line) void speakOnLaptop(line)
})
watch(laptopAudio, (on) => { if (!on) cancelLaptopSpeech() })
function toggleLaptopMic(): void {
  if (laptopMic.value) {
    mic?.stop(); mic = null; laptopMic.value = false
  } else {
    mic = createMic(text => presentation.pushSpeech(text))
    if (mic) { mic.start(); laptopMic.value = true }
  }
}

// ── Status polling while the view is open ──────────────────────────────────
let pollTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  presentation.fetchStatus()
  pollTimer = setInterval(() => presentation.fetchStatus(), 2500)
  fetchPersonas()
  const b = modeStore.behaviourFor('present')
  if (b) { presentBehaviourPersona.value = b.persona; presentBehaviourVoice.value = b.voice }
})
onUnmounted(() => { clearInterval(pollTimer); mic?.stop(); cancelLaptopSpeech() })

// ── Present-mode behaviour (persona/voice) via the mode policy ─────────────
const personas = ref<{ id: string; name: string }[]>([])
const presentBehaviourPersona = ref('presentation')
const presentBehaviourVoice = ref('alloy')
async function fetchPersonas(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    const data = await r.json()
    personas.value = (data.characters ?? []).map((c: { id: string; display_name?: string }) => ({ id: c.id, name: c.display_name ?? c.id }))
  } catch { personas.value = [] }
  if (!personas.value.some(p => p.id === 'presentation')) personas.value.push({ id: 'presentation', name: 'Presenter' })
}
async function saveAsideBehaviour(key: string, value: string): Promise<void> {
  await modeStore.setBehaviour('present', { [key]: value })
}
</script>

<style scoped>
.present { flex: 1; min-width: 0; display: flex; min-height: 0; }
.mono { font-family: var(--font-mono); }
.spacer { flex: 1; }
.hidden-input { display: none; }

.present-main { flex: 1; min-width: 0; overflow-y: auto; padding: 18px 24px; }
.present-inner { max-width: 820px; }
.present-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.present-head h2 { margin: 0; font-size: 19px; }
.builder-error { margin: 0 0 8px; }
.present-error { margin: 8px 0 0; font-size: 12.5px; color: var(--danger); }

.run-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 14px 16px; border: 1.5px solid var(--line-strong);
  border-radius: 12px; background: var(--surface);
}
.run-bar.live { border-color: var(--present); background: var(--present-wash); }
.run-text { flex: 1; min-width: 200px; }
.run-title { font-size: 13.5px; font-weight: 700; }
.run-sub { font-size: 12.5px; color: var(--ink-2); margin-top: 2px; }
.run-btn {
  padding: 8px 18px; border-radius: 9px; border: none; cursor: pointer;
  font-family: inherit; font-size: 13px; font-weight: 700; flex-shrink: 0;
  background: var(--present); color: #fff;
}
.run-btn.end { background: var(--danger); }

.hud { margin-top: 14px; border: 1.5px solid var(--present); border-radius: 12px; background: var(--surface); overflow: hidden; }
.hud-bar { display: flex; align-items: center; gap: 10px; padding: 9px 14px; background: var(--present); color: #fff; }
.hud-dot { width: 8px; height: 8px; border-radius: 50%; background: #fff; }
.hud-live { font-size: 12.5px; letter-spacing: 0.04em; text-transform: uppercase; }
.hud-counter { font-size: 11.5px; opacity: 0.9; }
.hud-body { display: flex; gap: 14px; padding: 14px 16px; flex-wrap: wrap; }
.hud-cam { width: 150px; aspect-ratio: 4 / 3; border-radius: 10px; background: linear-gradient(160deg, #2b3a30, #141c17); flex-shrink: 0; position: relative; overflow: hidden; }
.hud-cam-img { width: 100%; height: 100%; object-fit: cover; }
.hud-cam-tag {
  position: absolute; left: 7px; bottom: 7px; background: rgba(0, 0, 0, 0.5);
  color: #fff; font-size: 9.5px; padding: 2px 7px; border-radius: 4px;
}
.hud-text { flex: 1; min-width: 220px; }
.hud-label {
  font-size: 10.5px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 5px;
}
.hud-saying { margin: 0 0 4px; font-size: 14.5px; line-height: 1.45; }
.hud-doing { margin: 0 0 12px; font-size: 12px; color: var(--ink-3); }
.hud-next { margin: 0; font-size: 13.5px; color: var(--ink-2); }
.hud-transport { display: flex; flex-direction: column; gap: 6px; flex-shrink: 0; }
.hud-toggles { display: flex; gap: 7px; padding: 0 16px 14px; flex-wrap: wrap; }

.builder { margin-top: 14px; }

.beats-head { display: flex; align-items: center; gap: 10px; margin: 16px 0 9px; }
.beats-note { font-size: 12px; color: var(--ink-3); }
.beat-row {
  display: flex; gap: 12px; align-items: flex-start; padding: 11px 14px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--surface); margin-bottom: 7px;
}
.beat-row.current { border-color: var(--present); background: var(--present-wash); }
.beat-cue { font-size: 11.5px; color: var(--ink-3); width: 62px; flex-shrink: 0; padding-top: 2px; }
.beat-text { flex: 1; min-width: 0; }
.beat-say { font-size: 13.5px; line-height: 1.45; }
.beat-do { font-size: 12px; color: var(--ink-3); margin-top: 3px; }
.beat-kind {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 7px; border-radius: 999px; flex-shrink: 0;
  background: var(--present-wash); color: var(--present);
}
.beat-kind.keyword { background: var(--info-wash); color: var(--info); }

.present-aside {
  width: 262px; flex-shrink: 0; background: var(--surface);
  border-left: 1px solid var(--line); padding: 14px 16px; overflow-y: auto;
}
.aside-lead { margin: 0 0 14px; font-size: 12.5px; color: var(--ink-2); line-height: 1.5; }
.aside-field { margin-bottom: 12px; }
.aside-k { font-size: 11.5px; color: var(--ink-3); margin-bottom: 5px; }
.aside-v { font-size: 12.5px; color: var(--ink-2); }

.how-steps {
  margin: 0 0 14px; padding: 14px 18px 14px 34px; list-style: decimal;
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  font-size: 13px; line-height: 1.5; color: var(--ink-2); max-width: 74ch;
}
.how-steps li { margin: 0 0 7px; }
.how-steps li:last-child { margin-bottom: 0; }
.how-steps li.done { color: var(--ink-3); }
.how-steps li.done strong { text-decoration: line-through; }
.how-steps strong { color: var(--ink); }
.how-steps code {
  font-family: var(--font-mono); font-size: 11.5px; background: var(--sunken);
  padding: 1px 5px; border-radius: 5px;
}

.slides-status {
  display: flex; align-items: flex-start; gap: 10px; margin: 0 0 10px;
  padding: 10px 14px; border-radius: 11px; border: 1px solid var(--line);
  background: var(--surface);
}
.slides-status.live { border-color: var(--ok); background: var(--ok-wash); }
.slides-status.waiting { border-color: var(--warn); background: var(--warn-wash); }
.slides-dot {
  width: 9px; height: 9px; border-radius: 50%; margin-top: 5px; flex-shrink: 0;
  background: var(--ink-3);
}
.slides-status.live .slides-dot { background: var(--ok); }
.slides-status.waiting .slides-dot { background: var(--warn); }
.slides-text { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.slides-sub { font-size: 12px; color: var(--ink-2); }

.deck-warning {
  margin: 0 0 10px; padding: 10px 14px; border-radius: 11px;
  border: 1.5px solid var(--warn); background: var(--warn-wash);
  color: var(--ink); font-size: 12.5px; max-width: 74ch;
}
</style>
