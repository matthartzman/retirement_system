// Admin app (port 5056 in production; a spare port here): add a person, then change their access grants.
// Starts its own admin_app process on a throwaway workspace, so it does not use the planner fixtures.
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const PORT = Number(process.env.RETIREMENT_SYSTEM_E2E_ADMIN_PORT || 5961);
const BASE = `http://127.0.0.1:${PORT}`;

function waitUntilReady(deadline) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(`${BASE}/api/ping`, (res) => { res.resume(); resolve(); });
      req.on('error', () => (Date.now() > deadline ? reject(new Error('admin app never answered')) : setTimeout(attempt, 300)));
      req.setTimeout(2_000, () => req.destroy());
    };
    attempt();
  });
}

// One worker, in order: both tests share this process and the person the first one adds.
test.describe.configure({ mode: 'serial' });

let child;
let workspace;

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'admin-e2e-'));
  child = spawn(process.platform === 'win32' ? 'python' : 'python3',
    ['-m', 'admin_app', '--retirement-system-dir', workspace, '--port', String(PORT), '--no-open'],
    { cwd: ROOT, stdio: 'ignore' });
  await waitUntilReady(Date.now() + 30_000);
});

test.afterAll(() => {
  if (child) child.kill();
  if (workspace) fs.rmSync(workspace, { recursive: true, force: true });
});

test('add a person with Financial Insights access, then change their grants', async ({ page }) => {
  await page.goto(`${BASE}/#users`);
  await expect(page.getByRole('heading', { name: 'Users', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add person' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('#fName').fill('Ann Example');
  await dialog.locator('#fUser').fill('Ann');
  await dialog.locator('#fPw').fill('correct horse battery');
  await dialog.locator('#gMoney').selectOption('percent');
  await dialog.getByRole('button', { name: 'Add person' }).click();

  const row = page.locator('tr[data-user]', { hasText: 'ann' });
  await expect(row).toContainText('Ann Example');
  await expect(row).toContainText('Financial Insights');
  await expect(row).toContainText('Percent');
  await expect(row).toContainText('must change password');

  // Grants: switch to dollars, limit to the Live view, and add Retirement Planner.
  await row.getByRole('button', { name: 'Edit' }).click();
  await dialog.locator('#gMoney').selectOption('dollars');
  await dialog.locator('[data-view="trends"]').uncheck();
  await dialog.locator('[data-view="projections"]').uncheck();
  await dialog.locator('#gPlanner').check();
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(dialog).toBeHidden();
  await expect(row).toContainText('Dollars');
  await expect(row).toContainText('Retirement Planner');

  // The saved grant came back from the server, and each change reached the audit.
  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(dialog.locator('[data-view="live"]')).toBeChecked();
  await expect(dialog.locator('[data-view="trends"]')).not.toBeChecked();
  await dialog.getByRole('button', { name: 'Close' }).click();
  await page.goto(`${BASE}/#audit`);
  await expect(page.locator('tbody')).toContainText('user.add');
  await expect(page.locator('tbody')).toContainText('grant.set');
});

test('a duplicate username is refused with a visible message', async ({ page }) => {
  await page.goto(`${BASE}/#users`);
  await page.getByRole('button', { name: 'Add person' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('#fName').fill('Ann Again');
  await dialog.locator('#fUser').fill('ann');
  await dialog.locator('#fPw').fill('correct horse battery');
  await dialog.getByRole('button', { name: 'Add person' }).click();
  await expect(dialog.locator('#formErr')).toContainText('already in use');
});
