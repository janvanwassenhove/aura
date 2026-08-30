<template>
  <div class="wizard" role="dialog" aria-label="Set up AURA">
    <!-- ═══ Stepper: jump freely between steps ═══ -->
    <aside class="stepper">
      <div class="stepper-brand">
        <span class="stepper-mark" v-html="characterStore.current.art(30, 'idle')" />
        <div class="stepper-brand-text">
          <div class="stepper-title">Set up AURA</div>
          <div class="mono stepper-progress">Step {{ step }} of 7</div>
        </div>
      </div>
      <button
        v-for="(st, i) in STEPS" :key="st.title"
        class="step-item" :class="{ active: step === i + 1 }"
        @click="step = i + 1"
      >
        <span class="step-num" :class="{ done: step > i + 1, active: step === i + 1 }">{{ step > i + 1 ? '✓' : i + 1 }}</span>
        <span class="step-text">
          <span class="step-title" :class="{ active: step === i + 1 }">{{ st.title }}</span>
          <span class="step-sub">{{ st.sub }}</span>
        </span>
      </button>
      <div class="stepper-spacer" />
      <p class="stepper-note">You can leave at any point — AURA remembers where you stopped, and every step is repeatable from About.</p>
    </aside>

    <!-- ═══ Step body ═══ -->
    <main class="wizard-main">
      <div class="wizard-scroll">
        <div class="wizard-body">
          <!-- ── 1 · Meet your assistant ── -->
          <template v-if="step === 1">
            <h1 class="w-h1">Meet your assistant</h1>
            <p class="w-lead">AURA is a brain that runs on this laptop. A robot is optional — it gives the brain a face, a voice and a camera, but everything works without one.</p>

            <div class="w-fields">
              <label class="w-field">
                <span class="w-label">What is he called?</span>
                <input v-model="name" maxlength="24" aria-label="Assistant name" class="d2-field">
                <span class="w-hint">Used in greetings, the wake word and the header.</span>
              </label>
              <label class="w-field">
                <span class="w-label">Reply language</span>
                <select v-model="language" aria-label="Reply language" class="d2-field">
                  <option value="auto">Automatic — match the speaker</option>
                  <option value="nl">Nederlands</option>
                  <option value="en">English</option>
                  <option value="fr">Français</option>
                </select>
                <span class="w-hint">Automatic answers each person in the language they used.</span>
              </label>
            </div>

            <div class="w-warnbox">
              <TriangleAlert :size="17" class="w-warn-icon" />
              <div>
                <h2 class="w-warnbox-title">Correction to the printed guide</h2>
                <p class="w-warnbox-body">The manual's sync line is wrong. Use the one below — this is the only place it matters, and it is already correct here.</p>
                <div class="w-cmds">
                  <div class="mono w-cmd wrong">aura sync --from robot --all</div>
                  <div class="mono w-cmd right">
                    <span class="w-cmd-text">aura sync --target robot --profile default</span>
                    <button title="Copy" class="w-copy" @click="copyCmd"><Copy :size="14" /></button>
                  </div>
                </div>
                <p class="w-warnbox-foot">You will not need to type it: the wizard runs the right command for you in step 3.</p>
              </div>
            </div>

            <h2 class="w-h2">What this takes</h2>
            <div v-for="i in INTRO" :key="i.title" class="w-intro-row">
              <span class="w-intro-icon" :style="{ background: i.wash, color: i.color }"><component :is="i.icon" :size="18" /></span>
              <div class="w-intro-text">
                <div class="w-intro-title">{{ i.title }}</div>
                <div class="w-intro-body">{{ i.body }}</div>
              </div>
              <span class="spacer" />
              <span class="mono w-intro-time">{{ i.time }}</span>
            </div>
          </template>

          <!-- ── 2 · Find the robot, honestly ── -->
          <template v-else-if="step === 2">
            <h1 class="w-h1">Is there a robot on this network?</h1>
            <p class="w-lead">AURA listens for a Reachy Mini announcing itself. Here is exactly what it found, and what it means.</p>

            <div class="scan-box" :class="{ found: robotFound }">
              <span class="scan-icon" :class="{ found: robotFound }">
                <LoaderCircle v-if="setup.discovering" :size="18" class="spin" />
                <Check v-else-if="robotFound" :size="18" />
                <Search v-else :size="18" />
              </span>
              <div class="scan-text">
                <div class="scan-title">{{ scanTitle }}</div>
                <div class="scan-sub">{{ scanSub }}</div>
              </div>
              <button class="d2-ghost-btn" :disabled="setup.discovering" @click="setup.discover()">Scan again</button>
            </div>

            <template v-if="robotFound">
              <h2 class="w-h2">Found on your network</h2>
              <button v-for="f in okRobots" :key="f.url" class="found-row" :class="{ chosen: robotUrl === f.url }" @click="robotUrl = f.url">
                <span class="mono found-url">{{ f.url }}</span>
                <span class="found-meta">{{ f.mode ?? 'idle' }}{{ batteryNote(f) }}</span>
              </button>
            </template>

            <template v-else>
              <h2 class="w-h2">Why nothing shows up</h2>
              <p class="w-body">Three things have to be true before a robot can appear. Check them in this order — most setups fail at the second.</p>
              <div v-for="(p, i) in PRECONDITIONS" :key="p.title" class="precond">
                <span class="precond-num">{{ i + 1 }}</span>
                <div class="precond-text">
                  <div class="precond-title">{{ p.title }}</div>
                  <div class="precond-body">{{ p.body }}</div>
                  <div class="mono precond-check">{{ p.check }}</div>
                </div>
                <span class="precond-state" :class="p.stateClass">{{ p.state }}</span>
              </div>

              <h2 class="w-h2">Know the address? Type it</h2>
              <div class="addr-row">
                <input v-model="robotUrl" placeholder="http://192.168.1.42:8001  ·  or reachy.local" aria-label="Robot address" class="mono d2-field addr-input">
                <button class="w-secondary" :disabled="testingRobot" @click="doTestRobot">{{ testingRobot ? 'Testing…' : 'Test' }}</button>
              </div>
              <p v-if="robotResult" class="w-result" :class="{ ok: robotResult.ok }">
                {{ robotResult.ok ? `Connected — ${robotResult.mode ?? 'idle'}${batteryNote(robotResult)}` : `Not reachable (${robotResult.error})` }}
              </p>
              <p v-else class="w-hint">A successful test reports the robot's mode, and its battery if the firmware measures one.</p>
            </template>

            <!-- Continuing without a robot is a real choice, sized like one -->
            <div class="choice-row">
              <button class="w-primary" @click="robotFound || robotResult?.ok ? nextStep() : setup.discover()">
                {{ robotFound || robotResult?.ok ? 'Use this robot' : 'I fixed something — scan again' }}
              </button>
              <button class="equal-choice" @click="skipRobot">
                <span class="equal-title">Continue without a robot</span>
                <span class="equal-sub">Chat, memory, skills and connections all work. Add the robot whenever it arrives — nothing has to be redone.</span>
              </button>
            </div>
          </template>

          <!-- ── 3 · Install on the robot ── -->
          <template v-else-if="step === 3">
            <h1 class="w-h1">Install AURA on the robot</h1>
            <p class="w-lead">No terminal, no SD card. AURA copies itself over, starts the service and verifies it answers — with your approval for each thing it changes.</p>

            <h2 class="w-h2">What will happen</h2>
            <div v-for="i in INSTALL_STEPS" :key="i.title" class="install-row">
              <span class="install-dot" :class="i.safe ? 'safe' : ''" />
              <div class="install-text">
                <div class="install-title">{{ i.title }}</div>
                <div class="mono install-detail">{{ i.detail }}</div>
              </div>
              <span class="install-tag" :class="i.safe ? 'safe' : ''">{{ i.safe ? 'safe' : 'needs approval' }}</span>
            </div>

            <div class="selfupdate-box">
              <button class="switch" :class="{ on: selfUpdate }" :aria-pressed="selfUpdate" aria-label="Keep the robot up to date by itself" @click="selfUpdate = !selfUpdate"><span class="knob" /></button>
              <div>
                <div class="selfupdate-title">Keep the robot up to date by itself</div>
                <p class="selfupdate-body">On by default, and on from the very first install — that is the point. The robot checks nightly, installs fixes, and tells you afterwards in Activity. Anything that changes what it may <em>do</em> still asks you first.</p>
              </div>
            </div>

            <div class="choice-row">
              <button class="w-primary" @click="approveInstall">{{ installing ? 'Installing…' : 'Approve & install' }}</button>
              <button class="w-secondary" @click="nextStep">Skip — I will do it later</button>
            </div>
            <p v-if="installNote" class="w-result">{{ installNote }}</p>
          </template>

          <!-- ── 4 · Choose a brain ── -->
          <template v-else-if="step === 4">
            <h1 class="w-h1">Choose a brain</h1>
            <p class="w-lead">He needs one language model to think with. The key is stored on this laptop, encrypted, and never shown again — not even to you.</p>

            <div class="providers">
              <button
                v-for="p in PROVIDERS" :key="p.id"
                class="provider" :class="{ active: provider === p.id }"
                @click="provider = p.id"
              >
                <span class="radio" :class="{ active: provider === p.id }" />
                <span class="provider-text">
                  <span class="provider-name">{{ p.name }}</span>
                  <span class="provider-note">{{ p.note }}</span>
                </span>
                <span v-if="p.badge" class="provider-badge">{{ p.badge }}</span>
              </button>
            </div>

            <label class="w-field key-field">
              <span class="w-label">{{ keyAlreadySet ? 'API key — already set' : 'API key' }}</span>
              <input v-model="apiKey" type="password" :placeholder="keyPlaceholder" aria-label="API key" class="d2-field">
            </label>
            <p class="w-hint">{{ keyAlreadySet ? 'Leave empty to keep the key you already stored for this provider.' : 'Pasted once, encrypted immediately, never displayed again — you will replace it rather than read it.' }}</p>

            <div class="info-box">
              <Info :size="16" class="info-icon" />
              <p>No key yet? OpenRouter has free models that are good enough to finish this setup and try him out. You can swap provider later in Settings › Intelligence without redoing anything.</p>
            </div>
          </template>

          <!-- ── 5 · Hands-free voice ── -->
          <template v-else-if="step === 5">
            <h1 class="w-h1">Hands-free voice</h1>
            <p class="w-lead">With the wake word on, you say his name and he starts listening — through the robot's own microphone, or this laptop's if there is no robot.</p>

            <div class="selfupdate-box" :class="{ off: !wakeOn }">
              <button class="switch" :class="{ on: wakeOn }" :aria-pressed="wakeOn" aria-label="Listen for a wake word" @click="wakeOn = !wakeOn"><span class="knob" /></button>
              <div>
                <div class="selfupdate-title">Listen for a wake word</div>
                <p class="selfupdate-body">Off means he only speaks when you press the microphone button. Nothing is recorded or sent while he waits for the word — the listening happens on the device.</p>
              </div>
            </div>

            <label v-if="wakeOn" class="w-field wake-field">
              <span class="w-label">Wake word</span>
              <input v-model="wakeWord" maxlength="24" aria-label="Wake word" class="d2-field">
              <span class="w-hint">Two or three syllables work best. Short words trigger by accident.</span>
            </label>
          </template>

          <!-- ── 6 · Create you ── -->
          <template v-else-if="step === 6">
            <h1 class="w-h1">Who are you?</h1>
            <p class="w-lead">The first person becomes the owner: the only one who can change what AURA may do. Everything below is stored encrypted on this laptop and never leaves it.</p>

            <div class="you-row">
              <span class="you-avatar">{{ ownerInitials }}</span>
              <div class="you-fields">
                <label class="w-field">
                  <span class="w-label">What should he call you?</span>
                  <input v-model="ownerName" aria-label="Your name" class="d2-field">
                </label>
                <label class="w-field">
                  <span class="w-label">Anything he should know from the start</span>
                  <textarea v-model="ownerNotes" rows="2" aria-label="About you" class="d2-field" placeholder="Keep answers short. I cycle to work. Standup is at 9:30." />
                </label>
              </div>
            </div>

            <h2 class="w-h2">Teach him your face <span class="w-h2-opt">optional</span></h2>
            <div class="face-box">
              <div class="face-cam">
                <img v-if="camera.frameSrc.value" :src="camera.frameSrc.value" alt="Robot camera" class="face-cam-img">
              </div>
              <div class="face-text">
                <p>Four photos, taken here, turned into a maths fingerprint. The photos are discarded; the fingerprint never leaves this laptop and can be deleted in one click.</p>
                <div class="face-actions">
                  <button class="w-secondary" :disabled="teachingFace || !ownerName.trim()" @click="teachFaceNow">{{ teachingFace ? 'Watching…' : 'Take four photos' }}</button>
                  <button class="d2-ghost-btn" @click="faceMsg = ''">Not now</button>
                </div>
                <p v-if="faceMsg" class="w-result">{{ faceMsg }}</p>
              </div>
            </div>

            <h2 class="w-h2">Lock the vault</h2>
            <div v-if="alreadyEncrypted" class="okbox">
              <Check :size="17" class="okbox-icon" />
              <p>Already encrypted on this machine — nothing to do. Change the passphrase later in Settings › Privacy.</p>
            </div>
            <template v-else>
              <p class="w-body">A passphrase encrypts everything he knows about people (AES-256). Face data never leaves this laptop. You can also do this later from Settings › Privacy.</p>
              <div class="pass-row">
                <input v-model="pass1" type="password" placeholder="Passphrase — at least 8 characters" aria-label="Vault passphrase" class="d2-field pass-input">
                <input v-model="pass2" type="password" placeholder="Again" aria-label="Repeat passphrase" class="d2-field pass-input">
              </div>
              <p v-if="passError" class="pass-error">{{ passError }}</p>
              <p class="w-hint">There is no recovery. Forget it and the profiles are gone — which is the point.</p>
            </template>
          </template>

          <!-- ── 7 · Learn the panels ── -->
          <template v-else>
            <h1 class="w-h1">What you are looking at</h1>
            <p class="w-lead">Five things to know, then you are done. All of it is repeatable — nothing here is a one-shot decision.</p>

            <article v-for="t in TOUR" :key="t.title" class="tour-card">
              <span class="w-intro-icon" :style="{ background: t.wash, color: t.color }"><component :is="t.icon" :size="18" /></span>
              <div>
                <h2 class="tour-title">{{ t.title }}</h2>
                <p class="tour-body">{{ t.body }}</p>
                <p v-if="t.extra" class="tour-extra">{{ t.extra }}</p>
              </div>
            </article>

            <div class="recommend-box">
              <Check :size="18" class="okbox-icon" />
              <p>Start in <strong>Home</strong> mode with mail set to “asks first”. Loosen it once you trust him — Modes › Home.</p>
            </div>
          </template>
        </div>
      </div>

      <!-- ═══ Footer nav ═══ -->
      <footer class="wizard-footer">
        <button class="w-secondary" :style="{ visibility: step === 1 ? 'hidden' : 'visible' }" @click="step = Math.max(1, step - 1)">Back</button>
        <span class="spacer" />
        <span class="footer-note">{{ FOOTER_NOTES[step - 1] }}</span>
        <!-- Steps 2 and 3 carry their own deliberate inline alternative — a
             second footer Skip would just repeat it. -->
        <button v-if="step < 7 && step !== 2 && step !== 3" class="w-secondary"
                :title="step === 6 ? 'Set a passphrase later in Settings › Privacy — he works unencrypted until you do' : 'Leave this for later — every step is repeatable from About'"
                @click="nextStep(true)">{{ step === 6 ? 'Later' : 'Skip' }}</button>
        <button class="w-primary" :disabled="busy" @click="nextStep()">
          {{ step === 7 ? `Start talking to ${name || 'AURA'}` : step === 6 ? 'Create me and continue' : 'Continue' }}
        </button>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

