// U246: the bootstrap must ask for every optional stack the app depends on.
//
// `uv sync` PRUNES anything not requested. The bootstrap asked for the
// `recognition` extra and nothing else, so `computeruse` — which carries
// pyautogui — was removed from the environment on the next launch of any
// install that happened to have it. Everything that operates a real
// application goes through pyautogui: searching a track in Spotify, asking the
// Claude desktop app, typing in Chrome. All three were reported dead on the
// same evening, all three were this.
//
// Same class as U239 on the Pi (`uv sync --package robot-runtime` silently
// dropped the reachy SDK) and the recognition extra before it. Third time, so
// it gets a test rather than another comment.
//
// Plain node — run with `node apps/desktop/test-bootstrap-extras.cjs`.
const assert = require('assert')
const fs = require('fs')
const path = require('path')

const main = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf-8')
const pyproject = fs.readFileSync(
  path.resolve(__dirname, '..', 'aura-brain', 'pyproject.toml'), 'utf-8')

// Every optional extra the packaged app cannot work without, and one import
// name that proves it landed. Add a row here when a capability grows an extra.
const REQUIRED_EXTRAS = [
  { extra: 'recognition', proves: 'insightface', why: 'face recognition' },
  { extra: 'computeruse', proves: 'pyautogui', why: 'use_computer drives the screen' },
]

// --- the extras exist where we think they do -------------------------------
for (const { extra } of REQUIRED_EXTRAS) {
  assert.ok(new RegExp(`^${extra}\\s*=\\s*\\[`, 'm').test(pyproject),
    `aura-brain/pyproject.toml must define the '${extra}' extra`)
}
console.log('ok  every required extra is declared')

// --- the bootstrap asks for all of them ------------------------------------
const syncLines = main.split('\n').filter((l) => l.includes('uv sync'))
assert.ok(syncLines.length > 0, 'main.cjs must run uv sync during bootstrap')
const primary = syncLines.find((l) => REQUIRED_EXTRAS.every(
  ({ extra }) => l.includes(`--extra ${extra}`)))
assert.ok(primary,
  'one uv sync must request EVERY required extra; uv prunes what is not asked '
  + `for.\nsync lines found:\n${syncLines.map((l) => `  ${l.trim()}`).join('\n')}`)
console.log('ok  the primary sync requests every required extra')

// --- a fallback exists, and it does not silently become the normal path ----
assert.ok(syncLines.some((l) => !l.includes('--extra')),
  'a bare `uv sync` fallback must remain, so a wheel that will not build never '
  + 'leaves the app unable to start at all')
console.log('ok  a bare fallback sync remains')

// --- and the "already done" check notices when an extra went missing -------
// Without this the marker file alone says "bootstrapped" and a pruned venv is
// never healed — which is exactly how an install that once had pyautogui kept
// running without it.
for (const { proves, why } of REQUIRED_EXTRAS) {
  assert.ok(main.includes(`'${proves}'`),
    `the bootstrap must check for '${proves}' (${why}) before skipping the sync`)
}
const skipCheck = main.split('\n').find((l) => l.includes('doneRev === BOOTSTRAP_REV'))
assert.ok(skipCheck, 'the bootstrap must have a skip-if-done check')
const skipBlock = main.slice(main.indexOf(skipCheck), main.indexOf(skipCheck) + 200)
assert.ok(skipBlock.includes('recognitionInstalled()') && skipBlock.includes('computerUseInstalled()'),
  'the skip check must verify every extra actually landed, not just the marker')
console.log('ok  the skip-if-done check verifies every extra')

console.log('bootstrap-extras tests passed')
