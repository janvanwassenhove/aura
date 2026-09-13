/**
 * U173: update check against GitHub Releases.
 *
 * Pure logic lives here (dependency-injected, testable with plain node);
 * main.cjs owns the dialog/download side-effects.
 *
 * Private-repo reality: unauthenticated calls to a private repo's releases
 * return 404. When a GITHUB_TOKEN is present (infra/dev/.env — the same file
 * the connectors already use) we send it; without one the check simply finds
 * nothing until the repo goes public. Fails silent by design — an update
 * check must never bother the user with network errors.
 */

const REPO = 'janvanwassenhove/aura'

function parseVersion(v) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)/.exec(String(v || '').trim())
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

function isNewer(candidate, current) {
  const a = parseVersion(candidate)
  const b = parseVersion(current)
  if (!a || !b) return false
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i]
  }
  return false
}

/** The one asset a Windows user should install.
 *
 * U353: a release carries two of them. The NSIS `.exe` installs per-user into
 * %LOCALAPPDATA%; the MSI installs machine-wide into Program Files, which is
 * the only one a locked-down laptop will run. Handing an MSI install the .exe
 * would quietly produce a SECOND copy somewhere else, and which one the
 * shortcut then starts is a coin toss — so the update follows the way this
 * copy was installed.
 *
 * The fallback matters as much as the choice: an older release has no MSI at
 * all, and answering "no update available" to a per-machine install because
 * the preferred file is missing would be a lie.
 */
function pickWindowsAsset(assets, { perMachine = false } = {}) {
  const list = assets || []
  const msi = list.find((a) => /windows\.msi$/i.test(a.name)) || null
  const exe = list.find((a) => /windows-setup\.exe$/i.test(a.name)) || null
  return (perMachine ? msi || exe : exe || msi) || null
}

/** Was this copy installed for the whole machine (the MSI) or just this user?
 *
 * Decided by where the running executable lives, because that is the one thing
 * that is true regardless of how it got there. Anything unrecognised counts as
 * per-user: every install that exists before U353 is an NSIS per-user install,
 * so that is the answer that cannot break one.
 */
function installedPerMachine(exePath, env = process.env) {
  const exe = String(exePath || '').toLowerCase().replace(/\\+$/, '')
  if (!exe) return false
  const roots = [env.ProgramFiles, env['ProgramFiles(x86)'], env.ProgramW6432]
  return roots.some((root) => {
    if (!root) return false
    const prefix = String(root).toLowerCase().replace(/\\+$/, '') + '\\'
    return exe.startsWith(prefix)
  })
}

/** How to run a staged installer from the apply script.
 *
 * `call x.msi /S` does nothing useful — an MSI is data for msiexec, not a
 * program. And the MSI install is deliberately NOT silent: a per-machine
 * install needs elevation, and a UAC prompt appearing with no window to
 * explain it is worse than a wizard the owner can see.
 */
function installerCommand(installerPath) {
  return /\.msi$/i.test(String(installerPath || ''))
    ? `msiexec /i "${installerPath}"`
    : `call "${installerPath}" /S`
}

/** U224: the release's SHA256SUMS.txt, when the build published one. */
function pickChecksums(assets) {
  return (assets || []).find((a) => /^SHA256SUMS\.txt$/i.test(a.name)) || null
}

/** Reject anything that isn't a plain file name — the staged path is later
 *  interpolated into a .cmd, where a quote or space would break out of the
 *  quoting and inject commands. */
function safeAssetName(name) {
  return /^[A-Za-z0-9._-]+$/.test(String(name || '')) ? String(name) : null
}

/** SHA-256 of a file on disk, lowercase hex. */
async function fileSha256(filePath, fsImpl = require('fs')) {
  const crypto = require('crypto')
  const hash = crypto.createHash('sha256')
  await new Promise((resolve, reject) => {
    fsImpl.createReadStream(filePath)
      .on('data', (d) => hash.update(d))
      .on('error', reject)
      .on('end', resolve)
  })
  return hash.digest('hex')
}

