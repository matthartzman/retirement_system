// Per-worker isolated backend server (E2E efficiency review, 2026-09-15,
// recommendation R3).
//
// Before this file existed, playwright.config.js's `webServer` started ONE
// tools/e2e_server.py process, shared by every test in the suite
// (`fullyParallel: false, workers: 1` existed specifically because of this
// sharing). helpers.js documents, in detail, the class of bug that produced:
// a second spec's real build leaving `liabilitiesChanged`/`dirty` in a state
// the next spec didn't expect, races between one spec's loadAll() and
// another spec's navigation, etc. Eleven of tests/e2e/helpers.js's commits
// in the last 3 months were root-causing exactly this category of failure,
// not a genuine app bug.
//
// The fix is to stop sharing: each Playwright WORKER gets its own
// tools/e2e_server.py process on its own port, backed by its own throwaway
// workspace (e2e_server.py already stages a fresh tempdir per invocation --
// no change needed there). Tests within one worker still run sequentially
// against that worker's server (a real build genuinely mutates shared
// server-side state), but different workers now run fully in parallel
// against independent backends, and no spec can leak state into another
// spec running under a different worker.
import { test as base, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const BASE_PORT = Number(process.env.RETIREMENT_SYSTEM_E2E_PORT || 5951);
// tools/e2e_server.py does not build anything at startup (see its own
// module docstring for why) -- this only covers Python interpreter startup
// and Flask/http.server binding the port, which is fast. The real build
// cost is paid lazily, per worker, by helpers.js's ensureWorkbookBuilt().
const READY_TIMEOUT_MS = 30_000;

function pollUntilReady(url, deadline) {
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });
      req.on('error', () => {
        if (Date.now() > deadline) {
          reject(new Error(`e2e server never answered at ${url} within the startup deadline`));
        } else {
          setTimeout(attempt, 500);
        }
      });
      req.setTimeout(2_000, () => req.destroy());
    };
    attempt();
  });
}

export const test = base.extend({
  // Worker-scoped: one server (and one call to pollUntilReady) per worker
  // process, shared by every test that worker runs, not per test.
  workerServerUrl: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, use, workerInfo) => {
      const port = BASE_PORT + workerInfo.workerIndex;
      const url = `http://127.0.0.1:${port}`;

      const child = spawn(process.platform === 'win32' ? 'python' : 'python3', ['tools/e2e_server.py'], {
        cwd: ROOT,
        env: { ...process.env, RETIREMENT_SYSTEM_E2E_PORT: String(port) },
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      const output = [];
      child.stdout.on('data', (d) => output.push(d.toString()));
      child.stderr.on('data', (d) => output.push(d.toString()));
      let exited = false;
      child.on('exit', (code) => {
        exited = true;
        if (code !== 0 && code !== null) {
          // eslint-disable-next-line no-console
          console.error(`[worker ${workerInfo.workerIndex}] e2e server exited early (code ${code}):\n${output.join('')}`);
        }
      });

      try {
        await pollUntilReady(url, Date.now() + READY_TIMEOUT_MS);
      } catch (err) {
        if (exited) {
          throw new Error(`${err.message}\n\nServer output:\n${output.join('')}`);
        }
        throw err;
      }

      await use(url);

      child.kill();
    },
    { scope: 'worker' },
  ],

  // Playwright's own `baseURL` fixture is test-scoped and can't be
  // re-registered at worker scope directly -- overriding it here (still at
  // its default test scope) to simply read the worker-scoped server URL
  // above is what actually makes `page.goto('/')` transparently target THIS
  // worker's own server, with no change needed at any spec's call sites.
  baseURL: async ({ workerServerUrl }, use) => {
    await use(workerServerUrl);
  },
});

export { expect };
