// U412: a Mac app started from Finder can find the uv it installed.
//
// macOS gives an app launched from Finder or the Dock a PATH of
// /usr/bin:/bin:/usr/sbin:/sbin — not the shell's. The bootstrap installs uv
// into ~/.local/bin and adds it to PATH for that one process only, so on the
// NEXT launch `uv --version` failed, hasUv() said no, and uv was downloaded
// again: every launch, a network round trip before the window — and offline,
// "uv installation failed" and no app at all. A uv from Homebrew was never
// found either.
//
// Plain node — run with `node apps/desktop/test-tool-paths.cjs`.
const assert = require('assert')
const { withUserToolPaths } = require('./tool-paths.cjs')

const FINDER = '/usr/bin:/bin:/usr/sbin:/sbin'

// ── the places uv lives are added, in front ──────────────────────────────
{
  const out = withUserToolPaths({ PATH: FINDER, HOME: '/Users/x' }, 'darwin')
  const parts = out.PATH.split(':')
  for (const dir of ['/Users/x/.local/bin', '/opt/homebrew/bin', '/usr/local/bin']) {
    assert.ok(parts.includes(dir), `${dir} must be on PATH`)
    assert.ok(parts.indexOf(dir) < parts.indexOf('/usr/bin'), `${dir} must come before the system dirs`)
  }
  assert.ok(out.PATH.endsWith(FINDER), 'what was there stays, in order')
  console.log('ok  ~/.local/bin and Homebrew are on a Finder-launched PATH')
}

// ── nothing is added twice ───────────────────────────────────────────────
{
  const once = withUserToolPaths({ PATH: FINDER, HOME: '/Users/x' }, 'darwin')
  const twice = withUserToolPaths(once, 'darwin')
  assert.strictEqual(twice.PATH, once.PATH)
  console.log('ok  idempotent')
}

// ── Linux gets ~/.local/bin too; Windows is left exactly as it is ────────
{
  const linux = withUserToolPaths({ PATH: '/usr/bin', HOME: '/home/x' }, 'linux')
  assert.ok(linux.PATH.split(':').includes('/home/x/.local/bin'))
  const win = { PATH: 'C:\\Windows', USERPROFILE: 'C:\\Users\\x' }
  assert.deepStrictEqual(withUserToolPaths(win, 'win32'), win)
  console.log('ok  Linux too; Windows untouched')
}

// ── no HOME, no guessing ─────────────────────────────────────────────────
{
  const out = withUserToolPaths({ PATH: FINDER }, 'darwin')
  assert.ok(!out.PATH.includes('undefined'), 'never a path built from a missing HOME')
  console.log('ok  a missing HOME adds no bogus directory')
}

// ── main.cjs applies it before anything looks for uv ─────────────────────
{
  const src = require('fs').readFileSync(require('path').join(__dirname, 'main.cjs'), 'utf-8')
  const apply = src.indexOf('withUserToolPaths(')
  const firstUse = src.indexOf('function hasUv')
  assert.ok(apply > 0, 'main.cjs must apply it')
  assert.ok(apply < firstUse, 'it must run at load, before hasUv is defined and used')
  console.log('ok  main.cjs applies it at load')
}
