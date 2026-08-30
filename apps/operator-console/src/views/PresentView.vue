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
                {{ progressLine }}{{ presenter.rehearsing ? '' : armedNote }}
              </template>
              <template v-else>
                Running a scenario switches him to Present mode and locks mail, dev tools and screen control.
              </template>
            </div>
          </div>
          <!-- U267: editing what is loaded. "New scenario" opened an EMPTY
               builder and was the only way in, so changing one line meant
               typing the whole talk again. -->
          <button v-if="presentation.status.title && !builderOpen" class="d2-ghost-btn"
                  title="Open this scenario in the builder" @click="editScenario">Edit</button>
          <button v-if="presenting" class="d2-ghost-btn"
                  :title="presenter.rehearsing
                    ? 'Back to the real thing — he speaks and moves again'
                    : 'Walk the whole show with the robot muted: beats fire and you see every line, but nothing is spoken and nothing moves'"
                  @click="toggleRehearsal">
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
            <span class="mono hud-counter">{{ progressLine }}{{ presenter.rehearsing ? '' : elapsed ? ` · ${elapsed} elapsed` : '' }}</span>
          </div>
          <!-- U267: rehearsal is a real state in the brain now, and it changes
               what the room experiences, so it says so where it cannot be
               missed rather than as a word in a counter. -->
          <div v-if="presenter.rehearsing" class="hud-rehearsal">
            <strong>Rehearsal</strong> — beats fire and you see every line here,
            but he stays silent and still. The room hears nothing.
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
              <p class="hud-next">{{ nextCueLine }}</p>
            </div>
            <div class="hud-transport">
              <!-- U267: this button only ever fires HAND-ADVANCED beats. When
                   the next one waits for a slide or a word it does nothing,
                   silently — which is why "should be triggered automatically"
                   and "do i need to advance beat?" were the same question. -->
              <button class="d2-ghost-btn" :title="advanceHint"
                      :disabled="presentation.busy || !hasManualBeats"
                      @click="presentation.next()">Advance beat ⏭</button>
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
        <ScenarioBuilder v-if="builderOpen" ref="builderRef" class="builder" @start="startScenario" />

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
            <span class="mono beat-cue" :class="b.kind">{{ b.cue }}</span>
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

      <!-- ═══ U265: the overlay — him on the projector ═══ -->
      <div class="aside-field">
        <div class="aside-k">Overlay</div>
        <div class="aside-v ov-help">
          His character and subtitles of what he says, drawn over your slides.
          The window is click-through — your clicker keeps working.
        </div>
        <label class="ov-row">
          <span>Who is this screen for?</span>
          <select v-model="overlayMode" class="d2-field" aria-label="Overlay mode" @change="saveOverlayPrefs">
            <option value="audience">the room — character + subtitles only</option>
            <option value="presenter">me — adds cues, timing and warnings</option>
          </select>
        </label>
        <label v-if="overlayDisplays.length > 1" class="ov-row">
          <span>On which display?</span>
          <select v-model.number="overlayDisplay" class="d2-field" aria-label="Overlay display" @change="saveOverlayPrefs">
            <option v-for="d in overlayDisplays" :key="d.id" :value="d.id">
              {{ d.label }}{{ d.primary ? ' (this one)' : '' }} · {{ d.width }}×{{ d.height }}
            </option>
          </select>
        </label>
        <div class="ov-actions">
          <button class="d2-primary-btn" :disabled="overlayShown" @click="showOverlay">
            {{ isElectron ? 'Show overlay' : 'Open overlay window' }}
          </button>
          <!-- U266: Hide is ALWAYS here. It used to appear only while this view
               believed the overlay was up, and that belief resets every time the
               view is re-created — leaving a live overlay on the beamer with no
               button anywhere to take it down. A Hide that hides nothing costs
               nothing; an overlay you cannot close costs a talk. -->
          <button class="d2-ghost-btn" @click="hideOverlay">Hide</button>
        </div>
        <p v-if="!isElectron" class="ov-note">
          In a browser this opens a normal window (drag it to the beamer and
          press F11). The see-through, click-through version needs the desktop app.
        </p>
      </div>
    </aside>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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

