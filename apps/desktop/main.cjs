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

const { app, BrowserWindow, Menu, Tray, dialog, globalShortcut, ipcMain, screen, session, shell, nativeImage } = require('electron')
const { spawn, execSync } = require('child_process')
const http = require('http')
const fs = require('fs')
const path = require('path')

// U37-installer: a packaged (NSIS) install carries the Python workspace under
// resources/aura and the built console under resources/console; a dev checkout
// runs straight from the repo.
const IS_PACKAGED = app.isPackaged
const REPO_ROOT = IS_PACKAGED
  ? path.join(process.resourcesPath, 'aura')
  : path.resolve(__dirname, '..', '..')
const CONSOLE_DIST = IS_PACKAGED
  ? path.join(process.resourcesPath, 'console')
  : path.join(REPO_ROOT, 'apps', 'operator-console', 'dist')
// U177: ALL owner state lives OUTSIDE the install directory.
//
// It used to sit under resources/aura (.env, data/, skills/) — inside the
// folder the NSIS installer replaces on every update. Updating therefore
// wiped the knowledge store, face embeddings, memory DB, learned skills AND
// the knowledge passphrase. userData (%APPDATA%/aura-desktop) survives
// updates and uninstall-then-reinstall.
//
// Dev checkouts keep the old repo-relative paths — a dev run must not read
// or clobber the installed app's real data.
const USER_ROOT = IS_PACKAGED ? app.getPath('userData') : REPO_ROOT
const DATA_DIR = IS_PACKAGED
  ? path.join(USER_ROOT, 'data')
  : path.join(REPO_ROOT, 'data')
const SKILLS_DIR = path.join(IS_PACKAGED ? USER_ROOT : REPO_ROOT, 'skills')
const ENV_FILE = IS_PACKAGED
  ? path.join(USER_ROOT, '.env')
  : path.join(REPO_ROOT, 'infra', 'dev', '.env')
// Where those files used to live — migrated once, on the next launch.
const LEGACY_ENV_FILE = path.join(REPO_ROOT, 'infra', 'dev', '.env')
const LEGACY_DATA_DIR = path.join(REPO_ROOT, 'data')
const LEGACY_SKILLS_DIR = path.join(REPO_ROOT, 'skills')

/** Copy pre-U177 owner state out of the install dir, once. Never overwrites. */
function migrateLegacyState() {
  if (!IS_PACKAGED) return
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true })
    if (!fs.existsSync(ENV_FILE) && fs.existsSync(LEGACY_ENV_FILE)) {
      fs.copyFileSync(LEGACY_ENV_FILE, ENV_FILE)
    }
    if (fs.existsSync(LEGACY_DATA_DIR)) {
      for (const name of fs.readdirSync(LEGACY_DATA_DIR)) {
        const dest = path.join(DATA_DIR, name)
        const src = path.join(LEGACY_DATA_DIR, name)
        if (!fs.existsSync(dest) && fs.statSync(src).isFile()) fs.copyFileSync(src, dest)
      }
    }
    if (!fs.existsSync(SKILLS_DIR) && fs.existsSync(LEGACY_SKILLS_DIR)) {
      fs.cpSync(LEGACY_SKILLS_DIR, SKILLS_DIR, { recursive: true })
    }
  } catch (err) {
    console.error('legacy state migration failed (continuing):', err.message)
  }
}

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
  // U177: persist everything under userData, so an update can never wipe it.
  // Explicit values from .env still win (the || below), but the DEFAULTS are
  // no longer relative paths that land inside the install directory.
  const posix = (p) => p.replace(/\\/g, '/')
  env.AURA_ENV_FILE = ENV_FILE                    // where prefs/wizard write
  env.KNOWLEDGE_DB_PATH = env.KNOWLEDGE_DB_PATH || path.join(DATA_DIR, 'knowledge.enc.json')
  env.RECOGNITION_DB_PATH = env.RECOGNITION_DB_PATH || path.join(DATA_DIR, 'recognition.enc.json')
  env.DATABASE_URL = env.DATABASE_URL || `sqlite+aiosqlite:///${posix(path.join(DATA_DIR, 'aura-memory.db'))}`
  env.SKILLS_DIR = env.SKILLS_DIR || SKILLS_DIR
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
// First-run bootstrap (U37-installer): a packaged install needs uv + a synced
// Python environment before the brain can start. Dev checkouts skip this.
// ---------------------------------------------------------------------------

