<template>
  <div class="sb">
    <!-- Saved scenarios: load one, or start a fresh build -->
    <div class="sb-saved" v-if="saved.length">
      <span class="sb-saved-label">Saved:</span>
      <button v-for="s in saved" :key="s.name" class="sb-chip" @click="load(s.name)">
        {{ s.title || s.name }} <span class="sb-chip-n">{{ s.beats }}</span>
        <span class="sb-chip-x" title="Delete" @click.stop="remove(s.name)">×</span>
      </button>
    </div>

    <label class="sb-field">
      <span>Title</span>
      <input v-model="title" class="sb-input" placeholder="My robot talk" />
    </label>

    <!-- U263b: which deck this scenario belongs to. NOT a file to open - he
         never opens anything - just the name to compare against whatever
         slideshow is playing, so opening last month's deck says so instead of
         firing cues on the wrong slides in front of an audience. Optional: no
         name simply means no comparison. -->
    <label class="sb-field">
      <span>Deck name <em class="sb-hint">optional - so he can warn you if the wrong one is on screen</em></span>
      <input v-model="pptx" class="sb-input" placeholder="robot-junior-dev.pptx" />
    </label>

    <!-- U352: where the overlay starts. "Hidden" is for a talk where he should
         appear only at the moments the scenario names; the default is what
         every scenario did before this existed - on screen throughout. -->
    <label class="sb-field">
      <span>On the projector <em class="sb-hint">the overlay has to be switched on in the Present panel either way</em></span>
      <select v-model="scenarioOverlay" class="sb-input sb-scenario-overlay">
        <option value="">shown for the whole talk</option>
        <option value="hidden">starts hidden - beats bring him on</option>
      </select>
    </label>

    <!-- Beats -->
    <div v-for="(b, i) in beats" :key="b._k" class="sb-beat"
         :class="{ 'sb-beat--bad': badBeats.includes(b.id.trim()) }">
      <div class="sb-beat-head">
        <span class="sb-beat-n">{{ i + 1 }}</span>
        <input v-model="b.id" class="sb-input sb-id" placeholder="beat id" />
        <select v-model="b.mode" class="sb-input sb-mode" @change="onMode(b)">
          <option value="speak">💬 Speak (verbatim)</option>
          <option value="improvise">✨ Improvise (topic)</option>
          <option value="chime_in">🎤 Chime in (on keyword)</option>
          <option value="silent">🤫 Silent</option>
        </select>
        <span class="sb-spacer" />
        <button class="sb-mini" title="Move up" :disabled="i === 0" @click="move(i, -1)">↑</button>
        <button class="sb-mini" title="Move down" :disabled="i === beats.length - 1" @click="move(i, 1)">↓</button>
        <button class="sb-mini sb-mini--x" title="Remove" @click="beats.splice(i, 1)">×</button>
      </div>

      <div class="sb-beat-body">
        <!-- Trigger: chime_in is always keyword; others choose -->
        <div class="sb-trigger">
          <span class="sb-lbl">When</span>
          <select v-model="b._tkind" class="sb-input sb-tkind" :disabled="b.mode === 'chime_in'"
                  @change="syncTrigger(b)">
            <!-- U269: "I press Next" read as "when I go to the next slide",
                 which is the opposite of what it does. Asked as: "not clear
                 -> when going to next (clicking mouse/advance in
                 presentation?)". It is the AURA button, not the clicker, so
                 it now names the button. -->
            <option value="manual">I click “Advance beat” in AURA (your clicker will NOT fire it)</option>
            <option value="slide">I reach a slide in my deck (fires by itself)</option>
            <option value="keyword">I say a word out loud (fires by itself)</option>
          </select>
          <input v-if="b._tkind === 'slide'" v-model.number="b._tslide" type="number" min="1"
                 class="sb-input sb-tnum" placeholder="slide #" @input="syncTrigger(b)" />
          <input v-if="b._tkind === 'keyword'" v-model="b._tword" class="sb-input sb-tword"
                 placeholder="keyword" @input="syncTrigger(b)" />
        </div>

        <textarea v-if="b.mode === 'speak'" v-model="b.text" class="sb-input sb-text" rows="2"
                  placeholder="Exactly what the robot says…"></textarea>
        <!-- U349: one line, two characters. The hint is here rather than in a
             tooltip because nobody guesses a markup they have not been shown. -->
        <p v-if="b.mode === 'speak'" class="sb-hint sb-marker-hint">
          Hand the line over mid-sentence with
          <code>[persona:kids_companion]</code>, and back with <code>[persona]</code>.
        </p>
        <template v-if="b.mode === 'improvise' || b.mode === 'chime_in'">
          <input v-model="b.topic" class="sb-input" placeholder="Topic to talk about…" />
          <input v-model="b.guardrails" class="sb-input sb-faint" placeholder="Guardrails (optional, e.g. 'one sentence')" />
        </template>

        <!-- The persona named by a marker is resolved by the brain when the
             beat is spoken; a name that matches nothing falls back to the
             presentation voice ON STAGE. Saying so here is the whole point. -->
        <p v-if="unknownIn(b).length" class="sb-persona-warn">
          No character called {{ unknownIn(b).map(p => `“${p}”`).join(', ') }} —
          that part will come out in the presentation voice.
        </p>

        <!-- U352: deliberately outside the row below, which disappears for a
             silent beat - and a silent beat is the likeliest of all to want
             this. A beat whose whole job is to clear the screen for a live
             demo says nothing and gestures nothing. -->
        <div class="sb-row">
          <label class="sb-lbl">Projector
            <select v-model="b.overlay" class="sb-input sb-overlay"
                    title="Move the overlay from this beat onwards. Leave it alone and it stays as it was.">
              <option value="">leave as it is</option>
              <option value="show">bring him on screen</option>
              <option value="hide">take him off the screen</option>
            </select>
          </label>
        </div>

        <div class="sb-row" v-if="b.mode !== 'silent'">
          <label class="sb-lbl">Voice
            <select v-model="b.persona" class="sb-input sb-persona"
                    title="Which character speaks this beat. Its own voice and speed win over the Present panel's Voice.">
              <option value="">the presentation voice</option>
              <option v-for="p in personas" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </label>
          <label class="sb-lbl">Gesture
            <select v-model="b.gesture" class="sb-input sb-gest">
              <option :value="null">none</option>
              <option value="wave">wave</option><option value="nod">nod</option>
              <option value="tilt">tilt</option><option value="shrug">shrug</option>
            </select>
          </label>
          <label v-if="b.mode === 'improvise' || b.mode === 'chime_in'" class="sb-lbl">Engine
            <select v-model="b.engine" class="sb-input sb-gest" title="Pipeline can use tools (live data); realtime/blank is fast text">
              <option value="">default</option>
              <option value="pipeline">with tools</option>
            </select>
          </label>
        </div>
      </div>
    </div>

    <button class="sb-add" @click="addBeat">+ Add beat</button>

    <p v-if="error" class="sb-err">{{ error }}</p>
    <p v-if="badBeats.length" class="sb-err-hint">
      Marked in red above: {{ badBeats.join(', ') }}.
    </p>

    <div class="sb-actions">
      <input v-model="saveName" class="sb-input sb-savename" placeholder="save as… (name)" />
      <button class="sb-btn" :disabled="busy || !beats.length" @click="save">Save</button>
      <span class="sb-spacer" />
      <button class="sb-btn sb-btn--go" :disabled="busy || !beats.length" @click="emitStart">
        Start presentation
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BRAIN_URL } from '../lib/endpoints'
import { personaIdsIn } from '../lib/vocals'

