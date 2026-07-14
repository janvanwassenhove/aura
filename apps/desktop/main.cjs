/**
 * AURA desktop app — one window, whole stack.
 *
 * On launch it:
 *   1. reads infra/dev/.env (wizard output) for brain configuration,
 *   2. spawns aura-brain (uv) as a child process and waits for /health,
 *   3. serves the built operator console on http://localhost:5173
 *      (same origin as the brain's default CORS allow-list),
 *   4. opens the console in a BrowserWindow with a tray icon.
 *
 * Quit (or last window closed) tears the brain down with it.
 * Brain logs: %APPDATA%/aura-desktop/brain.log (also in the terminal).
 */

const { app, BrowserWindow, Menu, Tray, dialog, ipcMain, session, shell, nativeImage } = require('electron')
const { spawn, execSync } = require('child_process')
const http = require('http')
const fs = require('fs')
const path = require('path')

const REPO_ROOT = path.resolve(__dirname, '..', '..')
const CONSOLE_DIST = path.join(REPO_ROOT, 'apps', 'operator-console', 'dist')
const ENV_FILE = path.join(REPO_ROOT, 'infra', 'dev', '.env')
// 8020, not 8000: Pollen's "Reachy Mini Control" desktop app squats on 8000.
const BRAIN_PORT = 8020
const BRAIN_URL = `http://localhost:${BRAIN_PORT}`
const CONSOLE_PORT = 5173

let brainProc = null
let staticServer = null
let mainWindow = null
let tray = null
let quitting = false

// ---------------------------------------------------------------------------
// Config: .env (wizard output) + desktop defaults
// ---------------------------------------------------------------------------

function loadEnvFile(file) {
  const env = {}
  if (!fs.existsSync(file)) return env
  for (const line of fs.readFileSync(file, 'utf-8').split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue
    const idx = trimmed.indexOf('=')
    const key = trimmed.slice(0, idx).trim()
    const value = trimmed.slice(idx + 1).trim()
    if (key) env[key] = value
  }
  return env
}

function brainEnv() {
  const env = { ...process.env, ...loadEnvFile(ENV_FILE) }
  // Desktop defaults (only when the wizard/.env didn't decide already).
  env.ROBOT_RUNTIME_URL = env.ROBOT_RUNTIME_URL || 'http://reachy-mini.local:8001'
  env.HEARTBEAT_ENABLED = env.HEARTBEAT_ENABLED || 'true'
  env.CORS_ORIGINS = env.CORS_ORIGINS || `http://localhost:${CONSOLE_PORT}`
  env.PORT = String(BRAIN_PORT)
  // The desktop app is text-first: voice STT/TTS run on the robot (U22/U24),
  // not in this window. Local model providers would crash a laptop without
  // the model files installed.
  env.STT_PROVIDER = 'null'
  env.TTS_PROVIDER = 'null'
  // Face recognition: on by default — it only activates when the knowledge
  // passphrase is set (wizard) and degrades to inert without the model stack.
  env.RECOGNITION_ENABLED = env.RECOGNITION_ENABLED || 'true'
  env.FACE_EMBEDDER = env.FACE_EMBEDDER || 'insightface'
  // Laptop tools (U36g): the dev agent can read code freely and run tasks;
  // every write/commit/push still pops the approval dialog in this app.
  env.DEV_AGENT_ENABLED = env.DEV_AGENT_ENABLED || 'true'
  // U40: pre-register safe desktop apps AURA may launch on request (each still
  // asks for approval). Owner extends this via ALLOWED_APPS in .env.
  // Spotify opens via its URI protocol handler (works for the Store/desktop
  // app without knowing its exe path); explorer resolves the protocol.
  env.ALLOWED_APPS = env.ALLOWED_APPS ||
    'vscode=code;code=code;notepad=notepad;spotify=explorer.exe spotify:'
  return env
}

// ---------------------------------------------------------------------------
// Brain child process
// ---------------------------------------------------------------------------

function startBrain() {
  const logPath = path.join(app.getPath('userData'), 'brain.log')
  const logStream = fs.createWriteStream(logPath, { flags: 'a' })
  logStream.write(`\n===== AURA brain start ${new Date().toISOString()} =====\n`)

  brainProc = spawn('uv', ['run', '--package', 'aura-brain', 'aura-brain'], {
    cwd: REPO_ROOT,
    env: brainEnv(),
    shell: process.platform === 'win32', // uv.exe resolution via PATH on Windows
  })
  brainProc.stdout.on('data', (d) => logStream.write(d))
  brainProc.stderr.on('data', (d) => logStream.write(d))
  brainProc.on('exit', (code) => {
    logStream.write(`===== brain exited (code ${code}) =====\n`)
    if (!quitting && mainWindow) {
      dialog.showErrorBox(
        'AURA brain stopped',
        `The brain process exited (code ${code}).\nSee log: ${logPath}`,
      )
    }
  })
  return logPath
}

