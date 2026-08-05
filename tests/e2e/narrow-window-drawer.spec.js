// Wave 6.1 (system review 2026-08-04, finding `ui-narrow-window-off-fold`):
// the off-canvas nav drawer used to only kick in at true phone widths
// (<=768px). Between 769-1180px the guided-step nav instead stacked above
// the content (aside.card.side{position:static}), pushing every step's
// content down a full screen height on a narrow desktop/tablet window.
// dashboard.css now reuses the same drawer pattern up through 1180px.
import { test, expect } from '@playwright/test';
import { openCurrentPlan } from './helpers.js';

test('the off-canvas nav drawer activates on a narrow desktop window (1000px), not just phone widths', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 });
  await openCurrentPlan(page);

  const toggle = page.locator('#navToggleBtn');
  await expect(toggle, 'hamburger toggle should be visible at 1000px, previously only shown <=768px').toBeVisible();

  const sideNav = page.locator('#sideNav');
  // Closed by default: off-canvas (translated out of view), not stacked inline.
  await expect(sideNav).toHaveCSS('position', 'fixed');

  await toggle.click();
  await expect(page.locator('body')).toHaveClass(/nav-open/);
  // Open: translated fully on-screen.
  await expect(async () => {
    const matrix = await sideNav.evaluate((el) => getComputedStyle(el).transform);
    expect(matrix).toBe('matrix(1, 0, 0, 1, 0, 0)');
  }).toPass({ timeout: 2000 });

  await page.locator('#navCloseBtn').click();
  await expect(page.locator('body')).not.toHaveClass(/nav-open/);
});
