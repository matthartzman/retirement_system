// The Admin console's Users UI, hosted by the gateway at /gateway/admin, in a real browser against a real gateway.
// Admin journeys (list, add, edit role, typed-username delete, last-admin refusal), the CSP (no violations), and an
// ordinary user who must not reach any of it.
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
      await use({ ...info, url: `http://127.0.0.1:${info.port}`, cookies: {} });
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

// One real sign-in per person per run; later tests reuse that person's cookies.
async function signIn(page, stack, who) {
  const creds = who === 'admin'
    ? { user: stack.admin_username, secret: stack.admin_totp_secret }
    : { user: stack.username, secret: stack.totp_secret };
  if (stack.cookies[who]) return page.context().addCookies(stack.cookies[who]);
  await page.goto('/login');
  const result = await page.evaluate(async ({ user, password, code }) => {
    const post = async (p, body, csrf) => {
      const r = await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) }, body: JSON.stringify(body) });
      return { status: r.status, body: await r.json().catch(() => ({})) };
    };
    const login = await post('/api/auth/login', { username: user, password });
    if (login.status !== 200) return login;
    return post('/api/auth/totp/verify', { code }, login.body.csrf_token);
  }, { user: creds.user, password: stack.password, code: totpNow(creds.secret) });
  expect(result.status, JSON.stringify(result.body)).toBe(200);
  stack.cookies[who] = (await page.context().storageState()).cookies;
}

function watchCsp(page) {
  const violations = [];
  page.on('console', (m) => { if (/content security policy/i.test(m.text())) violations.push(m.text()); });
  page.on('pageerror', (e) => violations.push(`pageerror: ${e.message}`));
  return violations;
}

test.describe.configure({ mode: 'serial' });

test('an unsigned browser is sent to the login page, not shown the console or its scripts', async ({ page, request }) => {
  await page.goto('/gateway/admin');
  await expect(page).toHaveURL(/\/login/);
  const r = await request.get('/gateway/admin/static/users.js', { maxRedirects: 0 });
  expect(r.status()).toBe(302);
});

test('an admin sees the people list with no CSP violations and the gateway-only controls', async ({ page, stack }) => {
  const violations = watchCsp(page);
  await signIn(page, stack, 'admin');
  const resp = await page.goto('/gateway/admin');
  expect(resp.headers()['content-security-policy']).toContain("default-src 'self'");
  await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible();
  const table = page.locator('table').first();
  await expect(table).toContainText('Root Admin');
  await expect(table).toContainText('Carol');
  // what the gateway has no meaning for is not offered
  await expect(page.getByText('Financial Insights')).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Access' })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Expires' })).toBeVisible();
  await page.getByRole('button', { name: 'Add person' }).click();
  await expect(page.locator('dialog')).toContainText('Two-factor sign-in: required for everyone.');
  await expect(page.locator('dialog')).toContainText('Notes');
  await expect(page.locator('dialog #fExpires')).toBeVisible();
  await expect(page.locator('dialog')).toContainText('12+ characters');
  await page.getByRole('button', { name: 'Close' }).click();
  expect(violations).toEqual([]);
});

test('add a person: a short temporary password is refused, a good one creates them', async ({ page, stack }) => {
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin');
  await page.getByRole('button', { name: 'Add person' }).click();
  const dlg = page.locator('dialog');
  await dlg.locator('#fName').fill('Dana Example');
  await dlg.locator('#fUser').fill('dana');
  await dlg.locator('#fPw').fill('short-one');
  await dlg.locator('#fSave').click();
  await expect(dlg.locator('#formErr')).toContainText('at least 12 characters');
  await dlg.locator('#fPw').fill('a long enough temp password');
  await dlg.locator('#fSave').click();
  await expect(page.locator('dialog')).toBeHidden();
  await expect(page.locator('table').first()).toContainText('Dana Example');
});

