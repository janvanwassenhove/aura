/**
 * Port resolution and runtime config for the console — U234.
 *
 * Extracted from main.cjs so it can be tested without Electron. These three
 * functions are the whole answer to "another app is on our port": ask for the
 * one we want, take any free one if we cannot have it, and tell the console
 * where things actually ended up.
 */

const http = require('http')

/**
 * Bind `server` to `preferred`, or to any free port if that one is taken.
 *
 * Returns the port actually bound. A neighbouring dev server on 5173 is a
 * completely ordinary thing for a developer's machine to have; refusing to
 * start over it is a worse trade than moving.
 */
function listenPreferring(server, preferred, host = '127.0.0.1', onFallback = null) {
  return new Promise((resolve, reject) => {
    const handleFirstError = (err) => {
      if (err.code !== 'EADDRINUSE' && err.code !== 'EACCES') return reject(err)
      if (onFallback) onFallback(preferred, err.code)
      server.removeListener('error', handleFirstError)
      server.once('error', reject)
      server.listen(0, host, () => resolve(server.address().port))
    }
    server.once('error', handleFirstError)
    server.listen(preferred, host, () => resolve(server.address().port))
  })
}

/**
 * Find a free port for a process we do not control — the brain binds it itself.
 *
 * There is a race here by construction: we let go of the port before the brain
 * takes it. It is small and it is the honest cost of not owning the socket; if
 * something wins that race, the brain fails to bind and the health check says
 * so rather than the app silently talking to a stranger.
 */
function pickFreePort(preferred, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const probe = http.createServer()
    listenPreferring(probe, preferred, host)
      .then((port) => probe.close(() => resolve(port)))
      .catch(() => resolve(preferred))   // could not probe: let the brain try
  })
}

/**
 * Inject the resolved endpoints into index.html.
 *
 * The console is a static build, so without this the brain's port would have to
 * be known at compile time — which is exactly what stops a packaged app from
 * ever moving off a busy one. `src/lib/endpoints.ts` prefers this over anything
 * baked in.
 */
function withRuntimeConfig(html, { brainUrl, robotEventsWs }) {
  const cfg = JSON.stringify({ brainUrl, robotEventsWs })
  const tag = `<script>window.__AURA_RUNTIME__=${cfg}</script>`
  return html.includes('</head>')
    ? html.replace('</head>', `  ${tag}\n</head>`)
    : tag + html
}

module.exports = { listenPreferring, pickFreePort, withRuntimeConfig }
