// Multi-user Phase 5 in a real browser, through a real gateway to a real worker (no mocks).
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

async function openSettings(page) {
  await openPlanner(page);
  await page.evaluate(() => { activeStep = 'system_configuration'; renderMain(); });
}

test.describe.configure({ mode: 'serial' });

test('an unsigned browser is sent to the gateway login page, not a broken planner', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
});

test('signed in, the planner learns it is remote and hides what the worker refuses', async ({ page, stack }) => {
  await signIn(page, stack);
  await openSettings(page);
  await expect(page.locator('html')).toHaveClass(/remote-mode/);
  await expect(page.locator('.local-backup-card')).toBeHidden();
  await expect(page.locator('.monarch-autoupdate-card')).toBeHidden();
  await expect(page.locator('.monarch-upload-card')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  // the connector is off on this gateway: the panel says so and offers no Connect button
  await expect(page.locator('#monarchConnector')).toContainText(/connect your account/i);
  await expect(page.locator('#monarchConnector').getByRole('button', { name: 'Connect', exact: true })).toHaveCount(0);
});

test('Save Plan As downloads the plan file and Load Saved Plan uploads it back', async ({ page, stack }) => {
  await signIn(page, stack);
  await openPlanner(page);
  await page.evaluate(() => { activeStep = 'start'; renderMain(); });
  const dl = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Save Plan As' }).click();
  const download = await dl;
  expect(download.suggestedFilename()).toMatch(/\.rpx$/);
  const file = path.join(os.tmpdir(), `e2e_${Date.now()}.rpx`);
  await download.saveAs(file);
  expect(fs.statSync(file).size).toBeGreaterThan(10_000);

  await page.getByRole('button', { name: 'Load Saved Plan' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Choose file' }).click();
  await (await chooser).setFiles(file);
  await expect(page.getByText(/Plan loaded from/).first()).toBeVisible({ timeout: 30_000 });
  fs.unlinkSync(file);
});

test('balances CSV: dry run first, nothing imported until confirmed', async ({ page, stack }) => {
  await signIn(page, stack);
  await openSettings(page);
  const csv = path.join(os.tmpdir(), `e2e_bal_${Date.now()}.csv`);
  // the import refuses a stale export, so the last row must be yesterday or later
  const day = (back) => new Date(Date.now() - back * 86400000).toISOString().slice(0, 10);
  fs.writeFileSync(csv, `Date,Balance,Account\n${day(2)},100.00,E2E Test Checking\n${day(1)},120.00,E2E Test Checking\n`);
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: /choose balances file/i }).click();
  await (await chooser).setFiles(csv);
  const slot = page.locator('#monarchUpload_balances');
  await expect(slot).toContainText('nothing imported yet', { timeout: 30_000 });
  await expect(slot).toContainText('2 rows');
  await slot.getByRole('button', { name: /Import 2 rows/ }).click();
  await expect(slot).toContainText(/Imported/, { timeout: 30_000 });
  fs.unlinkSync(csv);
});

test('an expired session sends the page to the login page on the next request', async ({ page, stack, context }) => {
  await signIn(page, stack);
  await openPlanner(page);
  await context.clearCookies();
  await page.evaluate(() => fetch('/api/plans').catch(() => {}));
  await expect(page).toHaveURL(/\/login\?next=/, { timeout: 15_000 });
});

test('Sign out ends the session at the gateway', async ({ page, stack }) => {
  await signIn(page, stack);
  await openPlanner(page);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  const r = await page.request.get('/api/plans');
  expect(r.status()).toBe(401);
});
