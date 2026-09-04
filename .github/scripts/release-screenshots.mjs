/**
 * U166: release screenshots — captured from a FRESH demo stack.
 *
 * Privacy by construction: the stack this points at is booted seconds earlier
 * with the fake robot adapter (no camera), the echo LLM (no API keys) and an
 * empty knowledge store that self-seeds only the fictional demo persona (Mila
 * Kovač, U160). There is no way for personal data to appear in these images
 * because none exists in the environment.
 *
 * U297: it also feeds the README. Those pictures were captured by hand in
 * August and had been wrong for months — a screenshot that has to be retaken
 * by hand is a screenshot that silently rots, so the same script now produces
 * both, and `scripts/readme_shots.py` turns its output into the .webp files
 * the README points at.
 *
 * Best-effort: every shot degrades on its own — a missing element skips that
 * one image rather than failing the release, which treats this job as
 * optional anyway.
 *
 * Env:
 *   CONSOLE_URL  where the console is served (default http://localhost:4173)
 *   OUT_DIR      where the PNGs land (default ./shots)
 *   SHOTS        comma-separated shot names to capture (default: all but the
 *                ones marked `manual`, which need the stack changed first)
 */

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const CONSOLE_URL = process.env.CONSOLE_URL ?? 'http://localhost:4173'
const OUT_DIR = process.env.OUT_DIR ?? 'shots'
const ONLY = (process.env.SHOTS ?? '').split(',').map(s => s.trim()).filter(Boolean)

// The size every published screenshot has always had; the README lays them
// out at 900 and 440 CSS pixels, so this is a 2x-ish source for both.
const VIEWPORT = { width: 1600, height: 1000 }

mkdirSync(OUT_DIR, { recursive: true })
const log = (msg) => console.log(`[shots] ${msg}`)

/** Click a rail item by its visible label. */
async function goTo(page, label) {
  await page.getByRole('button', { name: new RegExp(`^${label}$`, 'i') })
    .first().click({ timeout: 10_000 })
  await page.waitForTimeout(900)
}

/**
 * Every published picture, in the order they are numbered. `manual: true`
 * marks a shot the driver will not take unless it is asked for by name,
 * because it needs the stack put into a state the happy path does not have.
 */
const SHOTS = [
  {
    name: '01-console',
    async run(page) {
      // A short scripted exchange so the hero shot shows the app DOING
      // something. The echo provider answers "[echo] <text>" deterministically
      // — no model, no keys — so we can wait for that exact marker.
      const input = page.getByPlaceholder(/message|say something/i).first()
      await input.waitFor({ timeout: 10_000 })
      await input.fill('Hello! What can you do?')
      await page.getByRole('button', { name: /^send$/i }).click()
      await page.getByText(/\[echo\]/).first().waitFor({ timeout: 30_000 })
      await page.waitForTimeout(750)   // let the reply finish rendering
    },
  },
  {
    name: '02-brain-person',
    async run(page) {
      await goTo(page, 'People')
      // The only profile a demo stack has is the fictional one.
      await page.locator('.person-row').first().click({ timeout: 10_000 })
      await page.waitForTimeout(1_200)
    },
  },
  {
    name: '03-knowledge-graph',
    async run(page) {
      await goTo(page, 'People')
      await page.locator('.person-row').first().click({ timeout: 10_000 })
      await page.getByRole('button', { name: /open graph/i })
        .first().click({ timeout: 10_000 })
      await page.waitForTimeout(3_000)  // the force layout needs to settle
    },
  },
  {
    name: '04-skills',
    async run(page) {
      await goTo(page, 'Skills')
      await page.waitForTimeout(1_200)
    },
  },
  {
    // Named for what it shows. The published picture used to be called
    // "model-roles", a section that only exists when the provider is OpenAI —
    // which a keyless demo stack never is, so the file never showed it.
    name: '05-settings',
    async run(page) {
      await goTo(page, 'Settings')
      await page.waitForTimeout(1_200)
    },
  },
  {
    // Needs the robot-runtime STOPPED, so it is a second pass:
    //   SHOTS=06-robot-offline node .github/scripts/release-screenshots.mjs
    name: '06-robot-offline',
    manual: true,
    async run(page) {
      await goTo(page, 'Robot')
      await page.waitForTimeout(2_500)  // let the connection actually fail
      // The point of this picture is the diagnosis, and the Connection card
      // only renders at "full" detail — the density dial in the header.
      await page.getByRole('group', { name: /detail level/i })
        .getByRole('button').last().click({ timeout: 10_000 })
      await page.waitForTimeout(600)
      // `scrollIntoViewIfNeeded` stops as soon as the heading is technically
      // visible, which left it on the very last pixel row. Ask for the top.
      await page.getByRole('heading', { name: /^connection$/i }).first()
        .evaluate(el => el.scrollIntoView({ block: 'start' }))
      await page.waitForTimeout(800)
    },
  },
]

const wanted = SHOTS.filter(s => (ONLY.length ? ONLY.includes(s.name) : !s.manual))
if (!wanted.length) {
  log(`nothing to capture for SHOTS=${process.env.SHOTS ?? ''}`)
  process.exit(0)
}

const browser = await chromium.launch()
try {
  for (const shot of wanted) {
    // A fresh page per shot: navigation in this console is Pinia state, not a
    // URL, so one failed click used to leave every later shot on the wrong
    // view — and they still LOOKED like screenshots, which is worse than a
    // gap. Reloading makes each picture independent of the one before it.
    const page = await browser.newPage({ viewport: VIEWPORT })
    try {
      // NOT networkidle: the console holds a WebSocket open for the event
      // stream, so the network is never idle and this waited the full timeout
      // every time. Every release for months shipped with no screenshots at
      // all — silently, because this job is allowed to fail.
      await page.goto(CONSOLE_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
      await page.getByRole('button', { name: /^talk$/i }).first()
        .waitFor({ timeout: 30_000 })
      // Nice-to-have: the green "App: Connected" pill instead of "Reconnecting…".
      await page.getByText(/app: connected/i).waitFor({ timeout: 10_000 }).catch(() => {})

      await shot.run(page)
      await page.screenshot({ path: path.join(OUT_DIR, `${shot.name}.png`) })
      log(`captured ${shot.name}.png`)
    } catch (err) {
      log(`skipped ${shot.name}: ${err.message.split('\n')[0]}`)
    } finally {
      await page.close()
    }
  }
} finally {
  await browser.close()
}
log('done')