// ── U265: the overlay ───────────────────────────────────────────────────────
// The setting is "who may see this screen", not "window or fullscreen" — the
// technical shape follows from the answer. Electron draws it transparent and
// click-through on the chosen display; a browser gets a plain window as the
// honest fallback (drag to the beamer, F11).
interface OverlayApi {
  displays: () => Promise<{ id: number; label: string; primary: boolean; width: number; height: number }[]>
  show: (opts: { mode: string; displayId: number | null; size?: number }) => Promise<{ shown: boolean }>
  hide: () => Promise<{ shown: boolean }>
  /** U266: added later — an older desktop shell will not have it. */
  state?: () => Promise<{ shown: boolean; mode?: string; displayId?: number | null }>
}
const overlayApi = (window as never as { aura?: { presentOverlay?: OverlayApi } })
  .aura?.presentOverlay
const isElectron = !!overlayApi

const overlayMode = ref<'audience' | 'presenter'>('audience')
const overlayDisplay = ref<number | null>(null)
const overlayDisplays = ref<{ id: number; label: string; primary: boolean; width: number; height: number }[]>([])
const overlayShown = ref(false)
let overlayWindow: Window | null = null      // the browser fallback

function saveOverlayPrefs(): void {
  try {
    localStorage.setItem('aura-overlay', JSON.stringify({
      mode: overlayMode.value, display: overlayDisplay.value,
    }))
  } catch { /* session-only */ }
}

async function showOverlay(): Promise<void> {
  if (overlayApi) {
    await overlayApi.show({ mode: overlayMode.value, displayId: overlayDisplay.value })
    overlayShown.value = true
    return
  }
  const url = `${location.origin}${location.pathname}#overlay?mode=${overlayMode.value}`
  overlayWindow = window.open(url, 'aura-overlay', 'width=1280,height=720')
  overlayShown.value = overlayWindow != null
}

async function hideOverlay(): Promise<void> {
  if (overlayApi) await overlayApi.hide()
  // U266: the browser fallback loses its handle the same way — re-opening the
  // window by NAME hands back the existing one, which can then be closed.
  const win = overlayWindow ?? window.open('', 'aura-overlay')
  try { win?.close() } catch { /* already gone */ }
  overlayWindow = null
  overlayShown.value = false
}

/** U266: adopt whatever is really on the beamer, so a re-created view offers
 *  the right button instead of a confident lie. */
async function syncOverlayState(): Promise<void> {
  if (!overlayApi?.state) return
  try {
    const s = await overlayApi.state()
    overlayShown.value = !!s?.shown
    if (s?.shown) {
      if (s.mode === 'presenter' || s.mode === 'audience') overlayMode.value = s.mode
      if (typeof s.displayId === 'number') overlayDisplay.value = s.displayId
    }
  } catch { /* older shell: leave the local guess */ }
}

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
  // U266: "waiting" presumes he is able to look. When he is not, waiting is
  // not what is happening and telling the presenter to press F5 again is the
  // worst possible advice — they already did, twice.
  if (st.slides_blocker) return 'He cannot see your slides'
  if (st.slides_state === 'waiting') return 'Waiting for your slideshow'
  return 'Manual - advance with the beat button'
})

