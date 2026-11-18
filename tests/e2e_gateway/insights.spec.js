// Financial Insight under /insights/ in a real browser (multi-user Phase 4), through a real gateway to a real worker.
// Based on remote-mode.spec.js. Multi-user Phase 5 in a real browser, through a real gateway to a real worker (no mocks).
// Sign-in goes through the gateway's API (password, then a TOTP code); the planner is then used as a person would.
import { test as base, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const PY = process.platform === 'win32' ? 'python' : 'python3';

const test = base.extend({
  stack: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use) => {
      const child = spawn(PY, ['tools/gateway_e2e_server.py'], { cwd: ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
      const info = await new Promise((resolve, reject) => {
        let buf = '';
        const timer = setTimeout(() => reject(new Error('gateway stack did not start')), 90_000);
        child.stdout.on('data', (d) => {
          buf += d.toString();
          const line = buf.split('\n').find((l) => l.startsWith('{'));
          if (line) { clearTimeout(timer); resolve(JSON.parse(line)); }
        });
        child.on('exit', () => reject(new Error('gateway stack exited early')));
      });
      await use({ ...info, url: `http://127.0.0.1:${info.port}` });
      child.kill();
    },
    { scope: 'worker' },
  ],
  baseURL: async ({ stack }, use) => use(stack.url),
});

function totpNow(secret) {
  const code = `import time,sys;sys.path.insert(0,r'${ROOT}');from src.gateway import totp;print(totp.code_at('${secret}',int(time.time()//30)))`;
  return execFileSync(PY, ['-c', code]).toString().trim();
}

// One real sign-in per run (a TOTP code works once per 30 s step); later tests reuse the session cookie.
// The login calls run inside the page so the browser's own cookie jar keeps the gateway's session cookie.
async function signIn(page, stack) {
  if (stack.cookies) return page.context().addCookies(stack.cookies);
  await page.goto('/login');
  const result = await page.evaluate(async ({ user, password, code }) => {
    const post = async (path, body, csrf) => {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify(body) });
      return { status: r.status, body: await r.json().catch(() => ({})) };
    };
    const login = await post('/api/auth/login', { username: user, password });
    if (login.status !== 200) return login;
    return post('/api/auth/totp/verify', { code }, login.body.csrf_token);
  }, { user: stack.username, password: stack.password, code: totpNow(stack.totp_secret) });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
  stack.cookies = (await page.context().storageState()).cookies;
}

async function openPlanner(page) {
  await page.goto('/');
  await page.waitForFunction(() => window.RetirementRemote && window.RetirementRemote.enabled === true, null, { timeout: 30_000 });
}

test.describe.configure({ mode: 'serial' });

test('the planner header offers Financial Insight; it opens under /insights/ for the signed-in user', async ({ page, stack }) => {
  await signIn(page, stack);
  await openPlanner(page);
  const link = page.locator('#insightsLink');
  await expect(link).toBeVisible({ timeout: 15_000 });
  await link.click();
  await expect(page).toHaveURL(/\/insights\/$/);
  await expect(page.getByRole('heading', { name: 'Financial Insight' })).toBeVisible();
  await expect(page.locator('#workerBar')).toBeVisible();
  await expect(page.locator('#workerPlan')).not.toHaveText('');
  await expect(page.locator('#exitBtn')).toBeHidden();
});

test('first open with no history runs one update and shows the empty state for a plan with no balances', async ({ page, stack }) => {
  await signIn(page, stack);
  const runNow = [];
  page.on('request', (r) => { if (r.url().endsWith('/insights/api/run-now')) runNow.push(r.method()); });
  await page.goto('/insights/');
  await expect(page.locator('#workerEmpty')).toBeVisible({ timeout: 90_000 });
  expect(runNow.length).toBeLessThanOrEqual(1);
});

test('polling requests are marked as background; user-triggered requests are not; the Planner link returns to the planner', async ({ page, stack }) => {
  await signIn(page, stack);
  const seen = {};
  page.on('request', (r) => {
    const p = new URL(r.url()).pathname;
    if (p.startsWith('/insights/api/')) seen[p] = r.headers()['x-background-poll'] || '';
  });
  await page.goto('/insights/');
  await expect.poll(() => seen['/insights/api/ping'], { timeout: 15_000 }).toBe('1');
  await expect.poll(() => seen['/insights/api/history'], { timeout: 15_000 }).toBe('');
  await page.locator('#workerPlanner').click();
  await expect(page).not.toHaveURL(/\/insights/);
  await page.waitForFunction(() => window.RetirementRemote && window.RetirementRemote.enabled === true, null, { timeout: 30_000 });
});

test('an ended session sends the Financial Insight page to the gateway login, returning to /insights/', async ({ page, stack, context }) => {
  await signIn(page, stack);
  await page.goto('/insights/');
  await expect(page.locator('#workerBar')).toBeVisible({ timeout: 15_000 });
  await context.clearCookies();
  await expect(page).toHaveURL(/\/login\?next=\/insights\//, { timeout: 20_000 });
});

test('Sign out on the Financial Insight page ends the gateway session', async ({ page, stack }) => {
  await signIn(page, stack);
  await page.goto('/insights/');
  await page.locator('#workerSignOut').click();
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  expect((await page.request.get('/insights/')).url()).toMatch(/\/login/);
});

// The sign-in page itself (not the API): a code works once per 30 s step, so each page sign-in uses the next unused step
// (the gateway accepts one step ahead) and waits for the clock when that step is not yet allowed.
function totpForStep(secret, step) {
  const code = `import sys;sys.path.insert(0,r'${ROOT}');from src.gateway import totp;print(totp.code_at('${secret}',${step}))`;
  return execFileSync(PY, ['-c', code]).toString().trim();
}

async function signInOnThePage(page, stack, app) {
  await page.context().clearCookies();
  await page.goto('/login');
  await expect(page.locator('#app-choice')).toBeVisible({ timeout: 15_000 });
  await page.locator(`#app-choice input[value="${app}"]`).check();
  const nowStep = () => Math.floor(Date.now() / 30_000);
  const step = Math.max(nowStep() + 1, (stack.lastStep || 0) + 1);
  while (nowStep() + 1 < step) await page.waitForTimeout(1_000);
  stack.lastStep = step;
  await page.locator('#username').fill(stack.username);
  await page.locator('#password').fill(stack.password);
  await page.locator('#login-form button[type=submit]').click();
  await page.locator('#code').fill(totpForStep(stack.totp_secret, step));
  await page.locator('#code-form button[type=submit]').click();
}

test('the sign-in page lets a member choose Financial Insight or the planner, and remembers the choice', async ({ page, stack }) => {
  await signInOnThePage(page, stack, 'insights');
  await expect(page).toHaveURL(/\/insights\/$/, { timeout: 20_000 });
  await expect(page.locator('#workerBar')).toBeVisible({ timeout: 15_000 });

  await page.context().clearCookies();
  await page.goto('/login');
  await expect(page.locator('#app-choice input[value="insights"]')).toBeChecked();   // remembered in this browser
  await signInOnThePage(page, stack, 'planner');
  await expect(page).not.toHaveURL(/\/insights/, { timeout: 20_000 });
  await page.waitForFunction(() => window.RetirementRemote && window.RetirementRemote.enabled === true, null, { timeout: 30_000 });
});