function hasUv() {
  try { execSync('uv --version', { stdio: 'ignore', shell: true }); return true }
  catch { return false }
}

async function ensureBootstrap(splashWindow) {
  if (!IS_PACKAGED) return
  const marker = path.join(app.getPath('userData'), '.bootstrap-done')
  if (fs.existsSync(marker) && hasUv()) return

  const say = (msg) => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.webContents.executeJavaScript(
        `document.querySelector('h2').textContent = ${JSON.stringify(msg)}`,
      ).catch(() => {})
    }
  }

  if (!hasUv()) {
    say('Installing the Python runtime (one-time)…')
    // Official uv installer; puts uv on the user PATH for future runs.
    // U166: per-platform — the PowerShell one-liner only exists on Windows,
    // so the macOS/Linux installers could never bootstrap.
    if (process.platform === 'win32') {
      execSync('powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"',
        { stdio: 'ignore', shell: true, timeout: 300_000 })
      // Current process PATH doesn't pick up the new location automatically.
      process.env.PATH = `${process.env.USERPROFILE}\\.local\\bin;${process.env.PATH}`
    } else {
      execSync('curl -LsSf https://astral.sh/uv/install.sh | sh',
        { stdio: 'ignore', shell: true, timeout: 300_000 })
      process.env.PATH = `${process.env.HOME}/.local/bin:${process.env.PATH}`
    }
    if (!hasUv()) throw new Error('uv installation failed — install it from https://astral.sh/uv and restart AURA')
  }

  say('Preparing AURA (one-time, a few minutes)…')
  execSync('uv sync --all-packages', { cwd: REPO_ROOT, stdio: 'ignore', shell: true, timeout: 900_000 })
  fs.writeFileSync(marker, new Date().toISOString())
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
// U75: screen-control overlay — glowing ring that follows the mouse + an
// abort banner while AURA drives the screen. Click-through, always on top.
// ---------------------------------------------------------------------------

let overlayWin = null
let overlayTimer = null

const OVERLAY_HTML = `data:text/html;charset=utf-8,
<body style="margin:0;background:transparent;overflow:hidden;font-family:sans-serif">
<div id="banner" style="position:fixed;top:10px;left:50%%;transform:translateX(-50%%);
background:rgba(15,23,42,.92);color:%23e2e8f0;border:1px solid %2360a5fa;border-radius:999px;
padding:8px 18px;font-size:13px;display:flex;gap:10px;align-items:center;box-shadow:0 4px 24px rgba(59,130,246,.35)">
<span style="width:9px;height:9px;border-radius:50%%;background:%2360a5fa;
box-shadow:0 0 10px %2360a5fa;animation:pulse 1.1s infinite"></span>
AURA bestuurt het scherm &mdash; druk <b>&nbsp;Esc&nbsp;</b> om af te breken</div>
<div id="ring" style="position:fixed;width:46px;height:46px;border-radius:50%%;
border:3px solid %2360a5fa;box-shadow:0 0 18px 4px rgba(96,165,250,.65), inset 0 0 12px rgba(96,165,250,.5);
transform:translate(-50%%,-50%%);pointer-events:none;animation:pulse 1.1s infinite"></div>
<style>@keyframes pulse{0%%,100%%{opacity:.95}50%%{opacity:.45}}</style>
<script>
require===undefined;
window.addEventListener('message',()=>{});
const {ipcRenderer} = window.electron||{};
</script>
<script>
  // cursor positions arrive via executeJavaScript from the main process
  window.__setCursor = (x, y) => {
    const r = document.getElementById('ring')
    r.style.left = x + 'px'; r.style.top = y + 'px'
  }
</script></body>`

