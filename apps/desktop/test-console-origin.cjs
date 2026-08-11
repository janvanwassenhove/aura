// U229 + U234: the console window must reach OUR console and OUR brain, on a
// machine where other projects are also running.
//
// Two failures live here. The first shipped: our static server binds 127.0.0.1
// while another project's Vite dev server holds [::1] on the same port — both
// binds succeed, no EADDRINUSE, no error anywhere — and then "localhost"
// resolves to ::1 first on Windows, so the window loads the neighbour. The
// second is the ordinary one: the port is simply taken, and refusing to start
// over a colleague's dev server is a bad trade when the OS will hand us a free
// port for the asking.
//
// Plain node — no test runner in this package; run with
// `node apps/desktop/test-console-origin.cjs`.
const assert = require('assert')
const fs = require('fs')
const http = require('http')
const path = require('path')

const { listenPreferring, pickFreePort, withRuntimeConfig } = require('./serving.cjs')

const serve = (host, body) => new Promise((resolve, reject) => {
  const server = http.createServer((_req, res) => { res.writeHead(200); res.end(body) })
  server.once('error', reject)
  server.listen(0, host, () => resolve(server))
})

const get = (url) => new Promise((resolve, reject) => {
  http.get(url, (res) => {
    let data = ''
    res.on('data', (c) => { data += c })
    res.on('end', () => resolve(data))
  }).on('error', reject)
})

async function main() {
  // --- the dual-stack trap: two servers, one port, two address families ----
  let squatter
  try {
    squatter = await serve('::1', 'SOMEBODY ELSES APP')
  } catch (err) {
    console.log(`skipped dual-stack check — no IPv6 loopback here (${err.code})`)
  }

  if (squatter) {
    const port = squatter.address().port
    // Binding the SAME port on IPv4 succeeds. This is the whole trap: nothing
    // fails, so nothing warns.
    const ours = await new Promise((resolve, reject) => {
      const server = http.createServer((_req, res) => { res.writeHead(200); res.end('THE CONSOLE') })
      server.once('error', reject)
      server.listen(port, '127.0.0.1', () => resolve(server))
    })

    assert.strictEqual(await get(`http://127.0.0.1:${port}`), 'THE CONSOLE',
      'addressing by IP must reach our own server')
    assert.strictEqual(await get(`http://[::1]:${port}`), 'SOMEBODY ELSES APP',
      'the other stack is genuinely a different server on the same port')

    ours.close()
    squatter.close()
    console.log('ok  dual-stack: 127.0.0.1 reaches our server while [::1] holds the same port')
  }

  // --- the port is taken on OUR stack: move, do not fail -------------------
  const blocker = await serve('127.0.0.1', 'BLOCKER')
  const taken = blocker.address().port
  let warned = null
  const server = http.createServer((_req, res) => { res.writeHead(200); res.end('MOVED') })
  const got = await listenPreferring(server, taken, '127.0.0.1', (p, code) => { warned = [p, code] })
  assert.notStrictEqual(got, taken, 'must not claim to have bound a port somebody else holds')
  assert.ok(got > 0, 'must return the port actually bound')
  assert.deepStrictEqual(warned, [taken, 'EADDRINUSE'], 'must say out loud that it moved')
  assert.strictEqual(await get(`http://127.0.0.1:${got}`), 'MOVED', 'the fallback port must serve us')
  assert.strictEqual(await get(`http://127.0.0.1:${taken}`), 'BLOCKER', 'the neighbour keeps its port')
  server.close()
  console.log(`ok  port ${taken} taken -> bound ${got} instead, neighbour undisturbed`)

  // --- the preferred port, when it is free ---------------------------------
  const free = await pickFreePort(taken + 1)
  assert.ok(free > 0, 'pickFreePort must return something usable')
  const direct = http.createServer()
  const bound = await listenPreferring(direct, free)
  assert.strictEqual(bound, free, 'a free preferred port must be used as-is')
  direct.close()
  blocker.close()
  console.log('ok  a free preferred port is used unchanged')

  // --- the console is told where the brain went ----------------------------
  const html = withRuntimeConfig('<html><head><title>x</title></head><body></body></html>',
    { brainUrl: 'http://127.0.0.1:9999', robotEventsWs: 'ws://127.0.0.1:9999/ws/events' })
  assert.ok(html.includes('window.__AURA_RUNTIME__'), 'index.html must carry the runtime config')
  assert.ok(html.includes('"brainUrl":"http://127.0.0.1:9999"'), 'the resolved brain URL must be in it')
  assert.ok(html.indexOf('__AURA_RUNTIME__') < html.indexOf('</head>'),
    'the config must land before the app script runs')
  const noHead = withRuntimeConfig('<body>hi</body>', { brainUrl: 'http://127.0.0.1:1' })
  assert.ok(noHead.startsWith('<script>'), 'a document without a head still gets the config')
  console.log('ok  the resolved endpoints are injected into index.html')

  // --- the source guard: nothing may address the console by name -----------
  const main = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf-8')
  const byName = main.split('\n')
    .map((line, i) => [i + 1, line])
    .filter(([, line]) => /localhost:\$\{consolePort\}|localhost:5173/.test(line))
    // The CORS allow-list deliberately carries both spellings: a human opening
    // the console in a browser will type the name.
    .filter(([, line]) => !line.includes('CORS_ORIGINS') && !line.includes('consoleUrl()'))
  assert.deepStrictEqual(byName, [],
    `main.cjs must address the console by IP, not by name:\n${byName.map(([n, l]) => `  ${n}: ${l.trim()}`).join('\n')}`)

  assert.ok(main.includes('const consoleUrl = () => `http://127.0.0.1:${consolePort}`'),
    'consoleUrl must be the IP form')
  assert.ok(main.includes('const brainUrl = () => `http://127.0.0.1:${brainPort}`'),
    'brainUrl must be the IP form')
  console.log('ok  main.cjs addresses both services by IP')

  // --- and nothing may hardcode a port that startup is meant to resolve ----
  assert.ok(!/const BRAIN_PORT = \d+/.test(main) && !/const CONSOLE_PORT = \d+/.test(main),
    'ports are resolved at startup; a fixed constant would defeat that')
  console.log('ok  no fixed port constants remain')

  console.log('console-origin tests passed')
}

main().catch((err) => { console.error(err); process.exit(1) })
