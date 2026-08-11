/**
 * One extra blog screenshot that the normal demo stack cannot produce: the
 * app's behaviour when the robot is NOT reachable. Run this with the fake
 * robot stopped — the heartbeat notices, and the console shows the diagnosis
 * plus the address field the post is about.
 *
 * Env: CONSOLE_URL, OUT_DIR.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const CONSOLE_URL = process.env.CONSOLE_URL ?? 'http://localhost:4173'
const OUT_DIR = process.env.OUT_DIR ?? 'blogshots'
mkdirSync(OUT_DIR, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
try {
  await page.goto(CONSOLE_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.getByText(/conversation/i).first().waitFor({ timeout: 30_000 })
  // The heartbeat polls on an interval; give it time to notice the robot left.
  await page.waitForTimeout(15_000)
  await page.screenshot({ path: path.join(OUT_DIR, '10-robot-offline.png') })
  console.log('[blogshots] captured 10-robot-offline.png')
} finally {
  await browser.close()
}