function showOverlay() {
  if (overlayWin) return
  const { width, height } = screen.getPrimaryDisplay().bounds
  overlayWin = new BrowserWindow({
    width, height, x: 0, y: 0,
    frame: false, transparent: true, alwaysOnTop: true, skipTaskbar: true,
    focusable: false, hasShadow: false, resizable: false,
    webPreferences: { sandbox: true },
  })
  overlayWin.setIgnoreMouseEvents(true)
  overlayWin.setAlwaysOnTop(true, 'screen-saver')
  overlayWin.loadURL(OVERLAY_HTML)
  overlayTimer = setInterval(() => {
    if (!overlayWin) return
    const p = screen.getCursorScreenPoint()
    overlayWin.webContents.executeJavaScript(
      `window.__setCursor && window.__setCursor(${p.x}, ${p.y})`, true,
    ).catch(() => {})
  }, 40)
  // Esc aborts the run (global — works whatever app has focus).
  globalShortcut.register('Escape', () => {
    const req = http.request({ host: 'localhost', port: BRAIN_PORT, method: 'POST',
      path: '/orchestrator/computeruse/abort' })
    req.on('error', () => {})
    req.end()
  })
}

function hideOverlay() {
  if (overlayTimer) { clearInterval(overlayTimer); overlayTimer = null }
  globalShortcut.unregister('Escape')
  if (overlayWin) { overlayWin.destroy(); overlayWin = null }
}

ipcMain.on('aura:screen-control', (_e, active) => {
  if (active) showOverlay()
  else hideOverlay()
})

// ---------------------------------------------------------------------------
// Window, tray, menu
// ---------------------------------------------------------------------------

// Splash: lined bot icon (lucide "bot" path), draggable since the window is
// frameless. charset=utf-8 + HTML entities so the ellipsis/middot render
// correctly (a plain data: URL mis-decodes them as Latin-1).
const SPLASH_HTML = `data:text/html;charset=utf-8,
<body style="margin:0;background:%230f172a;color:%23e2e8f0;font-family:sans-serif;-webkit-app-region:drag;
display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column">
<svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="%2393c5fd" stroke-width="1.5"
stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/>
<path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
<h2 style="margin:.8rem 0 0;font-weight:600">AURA is starting&hellip;</h2>
<p style="color:%2394a3b8;font-size:.9rem">brain &middot; connectors &middot; knowledge (encrypted)</p></body>`

function trayIcon() {
  // U171: the real app icon (Reachy silhouette), scaled for the tray — the
  // old hardcoded base64 "blue dot" predates having an icon at all.
  const img = nativeImage.createFromPath(path.join(__dirname, 'build', 'icon.png'))
  return img.isEmpty() ? img : img.resize({ width: 16, height: 16 })
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

  // U170: links with target=_blank (About dialog → mityjohn.com, GitHub) open
  // in the SYSTEM browser — never as a second Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) shell.openExternal(url)
    return { action: 'deny' }
  })

  // Window controls for the custom title bar (see preload.cjs).
  ipcMain.on('win:minimize', () => mainWindow?.minimize())
  ipcMain.on('win:toggleMaximize', () => {
    if (!mainWindow) return
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()
  })
  ipcMain.on('win:close', () => mainWindow?.close())

  // U95: restart the brain child process (loads new code / config) without
  // quitting the whole app. The console calls this via the preload bridge.
  // U170: version for the About dialog.
  ipcMain.handle('aura:app-version', () => app.getVersion())

  // U178: manual "check for updates" from the About dialog. Unlike the
  // background check this REPORTS its outcome — including "can't reach the
  // private repo", which is why automatic checking looked broken.
  ipcMain.handle('aura:check-update', async () => {
    if (!IS_PACKAGED) return { status: 'dev' }
    const result = await checkForUpdate({ currentVersion: app.getVersion(), token: updateToken() })
    if (result.status === 'update') setTimeout(() => maybeOfferUpdate(), 300)
    return result
  })

  ipcMain.handle('aura:restart-brain', async () => {
    try {
      stopBrain()
      await new Promise((r) => setTimeout(r, 1200))  // let the tree die
      startBrain()
      await waitForBrain()
      return { ok: true }
    } catch (err) {
      return { ok: false, error: String(err && err.message || err) }
    }
  })

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
// U173: update check — ask the owner when a newer GitHub release exists
// ---------------------------------------------------------------------------

