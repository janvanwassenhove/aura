// U344: the brain must be launched through the interpreter, and a brain that
// died must say so instead of freezing the splash.
//
// Reported as "it blocks on the splash screen". The log said everything:
//
//   error: Failed to spawn: `aura-brain`
//     Caused by: Access is denied. (os error 5)
//
// A managed Windows machine runs the Defender ASR rule "block executable files
// from running unless they meet a prevalence, age, or trusted list criterion"
// (01443614-CD74-433A-B99E-2ECDC07BFC25). Every console script uv writes into
// .venv\Scripts is a freshly generated, unsigned launcher, so all of them are
// refused — `uvicorn.exe` and `aura-brain.exe` alike, while `python.exe` runs
// fine. Nothing in the app is wrong; the shim is simply not allowed to exist
// as an entry point on a corporate laptop.
//
// The second half is the worse one. The brain was already gone, and the app
// kept polling /health for ninety seconds before reporting a timeout that
// named no cause — constitution XI, a failure that cannot be seen.
//
// Plain node — run with `node apps/desktop/test-brain-launch.cjs`.
const assert = require('assert')
const fs = require('fs')
const path = require('path')

const main = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf-8')

// --- the brain is spawned as a module, never as a generated shim -----------
const spawnLine = main.split('\n').find((l) => l.includes("spawn('uv'"))
assert.ok(spawnLine, 'main.cjs must spawn the brain via uv')
assert.ok(/'python',\s*'-m',\s*'aura_brain'/.test(spawnLine),
  'the brain must start as `python -m aura_brain`; a generated .venv\\Scripts '
  + `launcher is blocked by Defender ASR on managed machines.\nfound: ${spawnLine.trim()}`)
assert.ok(!/'aura-brain'\s*\]/.test(spawnLine),
  'the `aura-brain` console script must not be the entry point')
console.log('ok  the brain starts through the interpreter')

// --- and that module actually exists, with the same entry point ------------
const pkgDir = path.resolve(__dirname, '..', 'aura-brain', 'src', 'aura_brain')
const dunderMain = path.join(pkgDir, '__main__.py')
assert.ok(fs.existsSync(dunderMain),
  '`python -m aura_brain` needs aura_brain/__main__.py')
const entry = fs.readFileSync(dunderMain, 'utf-8')
assert.ok(/from aura_brain\.main import run/.test(entry) && /\brun\(\)/.test(entry),
  '__main__.py must call the same run() the console script did')
const pyproject = fs.readFileSync(
  path.resolve(__dirname, '..', 'aura-brain', 'pyproject.toml'), 'utf-8')
assert.ok(/aura-brain\s*=\s*"aura_brain\.main:run"/.test(pyproject),
  'the console script stays declared — the two paths must not drift apart')
console.log('ok  aura_brain/__main__.py runs the declared entry point')

// --- a dead brain fails the wait at once, carrying the reason --------------
const waitBody = main.slice(main.indexOf('function waitForBrain'),
  main.indexOf('function waitForBrain') + 1200)
assert.ok(waitBody.includes('brainExit !== null'),
  'waitForBrain must give up as soon as the brain process has exited, instead '
  + 'of polling a process that will never answer')
assert.ok(waitBody.includes('brainTail'),
  "the failure must quote the brain's own stderr — a timeout that names no "
  + 'cause is the failure mode constitution XI forbids')
assert.ok(main.includes('brainExit = code'),
  'the exit handler must record the code waitForBrain reads')
assert.ok(main.includes('brainExit = null'),
  'startBrain must clear the previous exit, or a restart fails instantly')
console.log('ok  a brain that exited fails the wait immediately, with its reason')

console.log('\nall brain-launch checks passed')