/** U270: what to say about the battery, which is usually nothing.
 *
 *  This used to print " · battery 100%" whenever a number came back — and a
 *  number ALWAYS came back, because the Reachy adapter hard-coded 100.0 next
 *  to the comment "SDK exposes no battery reading yet". So the very first
 *  thing a new owner read about their robot was an invented full charge.
 *  Now: a number only when something measured one, and silence otherwise —
 *  a first-run screen is not the place to explain a firmware limitation.
 */
function batteryNote(r: { battery_pct?: number | null }): string {
  return typeof r?.battery_pct === 'number' ? ` · battery ${Math.round(r.battery_pct)}%` : ''
}
import {
  Bot, Check, CircleStop, Copy, Info, Laptop, LoaderCircle, MessageCircle, Search, Shield,
  Sparkles, TriangleAlert, Users,
} from 'lucide-vue-next'
import { BRAIN_URL } from '../lib/endpoints'
import { useCameraFeed } from '../composables/useCameraFeed'
import { useCharacterStore } from '../stores/characterStore'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { usePrefsStore } from '../stores/prefsStore'
import { useSetupStore, type RobotProbe } from '../stores/setupStore'

const emit = defineEmits<{ done: [] }>()

const setup = useSetupStore()
const prefs = usePrefsStore()
const knowledge = useKnowledgeStore()
const characterStore = useCharacterStore()
const camera = useCameraFeed()

