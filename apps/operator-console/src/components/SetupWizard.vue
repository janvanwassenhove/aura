<template>
  <div class="wizard-overlay">
    <div class="wizard">
      <header class="wizard-header">
        <Bot :size="22" class="wizard-logo" />
        <h1 class="wizard-title">Set up your assistant</h1>
        <div class="wizard-steps">
          <span v-for="(label, i) in stepLabels" :key="label"
                :class="['wizard-step-dot', { active: i === step, done: i < step }]"
                :title="label" />
        </div>
      </header>

      <!-- Step 0: name + language -->
      <section v-if="step === 0" class="wizard-body">
        <h2 class="step-title">Meet your robot</h2>
        <p class="step-hint">Give your assistant a call name — it's used in greetings, the wake word and the title bar.</p>
        <label class="field-label" for="wz-name">Assistant name</label>
        <input id="wz-name" v-model="name" class="field-input" maxlength="24" placeholder="Richie" />
        <label class="field-label" for="wz-lang">Reply language</label>
        <select id="wz-lang" v-model="language" class="field-input">
          <option value="auto">Automatic (match the speaker)</option>
          <option value="en">English</option>
          <option value="nl">Nederlands</option>
          <option value="fr">Français</option>
        </select>
      </section>

      <!-- Step 1: find the robot -->
      <section v-else-if="step === 1" class="wizard-body">
        <h2 class="step-title">Find your Reachy Mini</h2>
        <p class="step-hint">The robot must be powered on and on the same network.</p>
        <div class="wizard-row">
          <input v-model="robotUrl" class="field-input" placeholder="http://192.168.0.178:8001" />
          <button class="btn-conn btn-ghost" :disabled="testingRobot" @click="doTestRobot">
            <LoaderCircle v-if="testingRobot" :size="13" class="spinner" /> Test
          </button>
        </div>
        <p v-if="robotResult" :class="['step-result', robotResult.ok ? 'ok' : 'bad']">
          <template v-if="robotResult.ok">
            Connected — {{ robotResult.mode }} (battery {{ robotResult.battery_pct }}%)
          </template>
          <template v-else>Not reachable ({{ robotResult.error }})</template>
        </p>
        <button class="btn-conn btn-ghost" :disabled="setup.discovering" @click="setup.discover()">
          <LoaderCircle v-if="setup.discovering" :size="13" class="spinner" />
          {{ setup.discovering ? 'Scanning the network…' : 'Scan my network' }}
        </button>
        <ul v-if="setup.found.length" class="wizard-found">
          <li v-for="f in setup.found" :key="f.url">
            <button class="btn-conn btn-ghost" @click="robotUrl = f.url; doTestRobot()">{{ f.url }}</button>
          </li>
        </ul>
      </section>

      <!-- Step 2: LLM -->
      <section v-else-if="step === 2" class="wizard-body">
        <h2 class="step-title">Choose a brain</h2>
        <p class="step-hint">The assistant needs one LLM provider. Your key is stored locally and never shown again.</p>
        <label class="field-label" for="wz-provider">Provider</label>
        <select id="wz-provider" v-model="llmProvider" class="field-input">
          <option value="openai">OpenAI</option>
          <option value="openrouter">OpenRouter (free models available)</option>
          <option value="gemini">Google Gemini</option>
        </select>
        <label class="field-label" for="wz-key">API key
          <span v-if="keyAlreadySet" class="key-set-note">(already set — leave empty to keep)</span>
        </label>
        <input id="wz-key" v-model="llmKey" type="password" class="field-input" autocomplete="off"
               :placeholder="keyAlreadySet ? '••••••••' : 'sk-…'" />
      </section>

      <!-- Step 3: voice -->
      <section v-else-if="step === 3" class="wizard-body">
        <h2 class="step-title">Hands-free voice</h2>
        <p class="step-hint">With the wake word on, just say “{{ name || 'AURA' }}” to start a conversation via the robot's microphone.</p>
        <label class="wizard-check">
          <input v-model="wakeWordOn" type="checkbox" /> Enable wake-word listening
        </label>
        <template v-if="wakeWordOn">
          <label class="field-label" for="wz-wake">Wake word</label>
          <input id="wz-wake" v-model="wakeWord" class="field-input" maxlength="24" :placeholder="name || 'AURA'" />
        </template>
      </section>

      <!-- Step 4: security -->
      <section v-else-if="step === 4" class="wizard-body">
        <h2 class="step-title">Protect what it learns</h2>
        <template v-if="setup.status?.encrypted">
          <p class="step-result ok">Knowledge is already encrypted on this machine.</p>
        </template>
        <template v-else>
          <p class="step-hint">A passphrase encrypts everything the assistant knows about people (AES-256). Face data never leaves this laptop. You can also do this later via the brain panel.</p>
          <label class="field-label" for="wz-pass">Passphrase (min. 8 characters)</label>
          <input id="wz-pass" v-model="passphrase" type="password" class="field-input" autocomplete="new-password" />
          <p v-if="secureError" class="step-result bad">{{ secureError }}</p>
        </template>
      </section>

      <!-- Step 5: done -->
      <section v-else class="wizard-body">
        <h2 class="step-title">You're all set</h2>
        <p class="step-hint">
          {{ name || 'Your assistant' }} is ready. Add the people it should recognize via the
          brain panel (🧠) — teach faces, names and roles. Everything sensitive keeps asking
          for your approval first.
        </p>
      </section>

      <footer class="wizard-footer">
        <button v-if="step > 0" class="btn-conn btn-ghost" @click="step--">Back</button>
        <span class="wizard-spacer" />
        <button v-if="step < 5 && step !== 4" class="btn-conn btn-ghost" @click="skipStep">Skip</button>
        <button v-if="step === 4 && !setup.status?.encrypted" class="btn-conn btn-ghost" @click="step++">Later</button>
        <button v-if="step < 5" class="btn-conn btn-primary" :disabled="busy" @click="nextStep">
          <LoaderCircle v-if="busy" :size="13" class="spinner" /> Continue
        </button>
        <button v-else class="btn-conn btn-primary" :disabled="busy" @click="finishWizard">
          <LoaderCircle v-if="busy" :size="13" class="spinner" /> Start using {{ name || 'AURA' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Bot, LoaderCircle } from 'lucide-vue-next'
import { useSetupStore, type RobotProbe } from '../stores/setupStore'
import { usePrefsStore, type Language } from '../stores/prefsStore'

const emit = defineEmits<{ (e: 'done'): void }>()

const setup = useSetupStore()
const prefs = usePrefsStore()

const stepLabels = ['Name', 'Robot', 'Brain', 'Voice', 'Security', 'Done']
const step = ref(0)
const busy = ref(false)

// Step state
const name = ref('')
const language = ref<Language>('auto')
const robotUrl = ref('')
const robotResult = ref<RobotProbe | null>(null)
const testingRobot = ref(false)
const llmProvider = ref('openai')
const llmKey = ref('')
const wakeWordOn = ref(false)
const wakeWord = ref('')
const passphrase = ref('')
const secureError = ref('')

const BRAIN_URL =
  import.meta.env.VITE_BRAIN_URL ??
  import.meta.env.VITE_ORCHESTRATOR_URL ??
  'http://localhost:8000'

const keyAlreadySet = computed(() => {
  const s = setup.status
  if (!s) return false
  return { openai: s.openai_key_set, openrouter: s.openrouter_key_set, gemini: s.gemini_key_set }[llmProvider.value] ?? false
})

onMounted(() => {
  const s = setup.status
  if (s) {
    name.value = s.assistant_name !== 'AURA' ? s.assistant_name : ''
    robotUrl.value = s.robot_url
    llmProvider.value = s.llm_provider || 'openai'
    wakeWordOn.value = s.voice_mode === 'wake_word'
  }
})

async function doTestRobot(): Promise<void> {
  testingRobot.value = true
  robotResult.value = null
  try {
    robotResult.value = await setup.testRobot(robotUrl.value)
  } finally {
    testingRobot.value = false
  }
}

function skipStep(): void {
  step.value++
}

async function nextStep(): Promise<void> {
  busy.value = true
  try {
    if (step.value === 0 && name.value.trim()) {
      await prefs.save({ assistant_name: name.value.trim(), language: language.value })
    }
    if (step.value === 1 && robotUrl.value.trim()) {
      await setup.saveConfig({ robot_url: robotUrl.value.trim() })
    }
    if (step.value === 2) {
      const cfg: Record<string, unknown> = { llm_provider: llmProvider.value }
      const keyField = { openai: 'openai_api_key', openrouter: 'openrouter_api_key', gemini: 'gemini_api_key' }[llmProvider.value]
      if (llmKey.value.trim() && keyField) cfg[keyField] = llmKey.value.trim()
      await setup.saveConfig(cfg)
      llmKey.value = ''
    }
    if (step.value === 3) {
      await prefs.save({
        voice_mode: wakeWordOn.value ? 'wake_word' : 'off',
        wake_word: (wakeWord.value || name.value || 'AURA').trim(),
      })
    }
    if (step.value === 4 && !setup.status?.encrypted) {
      secureError.value = ''
      if (passphrase.value.length < 8) {
        secureError.value = 'Passphrase must be at least 8 characters (or choose Later).'
        return
      }
      const resp = await fetch(`${BRAIN_URL}/setup/secure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passphrase: passphrase.value, remember: true }),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        secureError.value = String(data.error ?? `HTTP ${resp.status}`)
        return
      }
      passphrase.value = ''
      await setup.fetchStatus()
    }
    step.value++
  } finally {
    busy.value = false
  }
}

async function finishWizard(): Promise<void> {
  busy.value = true
  try {
    await setup.finish()
    emit('done')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.wizard-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: var(--bg);
  display: flex; align-items: center; justify-content: center;
}
.wizard {
  width: 480px; max-width: 92vw;
  background: var(--surface); border: 1px solid var(--border-strong);
  border-radius: var(--radius-xl); box-shadow: var(--shadow-modal);
  padding: 1.75rem; display: flex; flex-direction: column; gap: 1.1rem;
}
.wizard-header { display: flex; align-items: center; gap: 0.6rem; }
.wizard-logo { color: var(--accent); }
.wizard-title { font-size: 1.05rem; font-weight: 600; margin: 0; flex: 1; }
.wizard-steps { display: flex; gap: 0.35rem; }
.wizard-step-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--surface-2); border: 1px solid var(--border-strong);
}
.wizard-step-dot.active { background: var(--accent); border-color: var(--accent); }
.wizard-step-dot.done { background: var(--ok, #4caf7d); border-color: transparent; }
.wizard-body { display: flex; flex-direction: column; gap: 0.55rem; min-height: 220px; }
.step-title { font-size: 0.95rem; font-weight: 600; margin: 0; }
.step-hint { font-size: 0.8rem; color: var(--text-faint); margin: 0 0 0.3rem; line-height: 1.45; }
.field-label { font-size: 0.75rem; color: var(--text-faint); }
.field-input {
  background: var(--surface-2); border: 1px solid var(--border-strong);
  border-radius: var(--radius-md); color: var(--text);
  padding: 0.45rem 0.6rem; font-size: 0.85rem; width: 100%;
}
.wizard-row { display: flex; gap: 0.5rem; align-items: center; }
.wizard-row .field-input { flex: 1; }
.wizard-found { list-style: none; margin: 0.3rem 0 0; padding: 0; display: flex; flex-direction: column; gap: 0.3rem; }
.wizard-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }
.step-result { font-size: 0.8rem; margin: 0; }
.step-result.ok { color: var(--ok, #4caf7d); }
.step-result.bad { color: var(--danger-text, #e5484d); }
.key-set-note { font-style: italic; }
.wizard-footer { display: flex; gap: 0.5rem; align-items: center; }
.wizard-spacer { flex: 1; }
.btn-conn {
  display: inline-flex; align-items: center; gap: 0.35rem;
  border-radius: var(--radius-md); padding: 0.42rem 0.85rem;
  font-size: 0.8rem; cursor: pointer; border: 1px solid var(--border-strong);
  background: var(--surface-2); color: var(--text);
}
.btn-primary { background: var(--accent); border-color: var(--accent); color: var(--accent-contrast, #fff); }
.btn-ghost { background: transparent; }
.btn-conn:disabled { opacity: 0.55; cursor: default; }
.spinner { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
