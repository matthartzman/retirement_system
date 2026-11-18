// Phase 9 shared view in a real browser, through a real gateway (--shared-views) and the owner's real worker.
// The owner shares and previews; the guest signs in with TOTP and sees the percent view; revoke then reload shows
// "not available"; Back after sign-out shows no data. Fails on any CSP violation (C24, C26, AC-7, AC-9).
// Run: npx playwright test -c playwright.gateway.config.js tests/e2e_gateway/shared-view.spec.js
import { test as base, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const PY = process.platform === 'win32' ? 'python' : 'python3';
const NOT_AVAILABLE = 'This view is not available. Ask the person who shared it with you.';

const test = base.extend({
  stack: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use) => {
      const child = spawn(PY, ['tools/gateway_e2e_server.py', '--shared-views'], { cwd: ROOT, stdio: ['ignore', 'pipe', 'inherit'] });
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

// Every page in this spec records CSP violations; the test fails on any.
async function watchCsp(page) {
  const violations = [];
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      (window.__csp = window.__csp || []).push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
  page.on('console', (m) => { if (/Content Security Policy/i.test(m.text())) violations.push(m.text()); });
  return async () => {
    const inPage = await page.evaluate(() => window.__csp || []).catch(() => []);
    return [...violations, ...inPage];
  };
}

async function signIn(page, username, password, secret) {
  await page.goto('/login');
  const result = await page.evaluate(async ({ user, password: pw, code }) => {
    const post = async (p, body, csrf) => {
      const r = await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify(body) });
      return { status: r.status, body: await r.json().catch(() => ({})) };
    };
    const login = await post('/api/auth/login', { username: user, password: pw });
    if (login.status !== 200) return login;
    return post('/api/auth/totp/verify', { code }, login.body.csrf_token);
  }, { user: username, password, code: totpNow(secret) });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
}

test.describe.configure({ mode: 'serial' });

test('owner shares a percent view, guest sees it, revoke ends it, Back after sign-out shows nothing', async ({ browser, stack }) => {
  // ---- the owner ----
  const ownerCtx = await browser.newContext();
  const owner = await ownerCtx.newPage();
  const ownerCsp = await watchCsp(owner);
  await signIn(owner, stack.username, stack.password, stack.totp_secret);
  // FI's first open runs one update, which gives the percent view its basis (the plan's net worth).
  await owner.goto('/insights/');
  await expect(owner.getByRole('heading', { name: 'Financial Insight' })).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => owner.evaluate(async () => (await (await fetch('/insights/api/history')).json()).length),
    { timeout: 90_000 }).toBeGreaterThan(0);
  // The FI header offers Share... to a member when the gateway's shared views are on.
  await expect(owner.locator('#workerShare')).toBeVisible({ timeout: 15_000 });
  await owner.click('#workerShare');
  await expect(owner).toHaveURL(/\/gateway\/sharing$/);
  await expect(owner.locator('#plan-line')).toContainText('Plan:', { timeout: 15_000 });
  await expect(owner.locator('#f-viewer option')).toHaveCount(1);
  await owner.fill('#f-title', 'For Vera');
  await owner.click('#f-publish');
  await expect(owner.locator('#sharing-status')).toHaveText('Published.', { timeout: 90_000 });
  await expect(owner.locator('#preview')).toContainText('Amounts are shown as a percent of net worth');
  await expect(owner.locator('#share-table')).toContainText('For Vera');

  // ---- the guest ----
  const guestCtx = await browser.newContext();
  const guest = await guestCtx.newPage();
  const guestCsp = await watchCsp(guest);
  await signIn(guest, stack.viewer_username, stack.password, stack.viewer_totp_secret);
  await guest.goto('/');
  await expect(guest).toHaveURL(/\/gateway\/viewer$/);  // a viewer's "/" is the guest page
  const main = guest.locator('#viewer-main');
  await expect(main).toContainText('Shared by Carol', { timeout: 15_000 });
  await expect(main).toContainText('For Vera');
  await expect(main).toContainText('Amounts are shown as a percent of net worth');
  await expect(main).not.toContainText('$');
  for (const tab of ['Snapshot', 'Trends', 'Projections']) await expect(guest.getByRole('button', { name: tab })).toBeVisible();
  // The planner, FI and the admin console are not there for a guest.
  for (const p of ['/api/plans', '/insights/api/history', '/api/auth/admin/users', '/api/share/list']) {
    expect(await guest.evaluate(async (u) => (await fetch(u)).status, p)).toBe(404);
  }

  // ---- revoke, then the guest reloads ----
  owner.once('dialog', (d) => d.accept());
  await owner.getByRole('button', { name: 'Revoke' }).click();
  await expect(owner.locator('#share-table')).toContainText('Nothing is shared yet.', { timeout: 15_000 });
  await guest.reload();
  await expect(main).toHaveText(NOT_AVAILABLE, { timeout: 15_000 });
  expect(await guest.evaluate(async () => (await fetch('/api/viewer/shares')).json())).toEqual({ success: true, shares: [] });

  // ---- a second share, then sign out and go Back ----
  await owner.fill('#f-title', 'Second look');
  await owner.click('#f-publish');
  await expect(owner.locator('#sharing-status')).toHaveText(/Published\.|refreshed less than a minute/, { timeout: 90_000 });
  await guest.reload();
  await expect(main).toContainText('Second look', { timeout: 15_000 });
  await guest.click('#logout');
  await expect(guest).toHaveURL(/\/login/, { timeout: 15_000 });
  await guest.goBack();
  await expect(guest.locator('body')).not.toContainText('Second look', { timeout: 15_000 });
  await expect(guest.locator('body')).not.toContainText('Shared by Carol');

  expect(await ownerCsp()).toEqual([]);
  expect(await guestCsp()).toEqual([]);
  await ownerCtx.close();
  await guestCtx.close();
});

test('an admin adds a viewer in the Admin console; no planner is made for it', async ({ browser, stack }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const csp = await watchCsp(page);
  await signIn(page, stack.admin_username, stack.password, stack.admin_totp_secret);
  await page.goto('/gateway/admin#users');
  await page.getByRole('button', { name: 'Add viewer' }).click();
  await page.fill('#vName', 'Adam Advisor');
  await page.fill('#vUser', 'adam');
  await page.fill('#vPw', 'a temporary password 22');
  await page.selectOption('#vSponsor', { label: 'Carol' });
  await page.locator('#viewerForm button[type=submit]').click();
  const row = page.locator('tr', { hasText: 'Adam Advisor' });
  await expect(row).toContainText('Viewer', { timeout: 15_000 });
  await expect(row).toContainText('for Carol');
  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.locator('#fRole')).toBeDisabled();
  expect(await csp()).toEqual([]);
  await ctx.close();
});