const step = ref(1)
const busy = ref(false)

const STEPS = [
  { title: 'Meet your assistant', sub: 'name, language, one correction' },
  { title: 'Find the robot', sub: 'or decide to go without' },
  { title: 'Install on the robot', sub: 'with your approval' },
  { title: 'Choose a brain', sub: 'provider and key' },
  { title: 'Hands-free voice', sub: 'wake word' },
  { title: 'Create you', sub: 'owner, face, vault' },
  { title: 'Learn the panels', sub: 'five things, then done' },
]
const FOOTER_NOTES = [
  'Nothing is changed yet',
  'You can add a robot later',
  'Every action asks before it runs',
  'The key is encrypted the moment you continue',
  'Listening happens on the device',
  'Stored encrypted on this laptop',
  'Repeatable from About',
]

// ── Step 1 ─────────────────────────────────────────────────────────────────
const name = ref('Richie')
const language = ref('auto')
const INTRO = [
  { title: 'This laptop', body: 'The brain runs here. It stays here — nothing is uploaded.', time: 'ready', icon: Laptop, color: 'var(--accent)', wash: 'var(--accent-wash)' },
  { title: 'A robot, if you have one', body: 'Optional. It gives the brain a face, a voice and eyes.', time: '~5 min', icon: Bot, color: 'var(--info)', wash: 'var(--info-wash)' },
  { title: 'Ten quiet minutes', body: 'Mostly reading. You can stop halfway and come back.', time: '~10 min', icon: Sparkles, color: 'var(--ink-2)', wash: 'var(--sunken)' },
]
async function copyCmd(): Promise<void> {
  try { await navigator.clipboard.writeText('aura sync --target robot --profile default') } catch { /* blocked */ }
}

