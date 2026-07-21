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

/** The one asset a Windows user should install. */
function pickWindowsAsset(assets) {
  return (assets || []).find((a) => /windows-setup\.exe$/i.test(a.name)) || null
}

/**
 * Returns {tag, version, htmlUrl, asset} when a newer release exists,
 * null otherwise (including on ANY error — silent by design).
 */
async function checkForUpdate({ currentVersion, token, fetchImpl = fetch }) {
  try {
    const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'aura-desktop' }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetchImpl(`https://api.github.com/repos/${REPO}/releases/latest`, { headers })
    if (!res.ok) return null            // 404 on private repo without token, rate limits, …
    const rel = await res.json()
    if (rel.draft || rel.prerelease) return null
    if (!isNewer(rel.tag_name, currentVersion)) return null
    return {
      tag: rel.tag_name,
      version: String(rel.tag_name).replace(/^v/, ''),
      htmlUrl: rel.html_url,
      asset: pickWindowsAsset(rel.assets),
    }
  } catch {
    return null
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

module.exports = { REPO, parseVersion, isNewer, pickWindowsAsset, checkForUpdate, downloadAsset }
