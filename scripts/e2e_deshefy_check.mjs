/**
 * Headless check that the Deshefy session UI tabs populate on production.
 * Usage: E2E_PASSWORD=... node scripts/e2e_deshefy_check.mjs
 */
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.APP_URL || 'https://cme-analysis-platform-official.vercel.app';
const USERNAME = process.env.E2E_USERNAME || 'tim@injurytrialattorneys.com';
const PASSWORD = process.env.E2E_PASSWORD;
const SESSION = 'cme_89f184bd4e80';
const SHOTS = '/tmp/deshefy_shots';
fs.mkdirSync(SHOTS, { recursive: true });

if (!PASSWORD) {
  console.error('Set E2E_PASSWORD env var');
  process.exit(2);
}

const results = [];
const consoleErrors = [];
const failedRequests = [];

function record(step, ok, detail = '') {
  results.push({ step, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${step}${detail ? ' — ' + detail : ''}`);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 300));
});
page.on('response', (res) => {
  if (res.status() >= 400) {
    failedRequests.push(`${res.request().method()} ${res.url().slice(0, 160)} -> HTTP ${res.status()}`);
  }
});

async function shot(name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

async function clickTab(...labels) {
  for (const label of labels) {
    const tab = page.getByRole('tab', { name: new RegExp(label, 'i') }).first();
    if ((await tab.count()) > 0) {
      await tab.click();
      await page.waitForTimeout(2500);
      return;
    }
    const btn = page.locator(`button:has-text("${label}")`).first();
    if ((await btn.count()) > 0) {
      await btn.click();
      await page.waitForTimeout(2500);
      return;
    }
  }
  throw new Error(`No tab found for: ${labels.join(', ')}`);
}

try {
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  await page.fill('#username', USERNAME);
  await page.fill('#password', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(2000);
  record('login succeeds', !page.url().includes('/login'), page.url());

  await page.goto(`${BASE}/sessions/${SESSION}`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(4000);
  const body = await page.textContent('body');
  record('session header shows Deshefy', /deshefy/i.test(body || ''));
  await shot('01_landing');

  // Report vs video tab
  await clickTab('Main issues', 'Report vs video');
  await page.waitForTimeout(3000);
  const testsPanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('verdict rows render', /supported|contradicted|not shown|not in report/i.test(testsPanel || ''), `${(testsPanel || '').trim().length} chars`);
  record('cross-exam prompts present', /doctor, page \d|show me on the video|cross-examination/i.test(testsPanel || ''));
  record('no Osborne/Scammon contamination (tests)', !/scammon|osborn/i.test(testsPanel || ''));
  const video = page.locator('video').first();
  record('video element present', (await video.count()) > 0);
  await shot('02_report_vs_video');

  // timestamp chip
  const chip = page.locator('button').filter({ hasText: /^\d{1,2}:\d{2}$/ }).first();
  if ((await chip.count()) > 0) {
    const chipLabel = (await chip.textContent())?.trim();
    await chip.click();
    await page.waitForTimeout(2500);
    const cur = await page.locator('video').first().evaluate((v) => v.currentTime).catch(() => -1);
    const [m, s] = chipLabel.split(':').map(Number);
    const target = m * 60 + s;
    record('timestamp chip seeks video', Math.abs(cur - target) < 6, `chip=${chipLabel} video=${cur.toFixed(1)}s`);
  } else {
    record('timestamp chip seeks video', false, 'no chip found');
  }

  // Analysis tab
  await clickTab('Analysis');
  const analysisPanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('analysis tab renders findings', /technique|behavior|examination quality|issues identified/i.test(analysisPanel || ''), `${(analysisPanel || '').trim().length} chars`);
  record('no "structured JSON unavailable" warning', !/structured json summaries are unavailable/i.test(analysisPanel || ''));
  await shot('03_analysis');

  // Timeline tab
  await clickTab('Timeline');
  const timelinePanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('timeline tab renders report', /examination timeline|full report/i.test(timelinePanel || ''), `${(timelinePanel || '').trim().length} chars`);
  await shot('04_timeline');

  // Overview tab
  await clickTab('Overview');
  const overviewPanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('overview shows analysis complete', /analysis complete/i.test(overviewPanel || ''));
  record('overview PDF report available', /report|pdf/i.test(overviewPanel || ''));
  await shot('05_overview');

  // Materials tab (video playback)
  await clickTab('Materials');
  await page.waitForTimeout(2500);
  const matVideo = page.locator('video').first();
  const hasVid = (await matVideo.count()) > 0;
  record('materials video present', hasVid);
  if (hasVid) {
    const played = await matVideo.evaluate(async (v) => {
      v.muted = true;
      try { await v.play(); } catch (e) { return { err: String(e) }; }
      const t0 = v.currentTime;
      await new Promise((r) => setTimeout(r, 3000));
      v.pause();
      return { t0, t1: v.currentTime };
    });
    record('materials video plays', played.t1 > played.t0, JSON.stringify(played));
  }
  await shot('06_materials');
} catch (e) {
  record('UNCAUGHT', false, String(e).slice(0, 400));
  await shot('99_error');
}

console.log('\n--- console errors (' + consoleErrors.length + ') ---');
[...new Set(consoleErrors)].slice(0, 10).forEach((e) => console.log('  ', e));
console.log('--- failed requests (' + failedRequests.length + ') ---');
[...new Set(failedRequests)].slice(0, 10).forEach((e) => console.log('  ', e));
const failures = results.filter((r) => !r.ok);
console.log(`\nRESULT: ${results.length - failures.length}/${results.length} passed`);
await browser.close();
process.exit(failures.length ? 1 : 0);