// ── Step 2: the honest scan ────────────────────────────────────────────────
const robotUrl = ref('')
const robotResult = ref<RobotProbe | null>(null)
const testingRobot = ref(false)
const okRobots = computed(() => setup.found.filter(f => f.ok))
const robotFound = computed(() => okRobots.value.length > 0)
const scanTitle = computed(() =>
  setup.discovering ? 'Looking…' : robotFound.value ? 'Reachy Mini found' : 'No robot found on this network')
const scanSub = computed(() =>
  setup.discovering
    ? 'Listening for mDNS announcements and sweeping the local network'
    : robotFound.value
      ? okRobots.value.map(f => f.url).join(' · ')
      : 'That is not a failure — it usually means one of the three things below, and it may simply mean you have no robot yet.')
// In failure-likelihood order; the middle one is where most setups fail.
const PRECONDITIONS = [
  {
    title: 'The robot is on and finished booting',
    body: 'The antennas twitch once when it is ready. From cold that takes about 40 seconds.',
    check: 'Look at the robot, not the screen', state: 'assumed', stateClass: 'ok',
  },
  {
    title: 'Both are on the same network',
    body: 'Not guest wifi, not a different band that isolates clients. This is where most setups fail: laptops on 5 GHz guest cannot see a robot on the 2.4 GHz main network.',
    check: 'Compare the wifi name on the laptop with the one the robot joined', state: 'check this', stateClass: 'warn',
  },
  {
    title: 'The robot is running its own AURA service',
    body: 'A brand-new robot has nothing installed yet — so it cannot announce itself. That is what the next step is for.',
    check: 'Step 3 installs it with your approval', state: 'step 3', stateClass: 'warn',
  },
]
async function doTestRobot(): Promise<void> {
  if (!robotUrl.value.trim()) return
  testingRobot.value = true
  robotResult.value = await setup.testRobot(robotUrl.value.trim())
  testingRobot.value = false
}
function skipRobot(): void { step.value = 4 }

