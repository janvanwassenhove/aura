// U235: every module the shell requires must actually be inside the installer.
//
// `build.files` in package.json is an explicit allowlist. Adding a module to
// the source tree and forgetting that list produces an app that runs perfectly
// from a checkout and dies on first launch when installed:
//
//   Error: Cannot find module './serving.cjs'
//
// which is exactly what v2.0.58 did. Nothing in the test suite looked at the
// gap between "what main.cjs needs" and "what gets packed", so nothing could
// have caught it. This does.
//
// Plain node — run with `node apps/desktop/test-packaging.cjs`.
const assert = require('assert')
const fs = require('fs')
const path = require('path')

const pkg = require('./package.json')
const patterns = pkg.build.files

/** Does any `files` glob cover this path? Handles the shapes we actually use. */
function covered(rel) {
  return patterns.some((raw) => {
    if (raw.startsWith('!')) return false
    if (raw === rel) return true
    if (raw.endsWith('/**')) return rel.startsWith(raw.slice(0, -2))
    if (raw.includes('*')) {
      const rx = new RegExp('^' + raw.split('*').map((s) =>
        s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('[^/]*') + '$')
      return rx.test(rel)
    }
    return false
  })
}

/** Follow local requires from an entry point, transitively. */
function localRequires(entry, seen = new Set()) {
  const rel = path.basename(entry)
  if (seen.has(rel)) return seen
  seen.add(rel)
  const src = fs.readFileSync(path.join(__dirname, rel), 'utf-8')
  for (const m of src.matchAll(/require\(['"](\.\/[^'"]+)['"]\)/g)) {
    let target = m[1].replace(/^\.\//, '')
    if (!path.extname(target)) target += '.js'
    if (!fs.existsSync(path.join(__dirname, target))) {
      assert.fail(`${rel} requires ${m[1]}, which does not exist`)
    }
    localRequires(target, seen)
  }
  return seen
}

// The three entry points electron-builder cares about: main, preload, and
// anything they pull in.
const needed = new Set([
  ...localRequires('main.cjs'),
  ...localRequires('preload.cjs'),
])

const missing = [...needed].filter((f) => !covered(f))
assert.deepStrictEqual(missing, [],
  'these modules are required at runtime but not in package.json build.files:\n' +
  missing.map((f) => `  ${f}`).join('\n'))

console.log(`ok  all ${needed.size} runtime module(s) are covered by build.files:`)
for (const f of [...needed].sort()) console.log(`      ${f}`)

// The console dist and the Python workspace ride along as extraResources —
// main.cjs resolves them under process.resourcesPath, so a missing entry there
// fails the same way, just later.
const extras = (pkg.build.extraResources || []).map((r) => (typeof r === 'string' ? r : r.to))
for (const needle of ['console', 'aura/apps/aura-brain']) {
  assert.ok(extras.includes(needle), `extraResources must carry ${needle}`)
}
console.log('ok  extraResources still carry the console and the brain')

console.log('packaging tests passed')