const slidesDetail = computed(() => {
  const st = presentation.status
  if (st.slides_state === 'live') {
    const where = st.slide_total ? `slide ${st.slide} of ${st.slide_total}` : `slide ${st.slide}`
    return `${st.deck || 'your deck'} - ${where}`
  }
  if (st.slides_blocker) return st.slides_blocker
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

// ── U267: what has actually happened, and what he is actually waiting for ──
/** "beat 2 of 1" was the old line: the numerator counted hand-advanced beats
 *  and the denominator counted them too, so firing the only manual beat in a
 *  scenario put the position past the end. Both halves describe the WHOLE
 *  show now, and finishing says so instead of counting past itself. */
const progressLine = computed(() => {
  const prefix = presenter.rehearsing ? 'rehearsing · ' : ''
  if (!presenter.total) return `${prefix}no beats`
  if (presenter.finished) return `${prefix}all ${presenter.total} beats done`
  return `${prefix}beat ${presenter.done + 1} of ${presenter.total}`
})

/** The next cue, said as the thing the presenter must DO to reach it. */
const nextCueLine = computed(() => {
  const beat = presenter.nextBeat
  if (!beat) return 'the end — he bows and hands back to you'
  if (beat.kind === 'manual') return `${beat.cue} — he waits for you`
  if (beat.kind === 'keyword') return `${beat.cue} — fires when you say it`
  return `${beat.cue} — fires when you reach it`
})

const hasManualBeats = computed(() =>
  presenter.beats.some(b => b.kind === 'manual'))

const advanceHint = computed(() => hasManualBeats.value
  ? 'Fire the next hand-advanced beat now'
  : 'Every beat in this scenario fires on a slide or a keyword, so there is '
    + 'nothing here to advance by hand — just present your deck.')

const builderOpen = ref(false)
const builderRef = ref<{ loadScenario: (sc: Record<string, unknown>) => void } | null>(null)

// ── Run / end ──────────────────────────────────────────────────────────────
let modeBefore: 'home' | 'work' = 'home'
interface DraftBeat { id?: string; mode?: string; text?: string; motion?: string; trigger?: unknown }

/** The cue a beat waits for, as the builder actually writes it.
 *
 * U266: this is a STRING — "manual", "slide:4", "keyword:Java" — and always
 * was; `ScenarioBuilder.toScenario()` joins it that way and the brain parses
 * it that way. The code here read it as an OBJECT, and `'keyword' in 'manual'`
 * is not a false test, it is a `TypeError: Cannot use 'in' operator to search
 * for 'keyword' in manual`. It threw on the first beat, before the scenario
 * was ever POSTed — so "Start presentation" did precisely nothing, said
 * nothing, and left "No scenario loaded" on screen. Reported twice:
 * "start presentation is not doing anything".
 *
 * There is no vue-tsc step in this app, so the wrong type annotation compiled
 * happily and only ever failed at runtime, in a click handler, in front of a
 * deck. Hence the tolerant read below AND the catch in startScenario.
 */
function triggerOf(b: DraftBeat): string {
  return typeof b.trigger === 'string' ? b.trigger : 'manual'
}
function cueOf(b: DraftBeat, i: number): string {
  const t = triggerOf(b)
  if (t.startsWith('keyword:')) return `“${t.slice('keyword:'.length)}”`
  if (t.startsWith('slide:')) return `Slide ${t.slice('slide:'.length)}`
  // U267: "Beat 3" named the row, not the cue — so a hand-advanced beat gave
  // the presenter no hint that it was waiting for THEM. Asked as "do i need
  // to advance beat? should be triggered automatically."
  void i
  return 'You press Next'
}
/** U267: three cue kinds, not two. Every beat that was not a keyword was
 *  labelled SLIDE — including hand-advanced ones — so a beat that would never
 *  move on its own wore the badge of one that would. */
function kindOf(b: DraftBeat): 'manual' | 'slide' | 'keyword' {
  const t = triggerOf(b)
  if (t.startsWith('keyword:')) return 'keyword'
  if (t.startsWith('slide:')) return 'slide'
  return 'manual'
}

async function startScenario(scenario: object): Promise<void> {
  // U264: do NOT close the builder yet. It sits behind a v-if, so closing it
  // DESTROYS it and every beat typed into it — and closing before the load
  // was accepted meant a validation error (an empty `text` on a speak beat is
  // the easy one) wiped the work and left "No scenario loaded" behind, with
  // the reason scrolled off above. Reported as: "wanneer ik start presentation
  // klik verdwijnt alles".
  try {
    const beats = ((scenario as { beats?: DraftBeat[] }).beats ?? [])
    presenter.setBeats(beats.map((b, i) => ({
      id: b.id ?? `beat-${i + 1}`,
      cue: cueOf(b, i),
      kind: kindOf(b),
      say: b.text ?? '',
      do: b.motion ?? b.mode ?? '',
    })))
    const ok = await presentation.startScenario(scenario)
    if (ok) {
      builderOpen.value = false        // only now: the work is safely loaded
      modeBefore = modeStore.mode === 'present' ? 'home' : modeStore.mode
      await modeStore.setMode('present')
    }
  } catch (err) {
    // U266: a green button that swallows its own crash is the worst outcome
    // of the three — the presenter clicks again, and again, learning nothing.
    // Whatever went wrong, it goes where they are already looking.
    presentation.error = `Could not start: ${(err as Error)?.message ?? err}`
  }
}
async function toggleRun(): Promise<void> {
  if (presenting.value) {
    // U267: rehearsal lives in the brain and dies with the runner, so there
    // is nothing to reset here any more.
    await presentation.stop()
    await modeStore.setMode(modeBefore)
  } else if (presenter.beats.length) {
    // U267: re-running used to REBUILD the scenario out of the display rows —
    // `{id, mode:'speak', text: say}` — which silently threw away every
    // trigger, every topic and every gesture: a deck full of slide cues came
    // back as a pile of hand-advanced speak beats. Ask the brain for the real
    // one instead; fall back to the rows only if it has none.
    builderOpen.value = false
    const real = await presentation.fetchScenario()
    const scenario = real ?? {
      title: presentation.status.title ?? 'Scenario',
      beats: presenter.beats.map(b => ({ id: b.id, mode: 'speak', text: b.say })),
    }
    const ok = await presentation.startScenario(scenario)
    if (ok) await modeStore.setMode('present')
  } else {
    builderOpen.value = true
  }
}

/** U267: edit what is loaded, instead of retyping a talk to change one line.
 *  "New scenario" opened an empty builder and was the only door in. */
async function editScenario(): Promise<void> {
  const scenario = await presentation.fetchScenario()
  builderOpen.value = true
  await nextTick()
  if (scenario) builderRef.value?.loadScenario(scenario)
}

async function toggleRehearsal(): Promise<void> {
  await presentation.setRehearsing(!presenter.rehearsing)
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
  try {
    const saved = JSON.parse(localStorage.getItem('aura-overlay') ?? '{}')
    if (saved.mode === 'presenter' || saved.mode === 'audience') overlayMode.value = saved.mode
    if (typeof saved.display === 'number') overlayDisplay.value = saved.display
  } catch { /* defaults */ }
  overlayApi?.displays().then(d => { overlayDisplays.value = d }).catch(() => {})
  void syncOverlayState()      // U266: the beamer, not this view, is the truth
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
/* U267: the cue column is wider because it now says the cue ("Slide 12",
   "You press Next") rather than the row number ("Beat 3"). */
.beat-cue { font-size: 11.5px; color: var(--ink-3); width: 96px; flex-shrink: 0; padding-top: 2px; }
.beat-cue.manual { color: var(--ink-2); }
.beat-text { flex: 1; min-width: 0; }
.beat-say { font-size: 13.5px; line-height: 1.45; }
.beat-do { font-size: 12px; color: var(--ink-3); margin-top: 3px; }
.beat-kind {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 7px; border-radius: 999px; flex-shrink: 0;
  background: var(--present-wash); color: var(--present);
}
.beat-kind.keyword { background: var(--info-wash); color: var(--info); }
/* U267: a hand-advanced beat used to wear the SLIDE badge, promising it would
   fire on its own. Its own badge, and a quiet one — it is the kind that waits. */
.beat-kind.manual { background: var(--surface-2); color: var(--ink-3); }

.hud-rehearsal {
  margin: 0 12px 10px; padding: 8px 12px; border-radius: 8px;
  background: var(--warn-wash, rgba(200, 150, 20, 0.12));
  color: var(--ink-2); font-size: 12.5px; line-height: 1.45;
}

.present-aside {
  width: 262px; flex-shrink: 0; background: var(--surface);
  border-left: 1px solid var(--line); padding: 14px 16px; overflow-y: auto;
}
.aside-lead { margin: 0 0 14px; font-size: 12.5px; color: var(--ink-2); line-height: 1.5; }
.aside-field { margin-bottom: 12px; }
.ov-help { margin-bottom: 8px; }
.ov-row { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; font-size: 12px; color: var(--ink-3); }
.ov-actions { display: flex; gap: 6px; }
.ov-note { margin: 7px 0 0; font-size: 11.5px; color: var(--ink-3); }
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