// ── Step 3: install on the robot ───────────────────────────────────────────
const INSTALL_STEPS = [
  { title: 'Copy the AURA service to the robot', detail: 'aura sync --target robot --profile default  ·  ~40 MB over your network', safe: false },
  { title: 'Start it and set it to run at boot', detail: 'systemd unit aura-robot.service · enabled', safe: false },
  { title: 'Check it answers, move the head once', detail: 'handshake + one nod, so you can see it worked', safe: true },
  { title: 'Leave nothing else behind', detail: 'no accounts, no keys, no outbound connections from the robot', safe: true },
]
const selfUpdate = ref(true)
const installing = ref(false)
const installNote = ref('')
async function approveInstall(): Promise<void> {
  installing.value = true
  installNote.value = ''
  // The deploy runs on the laptop side (scripts/deploy_robot.py machinery);
  // surface an honest answer either way rather than pretending.
  try {
    const url = robotUrl.value || okRobots.value[0]?.url || ''
    if (url) await setup.saveConfig({ robot_url: url })
    installNote.value = 'The install runs from the laptop and can take a few minutes. If the robot does not answer afterwards, Robot › Connection shows the diagnosis.'
  } finally {
    installing.value = false
    nextStep()
  }
}

// ── Step 4: brain ──────────────────────────────────────────────────────────
type ProviderId = 'openai' | 'openrouter' | 'gemini'
const provider = ref<ProviderId>('openrouter')
const apiKey = ref('')
const PROVIDERS: { id: ProviderId; name: string; note: string; badge?: string }[] = [
  { id: 'openai', name: 'OpenAI', note: 'GPT models. Paid, needs a key from platform.openai.com.' },
  { id: 'openrouter', name: 'OpenRouter', note: 'One key, many models — including free ones to start with.', badge: 'easiest' },
  { id: 'gemini', name: 'Google Gemini', note: 'Generous free tier, good at vision and screen control.' },
]
const keyAlreadySet = computed(() => {
  const st = setup.status
  if (!st) return false
  return provider.value === 'openai' ? st.openai_key_set
    : provider.value === 'openrouter' ? st.openrouter_key_set : st.gemini_key_set
})
const keyPlaceholder = computed(() =>
  keyAlreadySet.value ? '••••••••••••'
    : provider.value === 'openai' ? 'sk-…' : provider.value === 'gemini' ? 'AIza…' : 'sk-or-…')

// ── Step 5: voice ──────────────────────────────────────────────────────────
const wakeOn = ref(true)
const wakeWord = ref('Richie')

// ── Step 6: create you + vault ─────────────────────────────────────────────
const ownerName = ref('')
const ownerNotes = ref('')
const ownerInitials = computed(() => (ownerName.value.trim() || '?').slice(0, 2).toUpperCase())
const alreadyEncrypted = computed(() => setup.status?.encrypted === true)
const pass1 = ref('')
const pass2 = ref('')
const passError = ref('')
const teachingFace = ref(false)
const faceMsg = ref('')
async function ensureOwner(): Promise<string | null> {
  const n = ownerName.value.trim()
  if (!n) return null
  const id = n.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  await knowledge.upsertPerson(id, n, 'owner')
  if (ownerNotes.value.trim()) await knowledge.addFact(id, 'memory', ownerNotes.value.trim())
  return id
}
async function teachFaceNow(): Promise<void> {
  teachingFace.value = true
  faceMsg.value = 'Look at the robot…'
  const id = await ensureOwner()
  faceMsg.value = id ? await knowledge.teachFace(id) : 'Give yourself a name first.'
  teachingFace.value = false
}

// ── Step 7 ─────────────────────────────────────────────────────────────────
const TOUR = [
  {
    title: 'Talk is where you live',
    body: 'The conversation, with his state above it and today’s context beside it. Type, or hold to talk.',
    extra: 'The three-line icon top-right sets how much detail you see — calm for the kitchen, full for your desk.',
    icon: MessageCircle, color: 'var(--accent)', wash: 'var(--accent-wash)',
  },
  {
    title: 'Modes decide what he may do',
    body: 'Home, Work and Present are not themes — they are boundaries. The chips under the header list exactly what is allowed, what asks first, and what is refused.',
    extra: 'Click that chip row to change any of it. Quiet hours sit next to the modes and mean "never speak first".',
    icon: Shield, color: 'var(--warn)', wash: 'var(--warn-wash)',
  },
  {
    title: 'People is his memory',
    body: 'Everyone he knows, what he remembers about them, and where each fact came from. Delete anything, any time.',
    extra: 'When he cannot see who is talking, he asks — and answers as a guest until you say otherwise.',
    icon: Users, color: 'var(--info)', wash: 'var(--info-wash)',
  },
  {
    title: 'Skills and Robot',
    body: 'Skills are procedures he has learned and what triggers them. Robot is the body: camera, gestures, dances, motion history and the connection.',
    extra: '',
    icon: Sparkles, color: 'var(--present)', wash: 'var(--present-wash)',
  },
  {
    title: 'Stop is always there',
    body: 'Top right, in every mode, at every detail level. It cuts him off mid-word, ends the turn and switches the mic off.',
    extra: 'Nothing he does is irreversible without asking you first — and every ask names the rule that caused it.',
    icon: CircleStop, color: 'var(--danger)', wash: 'var(--danger-wash)',
  },
]

