// U229: the console window must address its own server by IP.
//
// Background: our static server binds 127.0.0.1. A Vite dev server for some
// other project binds [::1] and defaults to the same port, 5173. Both binds
// succeed — different address families, no EADDRINUSE, no error anywhere — and
// then "localhost" resolves to ::1 first on Windows, so the window loads the
// other project. The app looks corrupted and is perfectly healthy.
//
// Plain node — no test runner in this package; run with
// `node apps/desktop/test-console-origin.cjs`.
const assert = require('assert')
const fs = require('fs')
const http = require('http')
const path = require('path')

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
  // --- the mechanism: two servers, one port, two address families ----------
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

  // --- the guard: main.cjs must not address the console by name ------------
  const main = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf-8')
  const byName = main.split('\n')
    .map((line, i) => [i + 1, line])
    .filter(([, line]) => /localhost:\$\{CONSOLE_PORT\}|localhost:5173/.test(line))
    // The CORS allow-list deliberately carries both spellings: a human opening
    // the console in a browser will type the name.
    .filter(([, line]) => !line.includes('CORS_ORIGINS'))
  assert.deepStrictEqual(byName, [],
    `main.cjs must address the console by IP, not by name:\n${byName.map(([n, l]) => `  ${n}: ${l.trim()}`).join('\n')}`)
  console.log('ok  main.cjs addresses the console by IP')

  assert.ok(main.includes("const CONSOLE_URL = `http://127.0.0.1:${CONSOLE_PORT}`"),
    'CONSOLE_URL must be the IP form')
  console.log('ok  CONSOLE_URL is the IP form')

  console.log('console-origin tests passed')
}

main().catch((err) => { console.error(err); process.exit(1) })