/** Verify a staged file against the release's SHA256SUMS.txt.
 *  Returns {ok, reason}. A MISSING checksum list is reported, not silently
 *  accepted — the caller decides, but it can never look like a pass. */
async function verifyAsset({ asset, checksumsAsset, filePath, token,
                             fetchImpl = fetch, fsImpl = require('fs') }) {
  if (!checksumsAsset) return { ok: false, reason: 'no-checksums' }
  const headers = { Accept: 'application/octet-stream', 'User-Agent': 'aura-desktop' }
  if (token) headers.Authorization = `Bearer ${token}`
  let text
  try {
    const res = await fetchImpl(checksumsAsset.url, { headers })
    if (!res.ok) return { ok: false, reason: `checksums HTTP ${res.status}` }
    text = await res.text()
  } catch (err) {
    return { ok: false, reason: `checksums unreachable: ${err.message}` }
  }
  // Lines are "<sha256>  <name>" (sha256sum prefixes binary names with '*').
  const wanted = text.split(/\r?\n/)
    .map((line) => line.trim().split(/\s+/))
    .find(([, name]) => name && name.replace(/^\*/, '') === asset.name)
  if (!wanted) return { ok: false, reason: 'asset not listed in checksums' }
  const actual = await fileSha256(filePath, fsImpl)
  return actual.toLowerCase() === wanted[0].toLowerCase()
    ? { ok: true }
    : { ok: false, reason: 'checksum mismatch' }
}

/**
 * U178: returns a STATUS, not just null.
 *
 *   {status:'update',  update:{tag,version,htmlUrl,asset}}
 *   {status:'current', latest:'v2.0.4'}
 *   {status:'unauthorized'}  — private repo and no/!valid token
 *   {status:'error', reason}
 *
 * The background check still only acts on 'update'; the About dialog can now
 * explain the other outcomes instead of leaving the owner wondering whether
 * update checking works at all (it looked broken while the repo was private).
 */
async function checkForUpdate({ currentVersion, token, fetchImpl = fetch,
                                perMachine = false }) {
  try {
    const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'aura-desktop' }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetchImpl(`https://api.github.com/repos/${REPO}/releases/latest`, { headers })
    if (res.status === 404 || res.status === 401 || res.status === 403) {
      return { status: 'unauthorized' }
    }
    if (!res.ok) return { status: 'error', reason: `HTTP ${res.status}` }
    const rel = await res.json()
    if (rel.draft || rel.prerelease) return { status: 'current', latest: currentVersion }
    if (!isNewer(rel.tag_name, currentVersion)) {
      return { status: 'current', latest: rel.tag_name }
    }
    return {
      status: 'update',
      update: {
        tag: rel.tag_name,
        version: String(rel.tag_name).replace(/^v/, ''),
        htmlUrl: rel.html_url,
        asset: pickWindowsAsset(rel.assets, { perMachine }),   // U353
        checksums: pickChecksums(rel.assets),   // U224
      },
    }
  } catch (err) {
    return { status: 'error', reason: err.message || 'network' }
  }
}

/**
 * Download a release asset to destPath. Uses the API asset URL with
 * Accept: octet-stream so it also works on private repos (with token);
 * GitHub answers with a redirect that fetch follows automatically.
 */
async function downloadAsset({ asset, token, destPath, fetchImpl = fetch, fsImpl = require('fs') }) {
  const headers = { Accept: 'application/octet-stream', 'User-Agent': 'aura-desktop' }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetchImpl(asset.url, { headers })
  if (!res.ok) throw new Error(`asset download failed: HTTP ${res.status}`)
  const { Readable } = require('stream')
  const { pipeline } = require('stream/promises')
  await pipeline(Readable.fromWeb(res.body), fsImpl.createWriteStream(destPath))
  return destPath
}

module.exports = { REPO, parseVersion, isNewer, pickWindowsAsset, pickChecksums,
                   safeAssetName, fileSha256, verifyAsset, checkForUpdate, downloadAsset,
                   installedPerMachine, installerCommand }
