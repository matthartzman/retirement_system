// Wave 6.2 (system review 2026-08-04, finding `ui-spending-domain-fragmentation`):
// Spending Model, Actual Spending (YTD), Spending Analysis, and Other Spending
// used to be 3 separate top-level nav steps (plus one already-hidden report
// page). They now live as tabs of a single "Spending" workspace, mirroring
// the existing Distribution Strategy tabbed workspace pattern.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

// Ticket 286 added a fifth tab: Withdrawal Order, moved here from the
// Distribution Strategy sub-nav (which that ticket removed entirely).
test('the Spending nav step tab-switches between its merged pages', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');

  const tabs = page.locator('.spending-workspace .workspace-tab');
  await expect(tabs).toHaveCount(5);
  await expect(tabs.first()).toHaveClass(/active/);
  await expect(tabs.first()).toHaveText('Spending Model');

  // Default tab renders the Spending Model field groups.
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();

  await page.getByRole('tab', { name: 'Actual Spending (YTD)' }).click();
  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/);
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();

  await page.getByRole('tab', { name: 'Other Spending' }).click();
  await expect(page.getByRole('tab', { name: 'Other Spending' })).toHaveClass(/active/);
  // Other Spending keeps its Travel/Large Items accordions (the Wave 1.4
  // jump-to-field fix depends on them staying <details>-based).
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Travel' })).toBeVisible();
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Large Items' })).toBeVisible();
  // DAF is deliberately NOT here: #269 removed the duplicate Donor-Advised
  // Fund section from Other Spending, leaving the canonical one on the
  // Charitable Giving step (entity_charitable). Asserted negatively so the
  // duplicate cannot quietly come back.
  await expect(
    page.locator('.lifestyle-workspace > details > summary', { hasText: 'Donor-Advised Fund' }),
  ).toHaveCount(0);

  // The tab choice is also a left-nav sub-tab, and is persisted to
  // localStorage the same way Distribution Strategy's tabs are.
  await expect(page.locator('.nav-subtab', { hasText: 'Other Spending' })).toHaveClass(/active/);
  const savedTab = await page.evaluate(() => localStorage.getItem('strategy_tab_spending_core'));
  expect(savedTab).toBe('Other Spending');
});
