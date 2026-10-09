/**
 * U412: re-seal the Mac app with an ad-hoc signature when there is no
 * Developer ID to sign it with.
 *
 * With `mac.identity: null` electron-builder skips signing — but it has already
 * renamed Electron's binary and rewritten Info.plist, which breaks the seal on
 * the bundle. A downloaded copy with a broken seal is "damaged and can't be
 * opened" to Gatekeeper, with no way past it but the terminal, and on Apple
 * Silicon the kernel refuses code whose signature does not hold.
 *
 * An ad-hoc signature (identity "-") seals the bundle as it ships. It proves
 * integrity, not identity: Gatekeeper still asks once ("Open Anyway" in
 * Privacy & Security). ADR-020 records why this is the default and how to move
 * to a Developer ID; when one is configured (CSC_LINK / CSC_NAME) this hook
 * steps aside and electron-builder signs and notarizes as usual.
 *
 * Runs as electron-builder's `afterPack`: after the bundle is complete, before
 * the DMG and the zip are made — so both carry the sealed app.
 */

'use strict'

const path = require('path')
const { execFileSync } = require('child_process')

/** What to run for this build, or null when it is not ours to sign. */
function adHocPlan(context, env = process.env) {
  if (context.electronPlatformName !== 'darwin') return null
  if (env.CSC_LINK || env.CSC_NAME) return null       // a real identity: electron-builder's job
  const name = `${context.packager.appInfo.productFilename}.app`
  const app = path.join(context.appOutDir, name)
  return {
    app,
    commands: [
      ['codesign', '--force', '--deep', '--sign', '-', '--timestamp=none', app],
      ['codesign', '--verify', '--deep', '--strict', '--verbose=2', app],
    ],
  }
}

async function afterPack(context) {
  const plan = adHocPlan(context)
  if (!plan) {
    if (context.electronPlatformName === 'darwin') {
      console.log('  • mac-sign: a Developer ID is configured — electron-builder signs this build')
    }
    return
  }
  for (const [cmd, ...args] of plan.commands) {
    execFileSync(cmd, args, { stdio: 'inherit' })
  }
  console.log(`  • mac-sign: ${path.basename(plan.app)} sealed ad hoc and verified ` +
              '(no Developer ID — Gatekeeper will ask the owner once)')
}

module.exports = afterPack
module.exports.default = afterPack
module.exports.adHocPlan = adHocPlan
