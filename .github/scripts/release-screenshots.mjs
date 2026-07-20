/**
 * U166: release screenshots — captured from a FRESH demo stack in CI.
 *
 * Privacy by construction: the stack this points at is booted seconds earlier
 * inside the runner with the fake robot adapter (no camera), the echo LLM (no
 * API keys) and an empty in-memory knowledge store that self-seeds only the
 * fictional demo persona (Mila Kovač, U160). There is no way for personal
 * data to appear in these images because none exists in the environment.
 *
 * Best-effort: every step degrades gracefully — a missing element skips that
 * shot rather than failing the release (the release workflow treats this job
 * as optional anyway).
 *
 * Env: CONSOLE_URL (default http://localhost:4173), OUT_DIR (default ./shots).
 */

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const CONSOLE_URL = process.env.CONSOLE_URL ?? 'http://localhost:4173'
const OUT_DIR = process.env.OUT_DIR ?? 'shots'
mkdirSync(OUT_DIR, { recursive: true })

const shot = (name) => path.join(OUT_DIR, name)
const log = (msg) => console.log(`[shots] ${msg}`)

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

try {
  log(`opening ${CONSOLE_URL}`)
  await page.goto(CONSOLE_URL, { waitUntil: 'networkidle', timeout: 60_000 })

  // The console is up once the conversation panel renders.
  await page.getByText(/conversation/i).first().waitFor({ timeout: 30_000 })
  // Nice-to-have: the green "App: Connected" pill instead of "Reconnecting…".
  await page.getByText(/app: connected/i).waitFor({ timeout: 10_000 }).catch(() => {})

  // A short scripted exchange so the hero shot shows the app DOING something.
  // The echo provider answers "[echo] <text>" deterministically — no model,
  // no keys — so we can wait for that exact marker.
  try {
    const input = page.getByPlaceholder(/type a message/i)
    await input.waitFor({ timeout: 10_000 })
    await input.fill('Hello! What can you do?')
    await page.getByRole('button', { name: /^send$/i }).click()
    await page.getByText(/\[echo\]/).first().waitFor({ timeout: 30_000 })
    await page.waitForTimeout(750) // let the reply finish rendering
  } catch {
    log('chat roundtrip skipped (no reply in time) — capturing the idle app')
  }

  await page.screenshot({ path: shot('01-operator-console.png') })
  log('captured 01-operator-console.png')

  // Brain panel: people (only the shipped demo profile), skills, graph.
  // NB: the header is "<assistant name>'s brain" — AURA on a fresh install.
  try {
    const brainHeader = page.getByText(/'s brain/i).first()
    if (!(await brainHeader.isVisible().catch(() => false))) {
      await page.getByTitle(/brain panel/i).click()
      await brainHeader.waitFor({ timeout: 10_000 })
    }
    // Open the demo profile so the shot shows a filled-in digital twin.
    await page.getByText(/mila/i).first().click({ timeout: 5_000 }).catch(() => {})
    await page.waitForTimeout(1_000)
    await page.screenshot({ path: shot('02-richies-brain.png') })
    log('captured 02-richies-brain.png')
  } catch {
    log('brain panel shot skipped')
  }

  // The knowledge graph — the demo persona's [[wiki-links]] light it up.
  try {
    await page.getByText(/^graph$/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(2_500) // force layout needs a moment to settle
    await page.screenshot({ path: shot('03-knowledge-graph.png') })
    log('captured 03-knowledge-graph.png')
  } catch {
    log('graph shot skipped')
  }
} finally {
  await browser.close()
}
log('done')
