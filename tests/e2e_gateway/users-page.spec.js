// The gateway's /gateway/users page behaves like the Admin console's Users page: a table with one Edit button
// per person, an Add person / Edit dialog with an Account section, and a collapsible
// "Password, sessions and removal" section. Real gateway, real browser, no mocks.
import { test as base, expect } from '@playwright/test';
import { spawn, execFileSync } from 'node:child_process';
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

async function signInAdmin(page, stack) {
  if (stack.cookies) return page.context().addCookies(stack.cookies);
  await page.goto('/login');
  const a = stack.admin;
  const result = await page.evaluate(async ({ user, password, code }) => {
    const post = async (p, body, csrf) => {
      const r = await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify(body) });
      return { status: r.status, body: await r.json().catch(() => ({})) };
    };
    const login = await post('/api/auth/login', { username: user, password });
    if (login.status !== 200) return login;
    return post('/api/auth/totp/verify', { code }, login.body.csrf_token);
  }, { user: a.username, password: a.password, code: totpNow(a.totp_secret) });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
  stack.cookies = (await page.context().storageState()).cookies;
}

const row = (page, username) => page.locator('#users-body tr', { has: page.locator('td', { hasText: new RegExp(`^${username}$`) }) });

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page, stack }) => {
  await signInAdmin(page, stack);
  await page.goto('/gateway/users');
  await expect(row(page, 'carol')).toBeVisible();
});

test('the list has one Edit button per person, and no per-row action buttons', async ({ page }) => {
  await expect(page.getByRole('button', { name: 'Add person' })).toBeVisible();
  await expect(page.locator('#users-body tr')).toHaveCount(2);
  await expect(row(page, 'carol').getByRole('button')).toHaveCount(1);
  await expect(row(page, 'carol').getByRole('button', { name: 'Edit' })).toBeVisible();
  await expect(row(page, 'carol')).toContainText('User');
  await expect(row(page, 'alice')).toContainText('Administrator');
});

test('Edit opens a dialog with Account fields and a collapsed actions section', async ({ page }) => {
  await row(page, 'carol').getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('#user-dialog');
  await expect(dlg).toBeVisible();
  await expect(dlg.getByRole('heading', { name: 'Edit Carol' })).toBeVisible();
  await expect(dlg.locator('#u-username')).toHaveValue('carol');
  await expect(dlg.locator('#u-username')).toHaveAttribute('readonly', '');
  await expect(dlg.locator('#u-role')).toHaveValue('user');
  await expect(dlg.locator('#u-temp')).toBeHidden();
  const acts = dlg.locator('details.acts');
  await expect(acts).not.toHaveAttribute('open', '');
  await acts.locator('summary').click();
  await expect(acts.getByRole('button', { name: 'Reset password' })).toBeVisible();
  await expect(acts.getByRole('button', { name: 'Reset two-factor' })).toBeVisible();
  await expect(acts.getByRole('button', { name: 'Disable' })).toBeVisible();
  await expect(acts.getByRole('button', { name: 'Delete' })).toBeVisible();
  await dlg.getByRole('button', { name: 'Close' }).click();
  await expect(dlg).toBeHidden();
});

test('Add person creates a user from the dialog', async ({ page }) => {
  await page.getByRole('button', { name: 'Add person' }).click();
  const dlg = page.locator('#user-dialog');
  await expect(dlg.getByRole('heading', { name: 'Add person' })).toBeVisible();
  await expect(dlg.locator('details.acts')).toBeHidden();
  await dlg.locator('#u-display').fill('Dave Jones');
  await dlg.locator('#u-username').fill('dave');
  await dlg.locator('#u-temp').fill('short');
  await dlg.locator('#u-save').click();
  await expect(dlg.locator('#form-err')).toContainText('12');
  await dlg.locator('#u-temp').fill('a long temporary password');
  await dlg.locator('#u-save').click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'dave')).toContainText('Dave Jones');
});

test('Save applies a role change; the last administrator cannot be demoted', async ({ page }) => {
  await row(page, 'dave').getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('#user-dialog');
  await dlg.locator('#u-role').selectOption('admin');
  await dlg.locator('#u-save-top').click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'dave')).toContainText('Administrator');
  await row(page, 'dave').getByRole('button', { name: 'Edit' }).click();
  await dlg.locator('#u-role').selectOption('user');
  await dlg.locator('#u-save').click();
  await expect(dlg).toBeHidden();
  // alice is now the only administrator: demoting her must be refused.
  await row(page, 'alice').getByRole('button', { name: 'Edit' }).click();
  await dlg.locator('#u-role').selectOption('user');
  await dlg.locator('#u-save').click();
  await expect(dlg.locator('#form-err')).not.toHaveText('');
  await expect(dlg).toBeVisible();
  await dlg.getByRole('button', { name: 'Close' }).click();
  await expect(row(page, 'alice')).toContainText('Administrator');
});

test('Disable asks for confirmation, then shows the status tag; Enable undoes it', async ({ page }) => {
  await row(page, 'carol').getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('#user-dialog');
  await dlg.locator('details.acts summary').click();
  page.once('dialog', (d) => d.dismiss());
  await dlg.getByRole('button', { name: 'Disable' }).click();
  await expect(dlg).toBeVisible();
  page.once('dialog', (d) => d.accept());
  await dlg.getByRole('button', { name: 'Disable' }).click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'carol').locator('.tag.bad')).toHaveText('disabled');
  await row(page, 'carol').getByRole('button', { name: 'Edit' }).click();
  await dlg.locator('details.acts summary').click();
  await dlg.getByRole('button', { name: 'Enable' }).click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'carol').locator('.tag.bad')).toHaveCount(0);
});

test('Reset password uses the inline field and enforces the length', async ({ page }) => {
  await row(page, 'carol').getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('#user-dialog');
  await dlg.locator('details.acts summary').click();
  await dlg.getByRole('button', { name: 'Reset password' }).click();
  await expect(dlg.locator('#form-err')).toContainText('12');
  await dlg.locator('#u-reset').fill('another long password');
  await dlg.getByRole('button', { name: 'Reset password' }).click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'carol')).toContainText('must change');
});

test('Delete asks for confirmation and removes the person', async ({ page }) => {
  await row(page, 'dave').getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('#user-dialog');
  await dlg.locator('details.acts summary').click();
  page.once('dialog', (d) => d.accept());
  await dlg.getByRole('button', { name: 'Delete' }).click();
  await expect(dlg).toBeHidden();
  await expect(row(page, 'dave')).toHaveCount(0);
});