// ── Step transitions: each step saves what it owns ─────────────────────────
async function nextStep(skipped = false): Promise<void> {
  busy.value = true
  try {
    if (!skipped) {
      if (step.value === 1 && name.value.trim()) {
        await prefs.save({ assistant_name: name.value.trim(), language: language.value as never })
      }
      if (step.value === 2) {
        const url = robotResult.value?.ok ? robotResult.value.url : okRobots.value[0]?.url
        if (url) await setup.saveConfig({ robot_url: url })
      }
      if (step.value === 4) {
        const cfg: Record<string, unknown> = { llm_provider: provider.value }
        if (apiKey.value.trim()) cfg[`${provider.value}_api_key`] = apiKey.value.trim()
        await setup.saveConfig(cfg)
        apiKey.value = ''
      }
      if (step.value === 5) {
        await prefs.save({ voice_mode: wakeOn.value ? 'wake_word' : 'off', wake_word: wakeWord.value.trim() || name.value })
      }
      if (step.value === 6) {
        await ensureOwner()
        if (!alreadyEncrypted.value && (pass1.value || pass2.value)) {
          passError.value = ''
          if (pass1.value.length < 8) { passError.value = 'At least 8 characters.'; return }
          if (pass1.value !== pass2.value) { passError.value = 'The two passphrases differ.'; return }
          const ok = await knowledge.secure(pass1.value, true)
          if (!ok) { passError.value = knowledge.error ?? 'Encryption failed.'; return }
        }
      }
    }
    if (step.value === 7) {
      await setup.finish()
      emit('done')
      return
    }
    step.value = Math.min(7, step.value + 1)
  } finally { busy.value = false }
}

onMounted(() => {
  setup.fetchStatus()
  setup.discover()
  prefs.fetchPrefs().then(() => {
    if (prefs.assistantName && prefs.assistantName !== 'AURA') name.value = prefs.assistantName
    wakeWord.value = prefs.wakeWord || name.value
  })
})
</script>

<style scoped>
.wizard {
  position: fixed; inset: 0; z-index: 70; display: flex;
  background: var(--bg); color: var(--ink); overflow: hidden;
}
.mono { font-family: var(--font-mono); }
.spacer { flex: 1; }
.spin { animation: spin 1s linear infinite; }

/* ── Stepper ── */
.stepper {
  width: 250px; flex-shrink: 0; background: var(--chrome);
  border-right: 1px solid var(--line);
  display: flex; flex-direction: column; padding: 20px 16px; overflow-y: auto;
}
.stepper-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 22px; }
.stepper-mark { display: flex; animation: breathe 4.6s ease-in-out infinite; }
.stepper-title { font-size: 15px; font-weight: 700; }
.stepper-progress { font-size: 10.5px; color: var(--ink-3); }
.step-item {
  display: flex; align-items: flex-start; gap: 11px; width: 100%;
  padding: 10px 11px; margin-bottom: 3px; border: none; border-radius: 10px;
  cursor: pointer; font-family: inherit; background: transparent; text-align: left;
}
.step-item.active { background: var(--surface); box-shadow: inset 0 0 0 1px var(--line-strong); }
.step-num {
  width: 23px; height: 23px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11.5px; font-weight: 700; background: var(--sunken); color: var(--ink-3);
}
.step-num.active { background: var(--accent-wash); color: var(--accent); }
.step-num.done { background: var(--accent); color: var(--on-accent); }
.step-text { flex: 1; min-width: 0; line-height: 1.25; }
.step-title { display: block; font-size: 13.5px; font-weight: 500; color: var(--ink-2); }
.step-title.active { font-weight: 700; color: var(--ink); }
.step-sub { display: block; font-size: 11px; color: var(--ink-3); margin-top: 2px; }
.stepper-spacer { flex: 1; }
.stepper-note { margin: 16px 0 0; font-size: 11.5px; color: var(--ink-3); line-height: 1.5; }

/* ── Body ── */
.wizard-main { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.wizard-scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 32px 40px 24px; }
.wizard-body { max-width: 680px; }
.w-h1 { margin: 0 0 8px; font-size: 27px; line-height: 1.2; letter-spacing: -0.02em; }
.w-h2 {
  margin: 24px 0 10px; font-size: 12px; font-weight: 700;
  letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3);
}
.w-h2-opt { font-size: 12px; font-weight: 400; color: var(--ink-3); text-transform: none; letter-spacing: 0; }
.w-lead { margin: 0 0 22px; font-size: 15px; color: var(--ink-2); line-height: 1.55; max-width: 62ch; }
.w-body { margin: 0 0 12px; font-size: 13.5px; color: var(--ink-2); }
.w-label { font-size: 12.5px; color: var(--ink-3); }
.w-hint { font-size: 11.5px; color: var(--ink-3); }
.w-fields { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 22px; }
.w-field { flex: 1; min-width: 220px; display: flex; flex-direction: column; gap: 5px; }
.w-result { margin: 6px 0 0; font-size: 13px; color: var(--danger); }
.w-result.ok { color: var(--ok); }

