// U412: the Mac app carries a valid signature, even without an Apple account.
//
// Reported (translated): "how can I fix the Mac installer (not working
// currently)". The release log said it plainly, for both architectures:
//
//   • skipped macOS code signing  reason=identity explicitly is set to null
//
// Skipping is not the same as leaving Electron's own signature alone:
// electron-builder renames the binary and rewrites Info.plist, which breaks the
// seal on the bundle. A downloaded copy of a bundle with a broken seal is what
// Gatekeeper calls "damaged and can't be opened — move it to the Trash", and
// on Apple Silicon the kernel refuses code whose signature does not hold.
//
// This hook re-seals the finished bundle with an ad-hoc signature. It is not a
// Developer ID: Gatekeeper still asks the owner to confirm once ("Open
// Anyway"). But that is a question with an answer, where "damaged" is not.
//
// Plain node — run with `node apps/desktop/test-mac-sign.cjs`.
const assert = require('assert')
const path = require('path')
const { adHocPlan } = require('./mac-sign.cjs')

const ctx = (platform, extra = {}) => ({
  electronPlatformName: platform,
  appOutDir: path.join('dist', 'mac-arm64'),
  packager: { appInfo: { productFilename: 'AURA' } },
  ...extra,
})

// ── a Mac build with no certificate is re-sealed ad hoc ──────────────────
{
  const plan = adHocPlan(ctx('darwin'), {})
  assert.ok(plan, 'an unsigned Mac build must be signed ad hoc')
  assert.strictEqual(plan.app, path.join('dist', 'mac-arm64', 'AURA.app'))
  const sign = plan.commands[0]
  assert.strictEqual(sign[0], 'codesign')
  assert.ok(sign.includes('--force') && sign.includes('--deep'), 'every nested helper and framework')
  const i = sign.indexOf('--sign')
  assert.ok(i > 0 && sign[i + 1] === '-', 'ad hoc means the identity "-"')
  assert.strictEqual(sign[sign.length - 1], plan.app)
  console.log('ok  an unsigned Mac build is re-sealed ad hoc')
}

// ── and the result is verified, so a broken seal fails the build ─────────
{
  const verify = adHocPlan(ctx('darwin'), {}).commands[1]
  assert.deepStrictEqual(verify.slice(0, 4), ['codesign', '--verify', '--deep', '--strict'])
  console.log('ok  the seal is verified before the DMG is made')
}

// ── a real certificate wins: electron-builder signs, we stay out of it ───
for (const env of [{ CSC_LINK: 'x' }, { CSC_NAME: 'Developer ID Application: X' }]) {
  assert.strictEqual(adHocPlan(ctx('darwin'), env), null, JSON.stringify(env))
}
console.log('ok  a Developer ID certificate is left to electron-builder')

// ── other platforms are none of its business ─────────────────────────────
for (const p of ['win32', 'linux']) assert.strictEqual(adHocPlan(ctx(p), {}), null, p)
console.log('ok  Windows and Linux builds are untouched')

// ── it is wired into the build ───────────────────────────────────────────
{
  const pkg = require('./package.json')
  assert.strictEqual(pkg.build.afterPack, './mac-sign.cjs', 'the hook must be configured')
  console.log('ok  package.json runs it after packing')
}
