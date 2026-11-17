// Plan assumptions (the planner's engine settings, edited with the shared settings renderer).
// Read-only: it opens each page and checks the rows render; it saves nothing to the plan.
import { test, expect } from './fixtures.js';

test('the five plan-assumption pages open from /plan-assumptions and render their settings', async ({ page }) => {
  await page.goto('/plan-assumptions');
  await page.waitForLoadState('networkidle');
  for (const title of ['Capital market assumptions', 'Asset correlations', 'Tax modeling', 'Global rebalancing controls', 'Annuity calibration']) {
    await page.getByRole('button', { name: new RegExp(title) }).first().click();
    await expect(page.locator('#main h2')).toHaveText(title, { timeout: 10_000 });
    await page.getByRole('button', { name: 'Expand all' }).click();
    await expect(page.locator('#main tr input.cfg-input, #main tr select.cfg-select').first()).toBeVisible({ timeout: 10_000 });
  }
});

test('/admin hands off instead of serving the old console', async ({ page }) => {
  const resp = await page.goto('/admin');
  expect(resp.status()).toBe(200);
  await expect(page.getByRole('heading', { name: /Admin app/ })).toBeVisible();
});
