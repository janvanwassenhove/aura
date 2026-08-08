// U224 (S11): the installer is executed with elevated trust, so what we
// downloaded must be what the release published. Plain node — no test runner in
// this package; run with `node apps/desktop/test-updater-verify.cjs`.
const assert = require('assert')
const crypto = require('crypto')
const fs = require('fs')
const os = require('os')
const path = require('path')

const { safeAssetName, fileSha256, verifyAsset } = require('./updater.cjs')

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
  console.log('updater verification: all assertions passed')
}

main().catch((err) => { console.error(err); process.exit(1) })
