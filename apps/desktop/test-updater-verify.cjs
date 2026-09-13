// U224 (S11): the installer is executed with elevated trust, so what we
// downloaded must be what the release published. Plain node — no test runner in
// this package; run with `node apps/desktop/test-updater-verify.cjs`.
const assert = require('assert')
const crypto = require('crypto')
const fs = require('fs')
const os = require('os')
const path = require('path')

const { safeAssetName, fileSha256, verifyAsset,
        pickWindowsAsset, installedPerMachine, installerCommand } = require('./updater.cjs')

async function main() {
  // --- safeAssetName: the .cmd-injection guard -----------------------------
  assert.strictEqual(safeAssetName('AURA-2.0.28-windows-setup.exe'),
                     'AURA-2.0.28-windows-setup.exe')
  for (const bad of ['a b.exe', 'x".exe', 'x&calc.exe', '..\\evil.exe', '', null]) {
    assert.strictEqual(safeAssetName(bad), null, `should refuse: ${bad}`)
  }

  // --- fileSha256 + verifyAsset -------------------------------------------
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aura-upd-'))
  const file = path.join(dir, 'installer.exe')
  fs.writeFileSync(file, 'pretend installer bytes')
  const digest = await fileSha256(file)
  assert.strictEqual(digest, crypto.createHash('sha256')
    .update('pretend installer bytes').digest('hex'))

  const asset = { name: 'installer.exe' }
  const checksumsAsset = { url: 'https://example/SHA256SUMS.txt' }
  const listing = (d) => `${d}  installer.exe\ndeadbeef  other-file.dmg\n`

  // Matching checksum → accepted.
  let ok = await verifyAsset({
    asset, checksumsAsset, filePath: file, token: '',
    fetchImpl: async () => ({ ok: true, text: async () => listing(digest) }),
  })
  assert.deepStrictEqual(ok, { ok: true })

  // Tampered file (the whole point) → refused.
  fs.writeFileSync(file, 'malicious installer bytes')
  ok = await verifyAsset({
    asset, checksumsAsset, filePath: file, token: '',
    fetchImpl: async () => ({ ok: true, text: async () => listing(digest) }),
  })
  assert.strictEqual(ok.ok, false)
  assert.strictEqual(ok.reason, 'checksum mismatch')

  // No checksums published (older release) → reported, never a silent pass.
  ok = await verifyAsset({ asset, checksumsAsset: null, filePath: file, token: '' })
  assert.deepStrictEqual(ok, { ok: false, reason: 'no-checksums' })

  // Asset absent from the list → refused rather than assumed fine.
  ok = await verifyAsset({
    asset, checksumsAsset, filePath: file, token: '',
    fetchImpl: async () => ({ ok: true, text: async () => 'abc  something-else.exe\n' }),
  })
  assert.strictEqual(ok.reason, 'asset not listed in checksums')

  fs.rmSync(dir, { recursive: true, force: true })

  // --- U353: update the way this copy was installed ------------------------
  //
  // A release now carries both installers. An MSI install lives in Program
  // Files; the NSIS .exe installs per-user into %LOCALAPPDATA%. Handing an
  // MSI install the .exe would quietly produce a SECOND copy in a different
  // place, and which one the shortcut then starts is a coin toss.
  const both = [
    { name: 'AURA-2.0.150-windows-setup.exe' },
    { name: 'AURA-2.0.150-windows.msi' },
    { name: 'SHA256SUMS.txt' },
  ]
  assert.strictEqual(pickWindowsAsset(both, { perMachine: true }).name,
                     'AURA-2.0.150-windows.msi')
  assert.strictEqual(pickWindowsAsset(both, { perMachine: false }).name,
                     'AURA-2.0.150-windows-setup.exe')
  assert.strictEqual(pickWindowsAsset(both).name,
                     'AURA-2.0.150-windows-setup.exe', 'per-user is the default')

  // An older release has no MSI. A per-machine install must still be offered
  // the .exe rather than nothing — "no update available" would be a lie.
  const exeOnly = [{ name: 'AURA-2.0.140-windows-setup.exe' }]
  assert.strictEqual(pickWindowsAsset(exeOnly, { perMachine: true }).name,
                     'AURA-2.0.140-windows-setup.exe')
  assert.strictEqual(pickWindowsAsset([], { perMachine: true }), null)

  // Where the running copy lives is how we know which it was.
  const env = { ProgramFiles: 'C:\\Program Files', LOCALAPPDATA: 'C:\\Users\\jan\\AppData\\Local' }
  assert.strictEqual(installedPerMachine('C:\\Program Files\\AURA\\AURA.exe', env), true)
  assert.strictEqual(
    installedPerMachine('C:\\Users\\jan\\AppData\\Local\\Programs\\AURA\\AURA.exe', env), false)
  // Case and trailing slashes are Windows being Windows, not a different place.
  assert.strictEqual(installedPerMachine('c:\\program files\\AURA\\AURA.exe', env), true)
  // Nothing known → assume per-user, which is what every install before U353 is.
  assert.strictEqual(installedPerMachine('', env), false)
  assert.strictEqual(installedPerMachine('D:\\portable\\AURA.exe', env), false)

  // --- and run it the way that file can be run -----------------------------
  //
  // `call x.msi /S` does nothing useful: an MSI is data for msiexec, not a
  // program. It is deliberately NOT silent — a per-machine install needs
  // elevation, and a UAC prompt nobody asked for is worse than a wizard.
  assert.match(installerCommand('C:\\tmp\\AURA-2.0.150-windows.msi'), /^msiexec /i)
  assert.match(installerCommand('C:\\tmp\\AURA-2.0.150-windows.msi'), /\/i /i)
  assert.ok(!/\/qn/i.test(installerCommand('C:\\tmp\\a.msi')), 'must not install silently')
  assert.strictEqual(installerCommand('C:\\tmp\\AURA-2.0.150-windows-setup.exe'),
                     'call "C:\\tmp\\AURA-2.0.150-windows-setup.exe" /S')

  console.log('updater verification: all assertions passed')
}

main().catch((err) => { console.error(err); process.exit(1) })