test('edit: the role changes and the last admin cannot be demoted', async ({ page, stack }) => {
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin');
  await page.locator('tr', { hasText: 'Dana Example' }).getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('dialog');
  await expect(dlg.locator('#fName')).not.toHaveAttribute('readonly', '');
  await dlg.locator('#fRole').selectOption('admin');
  await dlg.locator('#fSave').click();
  await expect(page.locator('dialog')).toBeHidden();
  await expect(page.locator('tr', { hasText: 'Dana Example' })).toContainText('admin');
  // demote her again, then try to demote the only remaining admin (root): refused with the store's message
  await page.locator('tr', { hasText: 'Dana Example' }).getByRole('button', { name: 'Edit' }).click();
  await page.locator('dialog #fRole').selectOption('user');
  await page.locator('dialog #fSave').click();
  await expect(page.locator('dialog')).toBeHidden();
  await page.locator('tr', { hasText: 'Root Admin' }).getByRole('button', { name: 'Edit' }).click();
  await page.locator('dialog #fRole').selectOption('user');
  await page.locator('dialog #fSave').click();
  await expect(page.locator('dialog #formErr')).toContainText(/last active admin/i);
  await page.getByRole('button', { name: 'Close' }).click();
});

test('edit: name, notes and access end are saved, a past date shows expired, End sessions is offered', async ({ page, stack }) => {
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin');
  const row = () => page.locator('tr', { hasText: 'Dana Example' });
  await row().getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('dialog');
  await dlg.locator('#fName').fill('Dana Renamed');
  await dlg.locator('#fNotes').fill('contractor, ends in spring');
  await dlg.locator('#fExpires').fill('2020-01-01');
  await dlg.locator('#fSave').click();
  await expect(dlg).toBeHidden();
  await expect(page.locator('tr', { hasText: 'Dana Renamed' })).toContainText('expired');
  await page.locator('tr', { hasText: 'Dana Renamed' }).getByRole('button', { name: 'Edit' }).click();
  await expect(dlg.locator('#fNotes')).toHaveValue('contractor, ends in spring');
  await dlg.locator('details.acts summary').click();
  await expect(dlg.getByRole('button', { name: 'End sessions' })).toBeVisible();
  await dlg.getByRole('button', { name: 'End sessions' }).click();
  await expect(dlg).toBeHidden();
  await page.locator('tr', { hasText: 'Dana Renamed' }).getByRole('button', { name: 'Edit' }).click();
  await dlg.locator('#fExpires').fill('');
  await dlg.locator('#fName').fill('Dana Example');
  await dlg.locator('#fSave').click();
  await expect(dlg).toBeHidden();
  await expect(row()).not.toContainText('expired');
});

test('delete needs the typed username and names the data loss', async ({ page, stack }) => {
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin');
  await page.locator('tr', { hasText: 'Dana Example' }).getByRole('button', { name: 'Edit' }).click();
  const dlg = page.locator('dialog');
  await dlg.getByText('Password, sessions and removal').click();
  await expect(dlg).toContainText('permanently removes their plans and data');
  const del = dlg.locator('#fDelete');
  await expect(del).toBeDisabled();
  await dlg.locator('#fConfirmDel').fill('dan');
  await expect(del).toBeDisabled();
  await dlg.locator('#fConfirmDel').fill('dana');
  await expect(del).toBeEnabled();
  await del.click();
  await expect(page.locator('dialog')).toBeHidden();
  await expect(page.locator('table').first()).not.toContainText('Dana Example');
});

test('the audit log shows the real admin as the actor', async ({ page, stack }) => {
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin#audit');
  await expect(page.getByRole('heading', { name: 'Admin audit' })).toBeVisible();
  const row = page.locator('tr', { hasText: 'user created' }).filter({ hasText: 'dana' });
  await expect(row.first()).toContainText('root');
});

test('an ordinary user is refused the console, its scripts and its API', async ({ page, stack }) => {
  await signIn(page, stack, 'user');
  // page.goto follows redirects, so a 403 here also proves the session cookie was sent (no bounce to /login)
  for (const p of ['/gateway/admin', '/gateway/admin/static/users.js', '/gateway/users']) {
    const r = await page.goto(p);
    expect(r.status(), p).toBe(403);
  }
  const status = await page.evaluate(async () => (await fetch('/api/auth/admin/console/users')).status);
  expect(status).toBe(403);
  await page.goto('/');  // and the planner gives them no link to it
  await expect(page.locator('a[href^="/gateway/admin"]')).toHaveCount(0);
});
