/**
 * Blog screenshots — captured from the same FRESH demo stack the release
 * screenshots use (U166): fake robot adapter, echo LLM, isolated skills vault
 * and database, and an in-memory knowledge store seeded only with the
 * fictional demo persona. No camera, no keys, no real profile can be present.
 *
 * Wider set than the release shots, because a blog post needs the specific
 * screen its paragraph is about. Every step degrades gracefully — a missing
 * element skips that shot and logs why, rather than failing the run.
 *
 * Env: CONSOLE_URL (default http://localhost:4173), OUT_DIR (default ./blogshots)
 */

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const CONSOLE_URL = process.env.CONSOLE_URL ?? 'http://localhost:4173'
const OUT_DIR = process.env.OUT_DIR ?? 'blogshots'
mkdirSync(OUT_DIR, { recursive: true })

const shot = (n) => path.join(OUT_DIR, n)
const log = (m) => console.log(`[blogshots] ${m}`)
const taken = []

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })

async function capture(name, fn) {
  try {
    await fn()
    await page.screenshot({ path: shot(name) })
    taken.push(name)
    log(`captured ${name}`)
  } catch (err) {
    log(`SKIPPED ${name} — ${err.message.split('\n')[0]}`)
  }
}

try {
  // The console holds a WebSocket open for the event stream, so the network is
  // never idle. Wait for content instead.
  await page.goto(CONSOLE_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.getByText(/conversation/i).first().waitFor({ timeout: 30_000 })
  await page.getByText(/app: connected/i).waitFor({ timeout: 10_000 }).catch(() => {})

  // --- 01: the assistant answering, for the opening post -------------------
  await capture('01-conversation.png', async () => {
    const input = page.getByPlaceholder(/type a message/i)
    await input.waitFor({ timeout: 10_000 })
    await input.fill('Who is in the room?')
    await page.getByRole('button', { name: /^send$/i }).click()
    await page.getByText(/\[echo\]/).first().waitFor({ timeout: 30_000 })
    await page.waitForTimeout(800)
  })

  // --- 06: the brain — a person with facts and observed signals ------------
  await capture('06-brain-person.png', async () => {
    const header = page.getByText(/'s brain/i).first()
    if (!(await header.isVisible().catch(() => false))) {
      await page.getByTitle(/brain panel/i).click()
      await header.waitFor({ timeout: 10_000 })
    }
    await page.getByText(/mila/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(1_200)
  })

  // --- 06b: the knowledge graph -------------------------------------------
  await capture('06b-knowledge-graph.png', async () => {
    await page.getByText(/^graph$/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(2_500)
  })

  // --- 06c: the skills library — approved standing instructions ------------
  await capture('06c-skills.png', async () => {
    await page.getByText(/skills library/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(1_200)
  })

  // --- 08: the model role selectors ---------------------------------------
  // They only render for a provider that HAS roles; the demo stack runs the
  // echo provider, so switch the dropdown to reveal them. No key is needed —
  // the lists come back empty, which is honest and is what the post discusses.
  await capture('08-model-roles.png', async () => {
    await page.getByTitle(/settings/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(800)
    const provider = page.locator('select').first()
    await provider.selectOption({ label: /openai/i }).catch(async () => {
      await provider.selectOption({ index: 0 })
    })
    await page.waitForTimeout(1_500)
  })

  // --- 10: the robot panel, where the address field lives ------------------
  await capture('10-robot-panel.png', async () => {
    await page.keyboard.press('Escape').catch(() => {})
    await page.waitForTimeout(400)
    await page.getByTitle(/robot/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(1_200)
  })

  // --- 05: the app log, where the loops report what they did --------------
  await capture('05-app-logs.png', async () => {
    await page.keyboard.press('Escape').catch(() => {})
    await page.waitForTimeout(400)
    await page.getByText(/app logs/i).first().click({ timeout: 5_000 })
    await page.waitForTimeout(1_200)
  })

  // --- 06d: the brain panel on its own, cropped, for the learning post -----
  await capture('06d-brain-panel-only.png', async () => {
    const header = page.getByText(/'s brain/i).first()
    if (!(await header.isVisible().catch(() => false))) {
      await page.getByTitle(/brain panel/i).click()
      await header.waitFor({ timeout: 10_000 })
    }
    await page.getByText(/mila/i).first().click({ timeout: 5_000 }).catch(() => {})
    await page.waitForTimeout(1_200)
    // element shot: just the panel, so the post shows the profile not the app
    const panel = page.locator('aside, [class*="brain"]').last()
    await panel.screenshot({ path: shot('06d-brain-panel-only.png') })
    throw new Error('__captured__')  // element shot already written
  })
} finally {
  await browser.close()
}

log(`done — ${taken.length} shots: ${taken.join(', ')}`)
