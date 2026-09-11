// Wave 6.2 (system review 2026-08-04, finding `ui-spending-domain-fragmentation`):
// Spending Model, Actual Spending (YTD), Spending Analysis, and Other Spending
// used to be 3 separate top-level nav steps (plus one already-hidden report
// page). They now live as tabs of a single "Spending" workspace, mirroring
// the existing Distribution Strategy tabbed workspace pattern.
//
// Other Spending's own tab is gone (2026-09): its content (Travel/Large Items)
// is now folded directly into the Spending Model tab's own output instead of
// living beside it as a separate stop -- see renderCoreSpendingUnified(),
// dashboard_decomp_spending_taxonomy.js.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

// Ticket 286 added a fifth tab: Withdrawal Order, moved here from the
// Distribution Strategy sub-nav (which that ticket removed entirely).
// Other Spending's removal (2026-09) brought the count back down to 4.
test('the Spending nav step tab-switches between its merged pages', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');

  const tabs = page.locator('.spending-workspace .workspace-tab');
  await expect(tabs).toHaveCount(4);
  await expect(tabs.first()).toHaveClass(/active/);
  await expect(tabs.first()).toHaveText('Spending Model');
  await expect(page.getByRole('tab', { name: 'Other Spending' })).toHaveCount(0);

  // Default tab renders the Spending Model field groups, and now also the
  // former Other Spending accordions (Travel/Large Items) below them -- the
  // Wave 1.4 jump-to-field fix depends on them staying <details>-based.
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Travel' })).toBeVisible();
  await expect(page.locator('.lifestyle-workspace > details > summary', { hasText: 'Large Items' })).toBeVisible();
  // DAF is deliberately NOT here: #269 removed the duplicate Donor-Advised
  // Fund section from Other Spending, leaving the canonical one on the
  // Charitable Giving step (entity_charitable). Asserted negatively so the
  // duplicate cannot quietly come back.
  await expect(
    page.locator('.lifestyle-workspace > details > summary', { hasText: 'Donor-Advised Fund' }),
  ).toHaveCount(0);

  await page.getByRole('tab', { name: 'Actual Spending (YTD)' }).click();
  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/);
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();

  // The tab choice is also a left-nav sub-tab, and is persisted to
  // localStorage the same way Distribution Strategy's tabs are.
  await expect(page.locator('.nav-subtab', { hasText: 'Actual Spending (YTD)' })).toHaveClass(/active/);
  const savedTab = await page.evaluate(() => localStorage.getItem('strategy_tab_spending_core'));
  expect(savedTab).toBe('Actual Spending (YTD)');
});

// Reported live: clicking "Spending Analysis" from the "Recommended spending
// flow" banner (distinct from the in-workspace tab of the same name) used to
// navigate to a separate hidden step, spawning a new "Reports" group in the
// left nav. spending_dashboard, ytd_transactions, and lifestyle_spending all
// now redirect onto the spending_core workspace (with the right tab
// selected) instead -- navigation.js's WORKSPACE_TAB_REDIRECTS.
test('navigating to the old standalone Spending Analysis/YTD/Other-Spending step ids lands on the Spending workspace instead', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');

  await page.evaluate(() => window.setStep('spending_dashboard'));
  await expect(page.getByRole('tab', { name: 'Spending Analysis' })).toHaveClass(/active/);
  // Exact match, not a substring: "Reports & Review" is a real, always-
  // visible top-level nav group since the Reports & Review redesign
  // (2026-09-10) and legitimately contains "Reports" -- this assertion
  // guards against the distinct bug of a *"Reports"* group (spending_dashboard's
  // own hidden STEPS entry, see WORKSPACE_TAB_REDIRECTS' comment above)
  // spawning from navigating here, which `hasText: 'Reports'`'s substring
  // match can no longer tell apart from "Reports & Review" always being present.
  await expect(page.locator('.nav-group-summary', { hasText: /^Reports$/ })).toHaveCount(0);

  await page.evaluate(() => window.setStep('ytd_transactions'));
  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/);

  await page.evaluate(() => window.setStep('lifestyle_spending'));
  await expect(page.getByRole('tab', { name: 'Spending Model' })).toHaveClass(/active/);
});
