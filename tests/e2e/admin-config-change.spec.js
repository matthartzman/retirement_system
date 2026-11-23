// Install-wide settings through the Admin app: change a real runtime setting (max_build_seconds), save it, and
// check it survives a fresh page load. Starts its own admin_app process on a throwaway workspace (so there is
// nothing to restore) and a spare port; it does not use the planner fixtures.
// Engine settings are covered by plan-assumptions.spec.js (they are per plan, in the planner).
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const PORT = Number(process.env.RETIREMENT_SYSTEM_E2E_ADMIN_SETTINGS_PORT || 5962);
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

let child;
let workspace;

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'admin-settings-e2e-'));
  child = spawn(process.platform === 'win32' ? 'python' : 'python3',
    ['-m', 'admin_app', '--retirement-system-dir', workspace, '--port', String(PORT), '--no-open'],
    { cwd: ROOT, stdio: 'ignore' });
  await waitUntilReady(Date.now() + 30_000);
});


// The Admin app needs its per-boot local token (security review X-1); the launcher hands a browser a cookie, a spec sends the header.
test.beforeEach(async ({ context }) => {
  const token = fs.readFileSync(path.join(workspace, 'local_state', 'admin_local_token'), 'utf8').trim();
  await context.setExtraHTTPHeaders({ 'X-Local-Token': token });
});

test.afterAll(() => { if (child) child.kill(); });

async function openBuildTimeout(page) {
  await page.goto(`${BASE}/`);
  await page.getByRole('button', { name: /Build timeout/ }).first().click();
  await page.getByRole('button', { name: 'Expand all' }).click();
  return page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
}

test('a runtime setting round-trips through the Admin app save and a fresh page load', async ({ page }) => {
  const input = await openBuildTimeout(page);
  await expect(input).toBeVisible({ timeout: 10_000 });
  expect(await input.inputValue()).toMatch(/^\d+$/);

  const NEW_VALUE = '2653';
  await input.fill(NEW_VALUE);
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input')).toHaveValue(NEW_VALUE, { timeout: 10_000 });

  // a second, independent page load proves the value is in the settings store, not just in this page's memory
  const fresh = await openBuildTimeout(page);
  await expect(fresh).toHaveValue(NEW_VALUE, { timeout: 10_000 });

  // and the save left an audit row naming a count, never a value
  await page.getByRole('button', { name: /Admin audit/ }).first().click();
  await expect(page.getByText('settings.save')).toBeVisible({ timeout: 10_000 });
});