const emit = defineEmits<{ start: [scenario: object] }>()

interface FormBeat {
  _k: number; id: string; mode: string
  _tkind: string; _tslide: number | null; _tword: string; trigger: string
  text: string; topic: string; guardrails: string; gesture: string | null; engine: string
  /** U349: the character that speaks this beat; '' is the presentation voice. */
  persona: string
  /** U352: '' leave alone | 'show' | 'hide' the projector overlay. */
  overlay: string
  /** U360: no control for these - carried so a round-trip cannot drop them. */
  voice: string; speed: number; pause: number
}

let seq = 0
const title = ref('')
const pptx = ref('')
const scenarioOverlay = ref('')   // U352: '' shown throughout | 'hidden'
const beats = ref<FormBeat[]>([])
const saved = ref<{ name: string; title: string; beats: number }[]>([])
const saveName = ref('')
const busy = ref(false)
const error = ref('')

/** U282: which beats the brain complained about.
 *
 *  The validators name them — "beat 'beat-3': speak mode needs 'text'" — and
 *  with four beats on screen a sentence at the bottom still leaves you
 *  counting cards to find the one that is wrong. The ids in the message point
 *  straight at them.
 */
const badBeats = computed(() =>
  [...error.value.matchAll(/beat '([^']+)'/g)].map(m => m[1]))

function blankBeat(): FormBeat {
  return { _k: seq++, id: `beat-${beats.value.length + 1}`, mode: 'speak',
           _tkind: 'manual', _tslide: 1, _tword: '', trigger: 'manual',
           text: '', topic: '', guardrails: '', gesture: null, engine: '',
           persona: '', overlay: '', voice: '', speed: 0, pause: 0 }
}

/** U349: the characters a beat may be handed to. Loaded from the brain — the
 *  console invents no characters of its own. */
const personas = ref<{ id: string; name: string }[]>([])
async function fetchPersonas(): Promise<void> {
  try {
    const r = await fetch(`${BRAIN_URL}/setup/characters`)
    const data = await r.json()
    personas.value = (data.characters ?? []).map(
      (c: { id: string; display_name?: string }) => ({ id: c.id, name: c.display_name ?? c.id }))
  } catch { personas.value = [] }
}

/** Inline personas in this beat's text that match no known character.
 *
 *  Silent while the list is empty: if the brain could not be reached, every
 *  marker would look wrong, and a warning on every line is noise rather than
 *  information.
 */
function unknownIn(b: FormBeat): string[] {
  if (!personas.value.length || b.mode !== 'speak') return []
  const known = new Set(personas.value.map(p => p.id.toLowerCase()))
  return personaIdsIn(b.text).filter(p => !known.has(p.toLowerCase()))
}
function addBeat() { beats.value.push(blankBeat()) }
function move(i: number, d: number) {
  const j = i + d
  ;[beats.value[i], beats.value[j]] = [beats.value[j], beats.value[i]]
}

// chime_in must use a keyword trigger — enforce it as the user picks the mode,
// so the keyword field appears immediately instead of after another action.
function onMode(b: FormBeat) {
  if (b.mode === 'chime_in') b._tkind = 'keyword'
  syncTrigger(b)
}
function syncTrigger(b: FormBeat) {
  if (b.mode === 'chime_in') b._tkind = 'keyword'
  b.trigger = b._tkind === 'slide' ? `slide:${b._tslide ?? 1}`
    : b._tkind === 'keyword' ? `keyword:${b._tword}` : 'manual'
}

/** Build the structured scenario the backend validates. */
function toScenario(): object {
  return {
    title: title.value,
    pptx: pptx.value.trim(),
    // U352: omitted rather than sent empty - "not mentioned" is the thing that
    // keeps every scenario written before this showing the overlay throughout.
    ...(scenarioOverlay.value ? { overlay: scenarioOverlay.value } : {}),
    beats: beats.value.map(b => {
      if (b.mode === 'chime_in') b._tkind = 'keyword'
      syncTrigger(b)
      const out: Record<string, unknown> = { id: b.id.trim(), trigger: b.trigger, mode: b.mode }
      if (b.mode === 'speak') out.text = b.text
      if (b.mode === 'improvise' || b.mode === 'chime_in') {
        out.topic = b.topic
        if (b.guardrails.trim()) out.guardrails = b.guardrails
        if (b.engine) out.engine = b.engine
      }
      if (b.gesture) out.gesture = b.gesture
      // U349: omitted rather than sent empty - an absent persona means
      // "the presentation voice", which is not a character id.
      if (b.persona) out.persona = b.persona
      if (b.overlay) out.overlay = b.overlay
      // U360: the builder has no control for these, but a scenario loaded
      // here and saved again must come out carrying what it came in with.
      if (b.voice) out.voice = b.voice
      if (b.speed) out.speed = b.speed
      if (b.pause) out.pause = b.pause
      return out
    }),
  }
}

async function fetchSaved() {
  try {
    const r = await fetch(`${BRAIN_URL}/presentation/scenarios`)
    if (r.ok) saved.value = (await r.json()).scenarios ?? []
  } catch { /* offline: no saved list */ }
}

/** Fill the form from a scenario object — from a saved file, or (U267) from
 *  the one that is currently loaded, so it can be edited rather than retyped. */
function loadScenario(sc: Record<string, unknown>, name = '') {
  if (!sc) return
  title.value = String(sc.title ?? '')
  pptx.value = String(sc.pptx ?? '')   // U263b: reloading a scenario keeps its deck
  scenarioOverlay.value = String(sc.overlay ?? '').toLowerCase() === 'hidden' ? 'hidden' : ''
  if (name) saveName.value = name
  beats.value = ((sc.beats as Record<string, unknown>[]) ?? []).map((b) => {
    const trig = String(b.trigger ?? 'manual')
    const kind = trig.split(':')[0]
    return {
      _k: seq++, id: String(b.id ?? ''), mode: String(b.mode ?? 'speak'),
      _tkind: kind, _tslide: kind === 'slide' ? Number(trig.split(':')[1]) : 1,
      _tword: kind === 'keyword' ? trig.split(':').slice(1).join(':') : '',
      trigger: trig, text: String(b.text ?? ''), topic: String(b.topic ?? ''),
      guardrails: String(b.guardrails ?? ''), gesture: (b.gesture as string) ?? null,
      engine: String(b.engine ?? ''), persona: String(b.persona ?? ''),
      overlay: String(b.overlay ?? '').toLowerCase(),
      voice: String(b.voice ?? ''), speed: Number(b.speed ?? 0), pause: Number(b.pause ?? 0),
    }
  })
}

async function load(name: string) {
  try {
    const r = await fetch(`${BRAIN_URL}/presentation/scenarios/${name}`)
    if (!r.ok) return
    const sc = (await r.json()).scenario
    if (sc) loadScenario(sc, name)
  } catch { /* ignore */ }
}

async function remove(name: string) {
  await fetch(`${BRAIN_URL}/presentation/scenarios/${name}`, { method: 'DELETE' })
  await fetchSaved()
}

async function save() {
  busy.value = true; error.value = ''
  try {
    const name = (saveName.value || title.value || 'scenario').trim()
    const r = await fetch(`${BRAIN_URL}/presentation/scenarios/${slug(name)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: toScenario() }),
    })
    const body = await r.json().catch(() => null)
    if (!r.ok) { error.value = body?.error ?? 'Could not save.'; return }
    await fetchSaved()
  } finally { busy.value = false }
}

function emitStart() {
  error.value = ''
  emit('start', toScenario())
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'scenario'
}

onMounted(() => { fetchSaved(); fetchPersonas(); if (!beats.value.length) addBeat() })
defineExpose({ setError: (m: string) => { error.value = m }, loadScenario })
</script>

<style scoped>
.sb { display: flex; flex-direction: column; gap: 0.7rem; }
.sb-saved { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.sb-saved-label { color: var(--text-faint); font-size: 0.78rem; }
.sb-chip {
  display: inline-flex; align-items: center; gap: 0.35rem;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: 999px; padding: 0.2rem 0.6rem; font-size: 0.78rem; cursor: pointer; color: var(--text);
}
.sb-chip:hover { border-color: var(--accent); }
.sb-chip-n { color: var(--text-faint); font-size: 0.7rem; }
.sb-chip-x { color: var(--text-faint); font-weight: 700; }
.sb-chip-x:hover { color: var(--danger, #e5484d); }

.sb-field { display: flex; flex-direction: column; gap: 0.2rem; font-size: 0.78rem; color: var(--text-muted); }
.sb-input {
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); color: var(--text); padding: 0.35rem 0.45rem; font-size: 0.82rem;
}
.sb-faint { font-size: 0.78rem; color: var(--text-muted); }

.sb-beat { border: 1px solid var(--border-strong); border-radius: var(--radius-md); padding: 0.6rem; background: var(--surface-2, rgba(127,127,127,0.05)); }
.sb-beat-head { display: flex; align-items: center; gap: 0.4rem; }
.sb-beat-n { width: 20px; height: 20px; border-radius: 50%; background: var(--accent); color: var(--accent-contrast, #fff); font-size: 0.7rem; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sb-id { width: 6rem; }
.sb-mode { flex: 1; }
.sb-spacer { flex: 1; }
.sb-mini { background: none; border: 1px solid var(--border-strong); border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer; width: 22px; height: 22px; }
.sb-mini:disabled { opacity: 0.4; }
.sb-mini--x:hover { color: var(--danger, #e5484d); border-color: currentColor; }
.sb-beat-body { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.5rem; }
.sb-trigger { display: flex; align-items: center; gap: 0.4rem; }
.sb-lbl { font-size: 0.76rem; color: var(--text-muted); display: inline-flex; align-items: center; gap: 0.3rem; }
.sb-tkind { flex: 0 0 auto; }
.sb-tnum { width: 5rem; }
.sb-tword { flex: 1; }
.sb-text { resize: vertical; font-family: inherit; }
.sb-row { display: flex; gap: 1rem; }
.sb-gest { padding: 0.2rem; }
.sb-persona { padding: 0.2rem; max-width: 12rem; }
.sb-overlay { padding: 0.2rem; max-width: 13rem; }
.sb-hint { font-style: normal; color: var(--text-faint); font-size: 0.72rem; }
.sb-marker-hint { margin: 0; }
.sb-marker-hint code { font-family: var(--font-mono); font-size: 0.7rem; }
/* U349: a warning, not an error - the beat is still perfectly startable. */
.sb-persona-warn { margin: 0; font-size: 0.74rem; color: var(--warn, #d08700); }

.sb-add { align-self: flex-start; background: transparent; border: 1px dashed var(--border-strong); border-radius: var(--radius-md); color: var(--text-muted); padding: 0.35rem 0.8rem; cursor: pointer; font-size: 0.8rem; }
.sb-add:hover { color: var(--text); border-color: var(--accent); }
.sb-err { color: var(--danger, #e5484d); font-size: 0.8rem; margin: 0; }
/* U282: which card to look at, not just what is wrong with it. */
.sb-err-hint { color: var(--danger, #e5484d); font-size: 0.76rem; margin: 0; opacity: 0.85; }
.sb-beat--bad { border-color: var(--danger, #e5484d); }
.sb-actions { display: flex; align-items: center; gap: 0.5rem; }
.sb-savename { width: 10rem; }
.sb-btn { background: transparent; border: 1px solid var(--border-strong); border-radius: var(--radius-md); color: var(--text); padding: 0.4rem 0.9rem; font-size: 0.82rem; cursor: pointer; }
.sb-btn:disabled { opacity: 0.6; }
.sb-btn--go { background: var(--accent); color: var(--accent-contrast, #fff); border-color: var(--accent); font-weight: 600; }
</style>
