// U375 (audit T7): every owner-state path the shell hands the brain is pinned
// outside the install directory — by test, not by memory.
//
// U177 moved the knowledge store, the faces, the memory DB and the skills out
// of the install directory, because an NSIS update replaces that directory
// wholesale. U327 found the settings U177 had left behind: the mode policy,
// the MCP servers, the connector preferences and the turn traces still
// defaulted to `./data`, which for a packaged app IS the install directory —
// reported as "quiet mode is on and he still talks", because an update had
// reset the file the brain reads. Both fixes live in `brainEnv()` in main.cjs,
// and until this file nothing checked that the list was complete or that a
// later edit had not quietly dropped a line from it.
//
// Like its siblings, this reads main.cjs as text: the module requires
// `electron` at load, so it cannot be imported by plain node. A source-level
// pin is weaker than executing brainEnv(), and it is what catches the U327
// class — a key that is no longer assigned, or assigned a relative default.
//
// Plain node — run with `node apps/desktop/test-brain-env.cjs`.
const assert = require('assert')
const fs = require('fs')
const path = require('path')

const main = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf-8')
const start = main.indexOf('function brainEnv()')
assert.ok(start > 0, 'main.cjs must define brainEnv()')
const body = main.slice(start, main.indexOf('\n}\n', start))

// --- every owner-state path lands under userData, never under the install --
// Each of these has been lost once to an update. The default must be built
// from DATA_DIR / USER_ROOT / ENV_FILE / SKILLS_DIR / SCENARIOS_DIR — the
// roots that live in userData when packaged — never from a relative path.
const OWNER_STATE = {
  AURA_ENV_FILE: /env\.AURA_ENV_FILE\s*=\s*ENV_FILE/,
  KNOWLEDGE_DB_PATH: /env\.KNOWLEDGE_DB_PATH\s*=.*DATA_DIR/,
  RECOGNITION_DB_PATH: /env\.RECOGNITION_DB_PATH\s*=.*DATA_DIR/,
  DATABASE_URL: /env\.DATABASE_URL\s*=.*DATA_DIR/,
  SKILLS_DIR: /env\.SKILLS_DIR\s*=.*SKILLS_DIR/,
  SCENARIOS_DIR: /env\.SCENARIOS_DIR\s*=.*SCENARIOS_DIR/,
  MODE_POLICY_PATH: /env\.MODE_POLICY_PATH\s*=.*DATA_DIR/,
  MCP_SERVERS_PATH: /env\.MCP_SERVERS_PATH\s*=.*DATA_DIR/,
  CONNECTOR_PREFS_PATH: /env\.CONNECTOR_PREFS_PATH\s*=.*DATA_DIR/,
  TURN_TRACE_PATH: /env\.TURN_TRACE_PATH\s*=.*DATA_DIR/,
  GESTURE_MODEL_PATH: /env\.GESTURE_MODEL_PATH\s*=.*DATA_DIR/,
}
for (const [key, pattern] of Object.entries(OWNER_STATE)) {
  assert.ok(pattern.test(body),
    `brainEnv() must pin ${key} under the owner's data directory — it was lost to an update once (U177/U327).`)
  assert.ok(!new RegExp(`env\\.${key}\\s*=\\s*['"]\\./`).test(body),
    `${key} must not default to a relative path; that resolves inside the install directory`)
}
console.log(`ok  ${Object.keys(OWNER_STATE).length} owner-state paths pinned outside the install directory`)

// --- an explicit .env value still wins over every default -------------------
// The `||` is the contract: the wizard's choice beats the shell's default.
for (const key of ['KNOWLEDGE_DB_PATH', 'MODE_POLICY_PATH', 'CONNECTOR_PREFS_PATH']) {
  assert.ok(new RegExp(`env\\.${key}\\s*=\\s*env\\.${key}\\s*\\|\\|`).test(body),
    `${key}: an explicit value from .env must win over the default (env.X = env.X || …)`)
}
console.log('ok  explicit .env values win over the shell defaults')

// --- the desktop is text-first: voice runs on the robot, never in this window
assert.ok(/env\.STT_PROVIDER\s*=\s*'null'/.test(body) && /env\.TTS_PROVIDER\s*=\s*'null'/.test(body),
  'STT/TTS must be forced to null in the desktop shell (U22/U24): a local model provider crashes a laptop without the model files')
console.log('ok  voice providers are forced off in the shell')

// --- U371: the build stamp reaches the brain when the release wrote one -----
assert.ok(/BUILD_COMMIT/.test(body) && /env\.AURA_BUILD_COMMIT/.test(body),
  'brainEnv() must hand the BUILD_COMMIT stamp to the brain as AURA_BUILD_COMMIT (U371), or a packaged app cannot say whether the robot is behind it')
console.log('ok  the build stamp is handed to the brain')

// --- the roots themselves come from userData when packaged ------------------
assert.ok(/const USER_ROOT = IS_PACKAGED \? app\.getPath\('userData'\)/.test(main),
  'USER_ROOT must be userData when packaged — the install directory is replaced by every update (U177)')
assert.ok(/const ENV_FILE = IS_PACKAGED\s*\?\s*path\.join\(USER_ROOT, '\.env'\)/.test(main),
  'the env file must live in userData when packaged')
console.log('ok  the roots live in userData when packaged')
