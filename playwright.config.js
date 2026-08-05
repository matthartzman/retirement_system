// Playwright browser E2E suite (system review 2026-08-04, finding
// `no-browser-execution-testing`): the frontend has ~810 functions and zero
// real DOM/browser coverage. `tests/frontend/*.test.mjs` exercises a handful
// of pure functions in a Node vm sandbox; this is the layer that catches a
// broken onclick handler, a JS exception on render, or a navigation dead end
// -- none of which a string match or a sandboxed pure-function call can see.
//
// webServer below owns the whole server lifecycle: it runs
// tools/e2e_server.py (which stages an isolated, frozen-fixture workspace and
// calls the same run_local_server() primitive main.py uses, without
// main.py's own unconditional webbrowser.open() side effect), polls the URL
// until it answers, and tears the process down when the run ends.
import { defineConfig, devices } from '@playwright/test';

const PORT = process.env.RETIREMENT_SYSTEM_E2E_PORT || '5951';
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './tests/e2e',
  // The build journey (J2) alone waits up to 80s for a real Monte Carlo
  // build to finish (see helpers.js triggerBuildAndWaitForOverlay's own
  // comment on why); this must clear that plus the rest of the test.
  timeout: 120_000,
  fullyParallel: false, // shares one server instance; specs run in file order
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: `python tools/e2e_server.py`,
    url: BASE_URL,
    env: { RETIREMENT_SYSTEM_E2E_PORT: PORT },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
