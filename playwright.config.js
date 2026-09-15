// Playwright browser E2E suite (system review 2026-08-04, finding
// `no-browser-execution-testing`): the frontend has ~810 functions and zero
// real DOM/browser coverage. `tests/frontend/*.test.mjs` exercises a handful
// of pure functions in a Node vm sandbox; this is the layer that catches a
// broken onclick handler, a JS exception on render, or a navigation dead end
// -- none of which a string match or a sandboxed pure-function call can see.
//
// E2E efficiency review (2026-09-15), recommendation R3: this used to start
// ONE shared tools/e2e_server.py via `webServer` below, with every spec
// (fullyParallel: false, workers: 1) racing to mutate the same server-side
// plan. tests/e2e/fixtures.js now starts one isolated server+workspace PER
// WORKER instead (a worker-scoped `baseURL` fixture), so there is no
// `webServer` entry here any more -- each spec file imports `test`/`expect`
// from './fixtures.js' rather than '@playwright/test' directly, and that
// import is what actually starts its worker's server. See fixtures.js for
// why this specific class of bug (documented at length across
// tests/e2e/helpers.js's git history) motivated the change.
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  // The build journey (J2) alone waits up to 80s for a real Monte Carlo
  // build to finish (see helpers.js triggerBuildAndWaitForOverlay's own
  // comment on why); this must clear that plus the rest of the test.
  // Individual build-triggering specs (and ensureWorkbookBuilt() callers
  // whose worker hasn't built a workbook yet) raise this further with their
  // own test.setTimeout() for the real build they end up running.
  timeout: 120_000,
  fullyParallel: true, // safe now: each worker has its own isolated server
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // GitHub-hosted windows-latest runners have 2 cores; each worker also
  // spawns its own Python backend (plus, for the workers that draw a
  // build-triggering spec, a real ~110s workbook build), so an unbounded
  // worker count would oversubscribe the runner rather than help it. Local
  // dev machines typically have more cores, so leave it to Playwright's own
  // default (CPU count) there.
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