const { checkForUpdate, downloadAsset } = require('./updater.cjs')
let updateDialogOpen = false

function skippedVersionFile() { return path.join(app.getPath('userData'), 'update-skip.json') }

function skippedVersion() {
  try { return JSON.parse(fs.readFileSync(skippedVersionFile(), 'utf-8')).skip } catch { return null }
}

function updateToken() {
  return loadEnvFile(ENV_FILE).GITHUB_TOKEN || process.env.GITHUB_TOKEN || ''
}

async function maybeOfferUpdate() {
  if (updateDialogOpen || !mainWindow) return
  const result = await checkForUpdate({ currentVersion: app.getVersion(), token: updateToken() })
  const update = result.status === 'update' ? result.update : null
  if (!update || update.tag === skippedVersion()) return

  updateDialogOpen = true
  try {
    const canAutoInstall = process.platform === 'win32' && !!update.asset
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Update beschikbaar',
      message: `AURA ${update.version} is beschikbaar (je gebruikt ${app.getVersion()}).`,
      detail: canAutoInstall
        ? 'De installer wordt gedownload en gestart; je instellingen blijven staan.'
        : 'De releasepagina wordt geopend zodat je de nieuwe versie kunt downloaden.',
      buttons: canAutoInstall
        ? ['Download & installeer', 'Later', 'Deze versie overslaan']
        : ['Open releasepagina', 'Later', 'Deze versie overslaan'],
      defaultId: 0, cancelId: 1,
    })
    if (response === 2) {
      fs.writeFileSync(skippedVersionFile(), JSON.stringify({ skip: update.tag }))
      return
    }
    if (response !== 0) return

    if (canAutoInstall) {
      try {
        const dest = path.join(app.getPath('temp'), update.asset.name)
        await downloadAsset({ asset: update.asset, token, destPath: dest })
        await shell.openPath(dest)      // NSIS wizard takes over
        quitting = true
        setTimeout(() => app.quit(), 1200)
        return
      } catch (err) {
        console.error('update download failed, opening release page instead:', err.message)
      }
    }
    shell.openExternal(update.htmlUrl)  // fallback: manual download
  } finally {
    updateDialogOpen = false
  }
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
    let logPath = ''
    try {
      migrateLegacyState()               // U177: rescue pre-userData state
      await ensureBootstrap(mainWindow)  // packaged first run: uv + sync
      logPath = startBrain()
      await serveConsole()
      await waitForBrain()
      if (mainWindow) mainWindow.loadURL(`http://localhost:${CONSOLE_PORT}`)
    } catch (err) {
      dialog.showErrorBox('AURA failed to start', `${err.message}${logPath ? `\nBrain log: ${logPath}` : ''}`)
    }
    // U173: releases ship continuously — tell the owner when a newer one
    // exists. First check after startup settles, then every 4 hours.
    if (IS_PACKAGED) {
      setTimeout(() => { maybeOfferUpdate() }, 30_000)
      setInterval(() => { maybeOfferUpdate() }, 4 * 60 * 60 * 1000)
    }
  })

  app.on('before-quit', () => { quitting = true })
  app.on('window-all-closed', () => app.quit())
  app.on('quit', () => {
    hideOverlay()
    stopBrain()
    if (staticServer) staticServer.close()
  })
}
