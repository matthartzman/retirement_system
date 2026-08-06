// Wave 6.3 (system review 2026-08-04, finding `ui-inconsistent-wide-table-pattern`):
// the widest transaction/lot tables (YTD Transactions, Investment Holdings)
// get a pinned identifying column (stays visible while scrolling horizontally)
// and a collapsible "extra" column group (secondary columns hidden by default,
// toggle button reveals them) instead of every column scrolling together.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('YTD Transactions table pins its first column and collapses secondary columns by default', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'ytd_transactions', 'Actual Spending (This Year)');

  const wrap = page.locator('.ytd-tx-table-wrap');
  await expect(wrap).toHaveClass(/pinned-col/);
  await expect(wrap).toHaveClass(/cols-collapsed/);

  const toggle = page.locator('.col-group-toggle').first();
  await expect(toggle).toHaveText('Show all columns');

  const firstTh = page.locator('.ytd-tx-table th').first();
  await expect(firstTh).toHaveCSS('position', 'sticky');

  const extraCell = page.locator('.ytd-tx-table [data-col-group="extra"]').first();
  await expect(extraCell).toBeHidden();

  await toggle.click();
  await expect(wrap).not.toHaveClass(/cols-collapsed/);
  await expect(toggle).toHaveText('Hide extra columns');
  await expect(extraCell).toBeVisible();
});

test('Investment Holdings table pins its first column', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'holdings', 'Investment Holdings');

  const wrap = page.locator('.holdings .lot-table-wrap').first();
  await expect(wrap).toHaveClass(/pinned-col/);

  const firstTh = wrap.locator('.lot-table th').first();
  await expect(firstTh).toHaveCSS('position', 'sticky');
});
