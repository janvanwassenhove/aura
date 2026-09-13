/**
 * U337: sign the Windows installer — when there is something to sign with.
 *
 * The build was never signed, so Windows greets every installer with "unknown
 * publisher", and a managed work PC refuses it outright. Reported as: "code
 * signing moet toegevoegd worden zodat ik ook kan installeren op werk pc en
 * niet langer exceptie krijg".
 *
 * This hook is deliberately a no-op when no credentials are configured: a fork,
 * a pull request and a local `npm run dist` must all still produce a working
 * (unsigned) installer, and a release must not fail because a secret is
 * missing. What it must never do is be silent about which of the two happened —
 * "is this build signed?" is answered in the log, and by the verification step
 * in the release workflow.
 *
 * Two routes, in order of preference:
 *
 *   1. **Azure Trusted Signing** (AZURE_TENANT_ID / AZURE_CLIENT_ID /
 *      AZURE_CLIENT_SECRET + TRUSTED_SIGNING_*). The key lives in Microsoft's
 *      HSM; nothing secret ever reaches the runner's disk. Since June 2023 a
 *      new OV certificate cannot be a plain file anyway — the private key must
 *      sit on certified hardware — so this is the route that still exists for
 *      a small publisher.
 *   2. **A PFX file** (WINDOWS_PFX_BASE64 + WINDOWS_PFX_PASSWORD), for an
 *      existing certificate or a hardware token that exports one. Written to a
 *      temp file, used, and deleted in a finally block.
 */

'use strict'

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

/** Windows SDK signtool, wherever this runner keeps it. */
function findSigntool() {
  if (process.env.SIGNTOOL_PATH) return process.env.SIGNTOOL_PATH
  const roots = [
    'C:\\Program Files (x86)\\Windows Kits\\10\\bin',
    'C:\\Program Files\\Windows Kits\\10\\bin',
  ]
  for (const root of roots) {
    if (!fs.existsSync(root)) continue
    const versions = fs.readdirSync(root).filter(d => d.startsWith('10.')).sort().reverse()
    for (const v of versions) {
      const exe = path.join(root, v, 'x64', 'signtool.exe')
      if (fs.existsSync(exe)) return exe
    }
  }
  return null
}

function run(exe, args) {
  execFileSync(exe, args, { stdio: 'inherit' })
}

exports.default = async function sign(configuration) {
  const file = configuration.path
  const timestamp = process.env.TIMESTAMP_URL || 'http://timestamp.digicert.com'
  const azure = process.env.AZURE_CLIENT_ID && process.env.AZURE_CLIENT_SECRET
    && process.env.AZURE_TENANT_ID && process.env.TRUSTED_SIGNING_ENDPOINT
  const pfx = process.env.WINDOWS_PFX_BASE64

  if (!azure && !pfx) {
    // Not an error: an unsigned build is the status quo and still works. It
    // must simply never look signed.
    console.log(`[sign] UNSIGNED — no signing credentials configured: ${file}`)
    return
  }

  const signtool = findSigntool()
  if (!signtool) {
    throw new Error('signtool.exe not found — cannot sign; set SIGNTOOL_PATH')
  }

  if (azure) {
    // The dlib does the talking to Azure; the key never leaves their HSM.
    const metadata = {
      Endpoint: process.env.TRUSTED_SIGNING_ENDPOINT,
      CodeSigningAccountName: process.env.TRUSTED_SIGNING_ACCOUNT,
      CertificateProfileName: process.env.TRUSTED_SIGNING_PROFILE,
    }
    const metaFile = path.join(os.tmpdir(), `aura-signing-${Date.now()}.json`)
    fs.writeFileSync(metaFile, JSON.stringify(metadata), 'utf8')
    try {
      console.log(`[sign] Azure Trusted Signing: ${file}`)
      run(signtool, [
        'sign', '/v', '/debug', '/fd', 'SHA256', '/tr', timestamp, '/td', 'SHA256',
        '/dlib', process.env.TRUSTED_SIGNING_DLIB
          || 'C:\\Program Files\\Microsoft\\Azure.CodeSigning.Dlib\\Azure.CodeSigning.Dlib.dll',
        '/dmdf', metaFile, file,
      ])
    } finally {
      fs.rmSync(metaFile, { force: true })
    }
    return
  }

  const pfxFile = path.join(os.tmpdir(), `aura-cert-${Date.now()}.pfx`)
  fs.writeFileSync(pfxFile, Buffer.from(pfx, 'base64'))
  try {
    console.log(`[sign] certificate file: ${file}`)
    run(signtool, [
      'sign', '/v', '/fd', 'SHA256', '/tr', timestamp, '/td', 'SHA256',
      '/f', pfxFile, '/p', process.env.WINDOWS_PFX_PASSWORD || '', file,
    ])
  } finally {
    // The private key must not outlive the signature, even on a throwaway
    // runner: a cached workspace is a real way for one to escape.
    fs.rmSync(pfxFile, { force: true })
  }
}
