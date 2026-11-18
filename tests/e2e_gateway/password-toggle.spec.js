// Show/hide (eye) toggle on every password field of the gateway UI, in a real browser against a real gateway:
// sign-in, change-password and the Admin console's dialogs. Toggles type and label, keeps the value, hides again after
// a submit or a bfcache restore, works from the keyboard, and trips no CSP violation.
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

const eyeFor = (scope, inputSel) => scope.locator(`.pw-wrap:has(${inputSel}) button.pw-eye`);

test.describe.configure({ mode: 'serial' });

test('sign-in: the eye shows and hides the password, keeping what was typed', async ({ page }) => {
  const violations = watchCsp(page);
  await page.goto('/login');
  const input = page.locator('#password');
  const eye = eyeFor(page, '#password');
  await expect(eye).toHaveCount(1);
  await expect(eye).toHaveAttribute('type', 'button');
  await expect(eye).toHaveAccessibleName('Show password');
  await expect(eye).toHaveAttribute('aria-pressed', 'false');
  await input.fill('correct horse battery');
  await eye.click();
  await expect(input).toHaveAttribute('type', 'text');
  await expect(input).toHaveValue('correct horse battery');
  await expect(eye).toHaveAccessibleName('Hide password');
  await expect(eye).toHaveAttribute('aria-pressed', 'true');
  await eye.click();
  await expect(input).toHaveAttribute('type', 'password');
  await expect(input).toHaveValue('correct horse battery');
  await expect(eye).toHaveAccessibleName('Show password');
  expect(violations).toEqual([]);
});

test('the eye works from the keyboard (Space and Enter) and is the next tab stop after its field', async ({ page }) => {
  await page.goto('/login');
  await page.locator('#password').focus();
  await page.keyboard.press('Tab');
  await expect(eyeFor(page, '#password')).toBeFocused();
  await page.keyboard.press('Space');
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
  await page.keyboard.press('Enter');
  await expect(page.locator('#password')).toHaveAttribute('type', 'password');
});

test('sign-in: after a failed submit the password is hidden again', async ({ page }) => {
  await page.goto('/login');
  await page.locator('#username').fill('nobody');
  await page.locator('#password').fill('wrong wrong wrong');
  await eyeFor(page, '#password').click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.locator('#status')).not.toHaveText('');
  await expect(page.locator('#password')).toHaveAttribute('type', 'password');
  await expect(eyeFor(page, '#password')).toHaveAccessibleName('Show password');
  await expect(eyeFor(page, '#password')).toHaveAttribute('aria-pressed', 'false');
});

test('a page restored from the back/forward cache comes back hidden', async ({ page }) => {
  await page.goto('/login');
  await page.locator('#password').fill('secret value 123');
  await eyeFor(page, '#password').click();
  await expect(page.locator('#password')).toHaveAttribute('type', 'text');
  await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
  await expect(page.locator('#password')).toHaveAttribute('type', 'password');
  await expect(page.locator('#password')).toHaveValue('secret value 123');
});

test('the value is never written to storage, the URL or the console', async ({ page }) => {
  const logs = [];
  page.on('console', (m) => logs.push(m.text()));
  await page.goto('/login');
  await page.locator('#password').fill('needle-value-xyz');
  await eyeFor(page, '#password').click();
  const stored = await page.evaluate(() => JSON.stringify([localStorage, sessionStorage, document.cookie, location.href]));
  expect(stored).not.toContain('needle-value-xyz');
  expect(logs.join('\n')).not.toContain('needle-value-xyz');
});

test('change password: all three fields get an eye, and a refused submit hides them again', async ({ page, stack }) => {
  await signIn(page, stack, 'user');
  await page.goto('/gateway/account');
  for (const id of ['#current', '#new', '#confirm']) {
    await expect(eyeFor(page, id)).toHaveCount(1);
    await eyeFor(page, id).click();
    await expect(page.locator(id)).toHaveAttribute('type', 'text');
  }
  await page.locator('#current').fill('whatever it was');
  await page.locator('#new').fill('a brand new password 1');
  await page.locator('#confirm').fill('a different password 2');
  await page.getByRole('button', { name: 'Change password' }).click();
  await expect(page.locator('#status')).toContainText('do not match');
  for (const id of ['#current', '#new', '#confirm']) {
    await expect(page.locator(id)).toHaveAttribute('type', 'password');
    await expect(eyeFor(page, id)).toHaveAccessibleName('Show password');
  }
  await expect(page.locator('#new')).toHaveValue('a brand new password 1');
});

test('Admin console: create-person and reset-password fields have an eye and hide after a refused save', async ({ page, stack }) => {
  const violations = watchCsp(page);
  await signIn(page, stack, 'admin');
  await page.goto('/gateway/admin');
  await page.getByRole('button', { name: 'Add person' }).click();
  const dlg = page.locator('dialog');
  await expect(eyeFor(dlg, '#fPw')).toHaveCount(1);
  await dlg.locator('#fName').fill('Eve Example');
  await dlg.locator('#fUser').fill('eve');
  await dlg.locator('#fPw').fill('short-one');
  await eyeFor(dlg, '#fPw').click();
  await expect(dlg.locator('#fPw')).toHaveAttribute('type', 'text');
  await expect(dlg.locator('#fPw')).toHaveValue('short-one');
  await dlg.locator('#fSave').click();
  await expect(dlg.locator('#formErr')).toContainText('at least 12 characters');
  await expect(dlg.locator('#fPw')).toHaveAttribute('type', 'password');
  await page.getByRole('button', { name: 'Close' }).click();
  // the reset-password field in the Edit dialog
  await page.locator('tr', { hasText: 'Carol' }).getByRole('button', { name: 'Edit' }).click();
  await page.locator('dialog').getByText('Maintenance').click();
  const reset = eyeFor(page.locator('dialog'), '#fResetPw');
  await expect(reset).toHaveCount(1);
  await page.locator('dialog #fResetPw').fill('too short');
  await reset.click();
  await expect(page.locator('dialog #fResetPw')).toHaveAttribute('type', 'text');
  await page.locator('dialog').getByRole('button', { name: 'Reset password' }).click();
  await expect(page.locator('dialog #formErr')).toContainText('at least 12 characters');
  await expect(page.locator('dialog #fResetPw')).toHaveAttribute('type', 'password');
  expect(violations).toEqual([]);
});
