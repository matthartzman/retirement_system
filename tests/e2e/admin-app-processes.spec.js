// Admin app "App settings" panel: app status with port and pid, start / stop, and the live sessions list with end-session.
// Starts its own admin_app on a throwaway workspace and a seeded identity store. Start and stop are answered by a
// stateful mock so the spec never launches (or kills) a real Planner or Financial Insights on the developer's PC;
// the real routes are covered by tests/test_admin_app_processes_functional.py. Sessions come from the real server.
import { test, expect } from '@playwright/test';
import { execFileSync, spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const PORT = Number(process.env.RETIREMENT_SYSTEM_E2E_ADMIN_PROCESSES_PORT || 5962);
const BASE = `http://127.0.0.1:${PORT}`;
const PY = process.platform === 'win32' ? 'python' : 'python3';

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

test.describe.configure({ mode: 'serial' });

let child;
let workspace;

test.beforeAll(async () => {
  workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'admin-proc-e2e-'));
  execFileSync(PY, ['-c', [
    'import sys, time',
    'from src.identity import IdentityStore',
    'from pathlib import Path',
    's = IdentityStore(Path(sys.argv[1]) / "local_state" / "identity.db", scrypt_n=2**4)',
    'uid = s.add_user("Pat Example", "pat", "correct horse battery", insights=True)',
    's.register_session("tok", uid, "insights", "remote", "203.0.113.7", now=time.time() - 120)',
  ].join('\n'), workspace], { cwd: ROOT });
  child = spawn(PY, ['-m', 'admin_app', '--retirement-system-dir', workspace, '--port', String(PORT), '--no-open'],
    { cwd: ROOT, stdio: 'ignore' });
  await waitUntilReady(Date.now() + 30_000);
});


// The Admin app needs its per-boot local token (security review X-1); the launcher hands a browser a cookie, a spec sends the header.
test.beforeEach(async ({ context }) => {
  const token = fs.readFileSync(path.join(workspace, 'local_state', 'admin_local_token'), 'utf8').trim();
  await context.setExtraHTTPHeaders({ 'X-Local-Token': token });
});

test.afterAll(() => {
  if (child) child.kill();
  if (workspace) fs.rmSync(workspace, { recursive: true, force: true });
});

test('status panel shows state, port and pid; Start and Stop post the app name', async ({ page }) => {
  const running = { planner: false, insights: true };
  const posts = [];
  const app = (name, label, port) => ({
    name, label, port, state: running[name] ? 'running' : 'stopped', running: running[name],
    pid: running[name] ? 4242 : null, managed: running[name], extra_ports: [],
  });
  await page.route('**/api/processes', (route) => route.fulfill({
    json: { success: true, apps: [app('planner', 'Retirement Planner', 5050), app('insights', 'Financial Insights', 5057)],
      admin: { label: 'Admin app', pid: 999, port: PORT, state: 'running' } },
  }));
  await page.route('**/api/processes/*', (route) => {
    const name = route.request().postDataJSON().app;
    posts.push([route.request().url().split('/').pop(), name]);
    running[name] = route.request().url().endsWith('/start');
    route.fulfill({ json: { success: true } });
  });

  await page.goto(`${BASE}/#sys-app_settings`);
  const planner = page.locator('#procApps tr', { hasText: 'Retirement Planner' });
  const insights = page.locator('#procApps tr', { hasText: 'Financial Insights' });
  await expect(planner).toContainText('stopped');
  await expect(planner).toContainText('5050');
  await expect(insights).toContainText('running');
  await expect(insights).toContainText('4242');
  await expect(page.locator('#procApps tr', { hasText: 'Admin app' })).toContainText('999');

  await planner.getByRole('button', { name: 'Start' }).click();
  await expect(planner).toContainText('running');
  expect(posts).toEqual([['start', 'planner']]);

  await insights.getByRole('button', { name: 'Stop' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Stop' }).click();
  await expect(insights).toContainText('stopped');
  expect(posts[1]).toEqual(['stop', 'insights']);
});

test('live sessions list who is signed in, and End sessions removes the row and is audited', async ({ page }) => {
  await page.route('**/api/processes', (route) => route.fulfill({ json: { success: true, apps: [], admin: null } }));
  await page.goto(`${BASE}/#sys-app_settings`);
  const row = page.locator('#procSessions tr', { hasText: 'Pat Example' });
  await expect(row).toContainText('Financial Insights');
  await expect(row).toContainText('Remote 203.0.113.7');

  await row.getByRole('button', { name: 'End sessions' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'End sessions' }).click();
  await expect(page.locator('#procSessions')).toContainText('Nobody is signed in');

  await page.goto(`${BASE}/#audit`);
  await expect(page.getByText('session.end')).toBeVisible();
});