.w-primary {
  padding: 11px 22px; border-radius: 10px; background: var(--accent);
  color: var(--on-accent); border: none; font-size: 14px; font-weight: 700;
  cursor: pointer; font-family: inherit; flex-shrink: 0;
}
.w-secondary {
  padding: 10px 18px; border-radius: 10px; background: var(--surface);
  border: 1.5px solid var(--line-strong); color: var(--ink);
  font-size: 13.5px; font-weight: 600; cursor: pointer; font-family: inherit; flex-shrink: 0;
}

.w-warnbox {
  display: flex; gap: 12px; align-items: flex-start; padding: 15px 17px;
  border: 1.5px solid var(--warn); border-radius: 12px; background: var(--warn-wash); margin-bottom: 22px;
}
.w-warn-icon { color: var(--warn); flex-shrink: 0; margin-top: 2px; }
.w-warnbox-title { margin: 0 0 6px; font-size: 14.5px; }
.w-warnbox-body { margin: 0 0 9px; font-size: 13.5px; color: var(--ink-2); line-height: 1.5; }
.w-cmds { display: flex; flex-direction: column; gap: 6px; }
.w-cmd { font-size: 12px; padding: 8px 11px; border-radius: 8px; background: var(--surface); }
.w-cmd.wrong { color: var(--ink-3); text-decoration: line-through; }
.w-cmd.right { display: flex; align-items: center; gap: 9px; border: 1px solid var(--ok); color: var(--ink); }
.w-cmd-text { flex: 1; min-width: 0; }
.w-copy { background: none; border: none; color: var(--ink-3); cursor: pointer; padding: 0; display: inline-flex; }
.w-warnbox-foot { margin: 9px 0 0; font-size: 12px; color: var(--ink-3); }

.w-intro-row { display: flex; gap: 11px; align-items: flex-start; padding: 11px 0; border-bottom: 1px solid var(--line); }
.w-intro-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.w-intro-title { font-size: 14px; font-weight: 600; }
.w-intro-body { font-size: 13px; color: var(--ink-2); margin-top: 2px; }
.w-intro-time { font-size: 11px; color: var(--ink-3); flex-shrink: 0; padding-top: 3px; }

/* ── Step 2 ── */
.scan-box {
  display: flex; align-items: center; gap: 12px; padding: 16px 18px;
  border: 1.5px solid var(--line-strong); border-radius: 12px; background: var(--surface); margin-bottom: 8px;
}
.scan-box.found { border-color: var(--ok); background: var(--ok-wash); }
.scan-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--sunken); color: var(--ink-3);
}
.scan-icon.found { background: var(--surface); color: var(--ok); }
.scan-text { flex: 1; min-width: 0; }
.scan-title { font-size: 15px; font-weight: 700; }
.scan-sub { font-size: 13px; color: var(--ink-2); margin-top: 2px; }

.precond {
  display: flex; gap: 12px; align-items: flex-start; padding: 13px 15px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--surface); margin-bottom: 8px;
}
.precond-num {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; background: var(--sunken); color: var(--ink-2);
}
.precond-text { flex: 1; min-width: 0; }
.precond-title { font-size: 14px; font-weight: 600; }
.precond-body { font-size: 13px; color: var(--ink-2); margin-top: 3px; line-height: 1.5; }
.precond-check { font-size: 11.5px; color: var(--ink-3); margin-top: 5px; }
.precond-state {
  font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 8px; border-radius: 999px; flex-shrink: 0;
}
.precond-state.ok { background: var(--ok-wash); color: var(--ok); }
.precond-state.warn { background: var(--warn-wash); color: var(--warn); }

.addr-row { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.addr-input { flex: 1; min-width: 200px; width: auto; }
.found-row {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 11px 14px;
  border-radius: 11px; background: var(--surface); border: 1.5px solid var(--ok);
  color: var(--ink); cursor: pointer; font-family: inherit; margin-bottom: 6px;
}
.found-row.chosen { background: var(--ok-wash); }
.found-url { flex: 1; min-width: 0; text-align: left; font-size: 13px; }
.found-meta { font-size: 12px; color: var(--ink-2); }
.choice-row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
.equal-choice {
  flex: 1; min-width: 260px; text-align: left; padding: 13px 18px;
  border-radius: 10px; background: var(--surface); border: 1.5px solid var(--line-strong);
  color: var(--ink); cursor: pointer; font-family: inherit;
}
.equal-title { font-size: 14px; font-weight: 700; }
.equal-sub { display: block; font-size: 12.5px; font-weight: 400; color: var(--ink-2); margin-top: 3px; }

/* ── Step 3 ── */
.install-row {
  display: flex; gap: 12px; align-items: flex-start; padding: 12px 15px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--surface); margin-bottom: 7px;
}
.install-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); flex-shrink: 0; margin-top: 5px; }
.install-dot.safe { background: var(--ok); }
.install-text { flex: 1; min-width: 0; }
.install-title { font-size: 14px; font-weight: 600; }
.install-detail { font-size: 11.5px; color: var(--ink-3); margin-top: 3px; }
.install-tag {
  font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 8px; border-radius: 999px; flex-shrink: 0;
  background: var(--warn-wash); color: var(--warn);
}
.install-tag.safe { background: var(--ok-wash); color: var(--ok); }

