// Wave 6.2 (system review 2026-08-04, finding `ui-spending-domain-fragmentation`):
// Spending Model, Actual Spending (YTD), Spending Analysis, and Other Spending
// used to be 3 separate top-level nav steps (plus one already-hidden report
// page). They now live as tabs of a single "Spending" workspace, mirroring
// the existing Distribution Strategy tabbed workspace pattern.
//
// #338 W-C: Actual Spending and Spending Analysis moved on again, to the
// Actual Spending step under Reports & Review (see below).
//
// Other Spending's own tab is gone (2026-09): its content (Travel/Large Items)
// is now folded directly into the Spending Model tab's own output instead of
// living beside it as a separate stop -- see renderCoreSpendingUnified(),
// dashboard_decomp_spending_taxonomy.js.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

// Ticket 286 added a fifth tab: Withdrawal Order, moved here from the
// Distribution Strategy sub-nav (which that ticket removed entirely).
// Other Spending's removal (2026-09) brought the count back down to 4.
// #338 W-C: Withdrawal Order moved to Optimize and Actual Spending (YTD) /
// Spending Analysis became the "Actual Spending" step under Reports &
// Review (tabs "This year" and "Analysis"), so Spending Model has no tab
// strip left and the tab behavior below is Actual Spending's.
test('Spending Model has no tabs; Actual Spending tab-switches between its merged pages', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');

  await expect(page.locator('.spending-workspace .workspace-tab')).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Withdrawal Order' })).toHaveCount(0);

  // Spending Model renders its field groups, and the former Other Spending
  // accordion (Large Items) below them -- the Wave 1.4 jump-to-field fix
  // depends on it staying <details>-based. Travel is its own Tracking Type
  // accordion since #338 W-C, not repeated here.
  await expect(page.locator('#mainPane .lifestyle-workspace')).toBeVisible();
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Travel' })).toHaveCount(0);
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Large Items' })).toBeVisible();
  // DAF is deliberately NOT here: #269 removed the duplicate Donor-Advised
  // Fund section from Other Spending, leaving the canonical one on the
  // Charitable Giving step (entity_charitable). Asserted negatively so the
  // duplicate cannot quietly come back.
  await expect(
    page.locator('.lifestyle-workspace > details > summary', { hasText: 'Donor-Advised Fund' }),
  ).toHaveCount(0);

  await navigateToStep(page, 'actual_spending', 'Actual Spending');
  const tabs = page.locator('.spending-workspace .workspace-tab');
  await expect(tabs).toHaveCount(2);
  await expect(tabs.first()).toHaveText('This year');

  await page.getByRole('tab', { name: 'Analysis' }).click();
  await expect(page.getByRole('tab', { name: 'Analysis' })).toHaveClass(/active/);
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();

  // The tab choice is also a left-nav sub-tab, and is persisted to
  // localStorage.
  await expect(page.locator('.nav-subtab', { hasText: 'Analysis' })).toHaveClass(/active/);
  const savedTab = await page.evaluate(() => localStorage.getItem('strategy_tab_actual_spending'));
  expect(savedTab).toBe('Analysis');
});

// Reported live: clicking "Spending Analysis" from the "Recommended spending
// flow" banner used to navigate to a separate hidden step, spawning a new
// "Reports" group in the left nav. spending_dashboard and ytd_transactions
// now redirect onto the actual_spending workspace (with the right tab
// selected) and lifestyle_spending onto Spending Model -- navigation.js's
// WORKSPACE_TAB_REDIRECTS / STEP_REDIRECTS. #338 W-C also removed the
// "Reports" group string from STEPS entirely.
test('navigating to the old standalone Spending Analysis/YTD/Other-Spending step ids lands on the merged steps instead', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');

  await page.evaluate(() => window.setStep('spending_dashboard'));
  await expect(page.getByRole('tab', { name: 'Analysis' })).toHaveClass(/active/);
  await expect(page.getByRole('heading', { name: 'Actual Spending' })).toBeVisible();
  // Exact match, not a substring: "Reports & Review" is a real, always-
  // visible top-level nav group and legitimately contains "Reports".
  await expect(page.locator('.nav-group-summary', { hasText: /^Reports$/ })).toHaveCount(0);

  await page.evaluate(() => window.setStep('ytd_transactions'));
  await expect(page.getByRole('tab', { name: 'This year' })).toHaveClass(/active/);

  await page.evaluate(() => window.setStep('lifestyle_spending'));
  await expect(page.getByRole('heading', { name: 'Spending Model' })).toBeVisible();
});
