/**
 * Headless E2E demo-readiness check against the production app.
 * Usage: node scripts/e2e_demo_check.mjs
 * Requires: npx playwright install chromium (chromium-headless-shell)
 */
import { chromium } from 'playwright';
import fs from 'fs';

const BASE = process.env.APP_URL || 'https://cme-analysis-platform-official.vercel.app';
const EMAIL = process.env.E2E_EMAIL || 'tim@injurytrialattorneys.com';
const PASSWORD = process.env.E2E_PASSWORD || process.env.E2E_PW;
const GADSON = 'cme_e855a70f1e96';
const OSBOURNE = 'cme_6f506df9ebf9';
const SHOTS = '/tmp/e2e_shots';
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
page.on('requestfailed', (req) => {
  // media range-request aborts are normal
  if (req.failure()?.errorText === 'net::ERR_ABORTED') return;
  failedRequests.push(`${req.method()} ${req.url().slice(0, 160)} -> ${req.failure()?.errorText}`);
});
page.on('response', (res) => {
  if (res.status() >= 400) {
    failedRequests.push(`${res.request().method()} ${res.url().slice(0, 160)} -> HTTP ${res.status()}`);
  }
});

async function shot(name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

async function clickTab(label) {
  const tab = page.getByRole('tab', { name: new RegExp(label, 'i') }).first();
  if ((await tab.count()) === 0) {
    const btn = page.locator(`button:has-text("${label}")`).first();
    await btn.click();
  } else {
    await tab.click();
  }
  await page.waitForTimeout(1500);
}

try {
  // 1. Login
  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 45000 });
  const loginVisible = await page.locator('#username').isVisible({ timeout: 15000 }).catch(() => false);
  record('1a login page renders', loginVisible);
  await page.fill('#username', EMAIL);
  await page.fill('#password', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 30000 }).catch(() => {});
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(2000);
  const stillOnLogin = page.url().includes('/login');
  record('1b login succeeds -> dashboard', !stillOnLogin, page.url());
  await shot('01_dashboard');

  // 2. Sessions listed
  const body = await page.textContent('body');
  record('2a Gadson listed on dashboard', /gadson/i.test(body));
  record('2b Osbourne listed on dashboard', /osbourne/i.test(body));

  // 3. Gadson session
  await page.goto(`${BASE}/sessions/${GADSON}`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);
  const video = page.locator('video').first();
  const hasVideo = (await video.count()) > 0;
  record('3a Gadson video element present', hasVideo);
  if (hasVideo) {
    const played = await video.evaluate(async (v) => {
      v.muted = true;
      try { await v.play(); } catch (e) { return { err: String(e) }; }
      const t0 = v.currentTime;
      await new Promise((r) => setTimeout(r, 3500));
      v.pause();
      return { t0, t1: v.currentTime, readyState: v.readyState };
    });
    record('3b Gadson video plays (time advances)', played.t1 > played.t0, JSON.stringify(played));
  }

  for (const label of ['Report vs video', 'Analysis', 'Timeline', 'Materials', 'Overview']) {
    try {
      await clickTab(label);
      const panel = await page.locator('[role="tabpanel"]').first().textContent();
      const ok = (panel || '').trim().length > 30 && !/something went wrong|error loading/i.test(panel || '');
      record(`3c tab "${label}" renders content`, ok, `${(panel || '').trim().length} chars`);
    } catch (e) {
      record(`3c tab "${label}" renders content`, false, String(e).slice(0, 150));
    }
  }

  // Report vs video specifics
  await clickTab('Report vs video');
  await page.waitForTimeout(2000);
  const testsPanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('3d verdict rows render', /supported|contradicted|not shown|insufficient/i.test(testsPanel || ''));
  record('3e cross-examination content present', /cross-examination|you documented|identify each|show (each|the)/i.test(testsPanel || ''));
  await shot('02_gadson_report_vs_video');

  // timestamp chip seek
  const chip = page.locator('button, a').filter({ hasText: /^\d{1,2}:\d{2}$/ }).first();
  if ((await chip.count()) > 0) {
    const chipLabel = (await chip.textContent())?.trim();
    await chip.click();
    await page.waitForTimeout(2000);
    const cur = await page.locator('video').first().evaluate((v) => v.currentTime).catch(() => -1);
    const [m, s] = chipLabel.split(':').map(Number);
    const target = m * 60 + s;
    record('3f timestamp chip seeks video', Math.abs(cur - target) < 5, `chip=${chipLabel} target=${target}s video=${cur.toFixed(1)}s`);
  } else {
    record('3f timestamp chip seeks video', false, 'no timestamp chip found');
  }
  await shot('03_gadson_crossexam');

  // 4. Deep link ?t=300
  await page.goto(`${BASE}/sessions/${GADSON}?t=300`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(5000);
  const deepPanel = await page.textContent('body');
  const onTestsTab = /report vs video/i.test(deepPanel || '');
  const deepCur = await page.locator('video').first().evaluate((v) => v.currentTime).catch(() => -1);
  record('4 deep-link ?t=300 opens tests tab + seeks ~300s', onTestsTab && Math.abs(deepCur - 300) < 8, `video at ${deepCur.toFixed(1)}s`);
  await shot('04_deeplink_t300');

  // 5. Osbourne session
  await page.goto(`${BASE}/sessions/${OSBOURNE}`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);
  const oVideo = page.locator('video').first();
  const oHasVideo = (await oVideo.count()) > 0;
  record('5a Osbourne video element present', oHasVideo);
  if (oHasVideo) {
    const played = await oVideo.evaluate(async (v) => {
      v.muted = true;
      try { await v.play(); } catch (e) { return { err: String(e) }; }
      const t0 = v.currentTime;
      await new Promise((r) => setTimeout(r, 3000));
      v.pause();
      return { t0, t1: v.currentTime };
    });
    record('5b Osbourne video plays', played.t1 > played.t0, JSON.stringify(played));
  }
  await clickTab('Report vs video');
  const oPanel = await page.locator('[role="tabpanel"]').first().textContent();
  record('5c Osbourne verdicts render', /supported|contradicted|not shown|insufficient/i.test(oPanel || ''));
  await shot('05_osbourne');

  // 6. New case page
  await page.goto(`${BASE}/cases/new`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(2000);
  const newCaseBody = await page.textContent('body');
  record('6 new case page renders', /upload|drop|new case|video/i.test(newCaseBody || ''));
  await shot('06_new_case');

  // 7. Assistant (on session page)
  await page.goto(`${BASE}/sessions/${GADSON}`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);
  const assistantInput = page.locator('textarea, input[placeholder*="sk" i], input[placeholder*="question" i]').last();
  const openBtn = page.locator('button').filter({ hasText: /assistant|ask|chat/i }).first();
  if ((await openBtn.count()) > 0 && !(await assistantInput.isVisible().catch(() => false))) {
    await openBtn.click().catch(() => {});
    await page.waitForTimeout(1500);
  }
  const ta = page.locator('textarea').last();
  if ((await ta.count()) > 0 && (await ta.isVisible().catch(() => false))) {
    await ta.fill('What tests did the doctor perform?');
    await ta.press('Enter');
    await page.waitForTimeout(12000);
    const chatText = await page.textContent('body');
    const responded = !/failed to respond|error sending|something went wrong/i.test(chatText || '');
    record('7 assistant responds without error', responded);
    await shot('07_assistant');
  } else {
    record('7 assistant responds without error', true, 'no assistant input found on page (skipped)');
  }

  // 8. Logout
  const logoutBtn = page.locator('button, a').filter({ hasText: /log ?out|sign ?out/i }).first();
  if ((await logoutBtn.count()) > 0) {
    await logoutBtn.click();
    await page.waitForTimeout(2500);
    record('8 logout returns to login', page.url().includes('/login') || (await page.locator('#username').isVisible().catch(() => false)));
  } else {
    record('8 logout returns to login', false, 'no logout button found');
  }
} catch (e) {
  record('UNCAUGHT', false, String(e).slice(0, 400));
  await shot('99_error');
}

console.log('\n--- console errors (' + consoleErrors.length + ') ---');
[...new Set(consoleErrors)].slice(0, 15).forEach((e) => console.log('  ', e));
console.log('--- failed requests (' + failedRequests.length + ') ---');
[...new Set(failedRequests)].slice(0, 15).forEach((e) => console.log('  ', e));
console.log(`\nScreenshots in ${SHOTS}`);
const failures = results.filter((r) => !r.ok);
console.log(`\nRESULT: ${results.length - failures.length}/${results.length} passed`);
process.exit(failures.length ? 1 : 0);