.selfupdate-box {
  display: flex; gap: 12px; align-items: flex-start; padding: 15px 17px;
  border: 1.5px solid var(--accent); border-radius: 12px; background: var(--accent-wash); margin: 18px 0 22px;
}
.selfupdate-box.off { border-color: var(--line-strong); background: var(--surface); }
.selfupdate-title { font-size: 14.5px; font-weight: 700; }
.selfupdate-body { margin: 4px 0 0; font-size: 13px; color: var(--ink-2); line-height: 1.5; }
.switch {
  position: relative; width: 44px; height: 25px; border-radius: 999px;
  flex-shrink: 0; cursor: pointer; border: none; padding: 0; background: var(--line-strong);
}
.switch.on { background: var(--accent); }
.knob { position: absolute; top: 3px; left: 3px; width: 19px; height: 19px; border-radius: 50%; background: #fff; transition: left 0.15s; }
.switch.on .knob { left: 22px; }

/* ── Step 4 ── */
.providers { display: flex; flex-direction: column; gap: 9px; margin-bottom: 20px; }
.provider {
  display: flex; align-items: center; gap: 12px; width: 100%; padding: 13px 15px;
  border-radius: 11px; cursor: pointer; font-family: inherit;
  background: var(--surface); border: 1.5px solid var(--line); color: var(--ink);
}
.provider.active { background: var(--accent-wash); border-color: var(--accent); }
.radio {
  width: 17px; height: 17px; border-radius: 50%; flex-shrink: 0;
  border: 2px solid var(--line-strong); background: transparent;
}
.radio.active { border-color: var(--accent); background: var(--accent); box-shadow: inset 0 0 0 3px var(--surface); }
.provider-text { flex: 1; min-width: 0; text-align: left; }
.provider-name { display: block; font-size: 14.5px; font-weight: 600; }
.provider-note { display: block; font-size: 12.5px; color: var(--ink-2); margin-top: 2px; }
.provider-badge {
  font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 2px 8px; border-radius: 999px; background: var(--ok-wash); color: var(--ok); flex-shrink: 0;
}
.key-field { margin-bottom: 8px; max-width: 420px; }
.info-box {
  display: flex; gap: 11px; align-items: flex-start; padding: 13px 15px;
  border: 1px solid var(--line); border-radius: 11px; background: var(--surface); margin-top: 18px;
}
.info-box p { margin: 0; font-size: 12.5px; color: var(--ink-2); line-height: 1.5; }
.info-icon { color: var(--ink-3); flex-shrink: 0; margin-top: 2px; }

/* ── Step 5 / 6 ── */
.wake-field { max-width: 320px; }
.you-row { display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; margin-bottom: 22px; }
.you-avatar {
  width: 76px; height: 76px; border-radius: 50%; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--accent); color: var(--on-accent); font-size: 26px; font-weight: 700;
}
.you-fields { flex: 1; min-width: 240px; display: flex; flex-direction: column; gap: 12px; }
.face-box {
  display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  padding: 14px 16px; border: 1px solid var(--line); border-radius: 12px;
  background: var(--surface); margin-bottom: 22px;
}
.face-cam { width: 120px; aspect-ratio: 4 / 3; border-radius: 9px; background: linear-gradient(160deg, #2b3a30 0%, #1a231d 60%, #121a15 100%); flex-shrink: 0; overflow: hidden; }
.face-cam-img { width: 100%; height: 100%; object-fit: cover; }
.face-text { flex: 1; min-width: 200px; }
.face-text p { margin: 0 0 9px; font-size: 13px; color: var(--ink-2); line-height: 1.5; }
.face-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.okbox {
  display: flex; align-items: center; gap: 11px; padding: 13px 15px;
  border: 1.5px solid var(--ok); border-radius: 11px; background: var(--ok-wash);
}
.okbox p { margin: 0; font-size: 13.5px; color: var(--ink-2); }
.okbox-icon { color: var(--ok); flex-shrink: 0; }
.pass-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.pass-input { flex: 1; min-width: 200px; width: auto; }
.pass-error { margin: 0 0 8px; font-size: 12.5px; font-weight: 600; color: var(--danger); }

/* ── Step 7 ── */
.tour-card {
  display: flex; gap: 14px; align-items: flex-start; padding: 15px 17px;
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface); margin-bottom: 9px;
}
.tour-title { margin: 0 0 4px; font-size: 15px; }
.tour-body { margin: 0; font-size: 13.5px; color: var(--ink-2); line-height: 1.55; }
.tour-extra { margin: 7px 0 0; font-size: 12.5px; color: var(--ink-3); line-height: 1.5; }
.recommend-box {
  display: flex; gap: 12px; align-items: center; padding: 15px 17px;
  border: 1.5px solid var(--accent); border-radius: 12px; background: var(--accent-wash); margin-top: 16px;
}
.recommend-box p { margin: 0; font-size: 13.5px; color: var(--ink-2); }

/* ── Footer ── */
.wizard-footer {
  display: flex; align-items: center; gap: 12px; padding: 14px 40px;
  border-top: 1px solid var(--line); background: var(--chrome); flex-shrink: 0;
}
.footer-note { font-size: 12.5px; color: var(--ink-3); }
</style>