function stopBrain() {
  if (brainProc && !brainProc.killed) {
    try {
      if (process.platform === 'win32') {
        // Kill the whole tree — uv spawns python underneath.
        execSync(`taskkill /pid ${brainProc.pid} /T /F`, { stdio: 'ignore' })
      } else {
        brainProc.kill('SIGTERM')
      }
    } catch { /* already gone */ }
  }
  brainProc = null
}

function waitForBrain(timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      const req = http.get(`${BRAIN_URL}/health`, { timeout: 2000 }, (res) => {
        res.resume()
        if (res.statusCode === 200) return resolve()
        retry()
      })
      req.on('error', retry)
      req.on('timeout', () => { req.destroy(); retry() })
    }
    const retry = () => {
      if (Date.now() > deadline) return reject(new Error('brain did not become healthy in time'))
      setTimeout(tryOnce, 1000)
    }
    tryOnce()
  })
}

// ---------------------------------------------------------------------------
// Static console server (same origin the brain's CORS default expects)
// ---------------------------------------------------------------------------

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
  '.json': 'application/json', '.woff2': 'font/woff2',
}

function serveConsole() {
  return new Promise((resolve, reject) => {
    staticServer = http.createServer((req, res) => {
      const urlPath = decodeURIComponent((req.url || '/').split('?')[0])
      let file = path.join(CONSOLE_DIST, urlPath === '/' ? 'index.html' : urlPath)
      if (!file.startsWith(CONSOLE_DIST) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        file = path.join(CONSOLE_DIST, 'index.html') // SPA fallback
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' })
      fs.createReadStream(file).pipe(res)
    })
    staticServer.once('error', reject)
    staticServer.listen(CONSOLE_PORT, '127.0.0.1', () => resolve())
  })
}

// ---------------------------------------------------------------------------
// Window, tray, menu
// ---------------------------------------------------------------------------

// Splash: lined bot icon (lucide "bot" path), draggable since the window is frameless.
const SPLASH_HTML = `data:text/html,
<body style="margin:0;background:%230f172a;color:%23e2e8f0;font-family:sans-serif;-webkit-app-region:drag;
display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column">
<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="%2393c5fd" stroke-width="1.5"
stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/>
<path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
<h2 style="margin:.8rem 0 0;font-weight:600">AURA is starting…</h2>
<p style="color:%2394a3b8;font-size:.9rem">brain · connectors · knowledge (encrypted)</p></body>`

function trayIcon() {
  // 16x16 robot-blue dot; a data-URL keeps the app asset-free.
  const png = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAWElEQVR4nGNgGAWMDAwM/xkYGP4TwP+JwXAD/hMLiDIAlwHYNODVjM8AbBpxGoBLIzYD8GnEMICQRnQDiNGIYgCxGlEcTaxGuAHkaCTKAGI0Yhgw8gEAoW9iEVrIZLQAAAAASUVORK5CYII='
  return nativeImage.createFromBuffer(Buffer.from(png, 'base64'))
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'AURA Operator Console',
    backgroundColor: '#0f172a',
    frame: false, // U33: the console draws its own title bar
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  })
  mainWindow.loadURL(SPLASH_HTML)
  mainWindow.on('closed', () => { mainWindow = null })

  // Window controls for the custom title bar (see preload.cjs).
  ipcMain.on('win:minimize', () => mainWindow?.minimize())
  ipcMain.on('win:toggleMaximize', () => {
    if (!mainWindow) return
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()
  })
  ipcMain.on('win:close', () => mainWindow?.close())

  const menu = Menu.buildFromTemplate([
    {
      label: 'AURA',
      submenu: [
        { label: 'Open console in browser', click: () => shell.openExternal(`http://localhost:${CONSOLE_PORT}`) },
        { label: 'Open brain API docs', click: () => shell.openExternal(`${BRAIN_URL}/docs`) },
        { label: 'Show brain log', click: () => shell.showItemInFolder(path.join(app.getPath('userData'), 'brain.log')) },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'toggleDevTools' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }] },
  ])
  Menu.setApplicationMenu(menu)

  tray = new Tray(trayIcon())
  tray.setToolTip('AURA — robot assistant')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Show console', click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } } },
    { role: 'quit' },
  ]))
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => { if (mainWindow) { mainWindow.show(); mainWindow.focus() } })

  app.whenReady().then(async () => {
    // U36e/U38: allow the console to use the laptop microphone (voice input).
    // Both handlers are needed — getUserMedia checks synchronously AND requests.
    session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => {
      cb(permission === 'media' || permission === 'microphone')
    })
    session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
      return permission === 'media' || permission === 'microphone'
    })
    createWindow()
    const logPath = startBrain()
    try {
      await serveConsole()
      await waitForBrain()
      if (mainWindow) mainWindow.loadURL(`http://localhost:${CONSOLE_PORT}`)
    } catch (err) {
      dialog.showErrorBox('AURA failed to start', `${err.message}\nBrain log: ${logPath}`)
    }
  })

  app.on('before-quit', () => { quitting = true })
  app.on('window-all-closed', () => app.quit())
  app.on('quit', () => {
    stopBrain()
    if (staticServer) staticServer.close()
  })
}
