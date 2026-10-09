/**
 * U412: the directories a user's own tools live in, on PATH.
 *
 * An app launched from Finder or the Dock gets PATH=/usr/bin:/bin:/usr/sbin:/sbin,
 * not the login shell's. The bootstrap installs uv into ~/.local/bin, so on
 * every launch after the first `uv --version` failed and uv was downloaded
 * again — and with no network, the app did not start at all. A uv from
 * Homebrew was never seen either.
 *
 * Windows is left alone: its installer writes the user PATH, which a GUI app
 * does inherit.
 */

'use strict'

const path = require('path')

function withUserToolPaths(env, platform = process.platform) {
  if (platform === 'win32') return env
  const home = env.HOME
  const wanted = [
    home && path.posix.join(home, '.local', 'bin'),   // uv's own installer
    home && path.posix.join(home, '.cargo', 'bin'),   // older uv installs
    '/opt/homebrew/bin',                              // Homebrew, Apple Silicon
    '/usr/local/bin',                                 // Homebrew, Intel
  ].filter(Boolean)
  const parts = (env.PATH || '').split(':').filter(Boolean)
  const missing = wanted.filter((d) => !parts.includes(d))
  if (!missing.length) return env
  return { ...env, PATH: [...missing, ...parts].join(':') }
}

module.exports = { withUserToolPaths }
