// Remote-mode journeys against a REAL gateway plus a real per-user worker (tools/gateway_e2e_server.py).
// Separate from playwright.config.js: the main suite runs a desktop-mode server and must stay that way.
// Run: npx playwright test -c playwright.gateway.config.js
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e_gateway',
  timeout: 120_000,
  workers: 1, // one gateway, one signed-in user, tests share the worker's plan
  fullyParallel: false,
  reporter: 'list',
  use: { trace: 'on-first-retry', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 900 } } }],
});
