// Ticket 285, fix round 2 (see focus-restoration-ytd-search.spec.js for the
// full background). This is the SELECT half of the two fields the sweep in
// "Fix round 1" measured as still falling back to <body>:
// dashboard_decomp_ytd_and_plan_folder_io.js:655,
// onchange="ytdCategoryFilter=this.value;resetYtdTxnPage();renderMain()".
//
// A <select> exercises a different path through renderMain()'s capture logic
// than a text input: `typeof _prevActive.selectionStart === "number"` is
// false for a SELECT element (selects don't expose selectionStart at all),
// so the selection-restore branch is structurally unreachable for this
// field -- only the unconditional `revived.focus(...)` applies. That is a
// property of the existing general mechanism, not something added here; this
// test exists to confirm that is actually true against a real browser, not
// just true by reading the code, and specifically that the round-trip value
// comparison (which the general mechanism only uses to decide whether to
// call setSelectionRange/.select()) does not misbehave for a value that
// legitimately changed because the user just picked a new option -- e.g. by
// somehow leaving the select showing the OLD option, or throwing.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('changing the YTD category filter keeps it focused, on the newly chosen option, after the autosave rerender', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');
  await page.getByRole('tab', { name: 'Actual Spending (YTD)' }).click();
  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/);

  // The category filter's options are derived from EXISTING transactions'
  // Category values (ytdFilterOptions("Category")), not from a static list --
  // seed one synthetic transaction with a distinctive category so there is a
  // real option to select into, regardless of what the frozen e2e fixture's
  // transactions (if any) already contain.
  const CATEGORY = 'E2E_Sweep_Category';
  await page.evaluate((category) => {
    window.addYtdTxn();
    // addYtdTxn() unshifts the new row to index 0.
    window.updateYtdTxn(0, 'Category', category);
    window.renderMain();
  }, CATEGORY);

  const select = page.locator('select[data-focus-key="ytd:category-filter"]');
  await expect(select, 'category filter select is missing its data-focus-key -- the round-2 opt-in did not ship').toHaveCount(1);
  await expect(select.locator(`option[value="${CATEGORY}"]`)).toHaveCount(1);

  try {
    await select.focus();
    // Real keyboard/DOM selection (not selectOption()'s programmatic path
    // alone -- selectOption() does move real focus in modern Playwright, but
    // matching the Holdings account-select spec's own reasoning: this is what
    // genuinely fires `change` on a focused, live element).
    await select.selectOption(CATEGORY);

    const info = await page.evaluate(() => {
      const el = document.activeElement;
      return {
        tag: el ? el.tagName : null,
        key: el && el.getAttribute ? el.getAttribute('data-focus-key') : null,
        value: el ? el.value : null,
      };
    });
    expect(info.tag, 'the synchronous onchange renderMain() destroyed focus').toBe('SELECT');
    expect(info.key).toBe('ytd:category-filter');
    // Not just "some select is focused" -- it must be showing the NEWLY
    // chosen value, proving this is the freshly re-rendered replacement
    // (whose <option selected> comes from window.ytdCategoryFilter, already
    // updated to CATEGORY before renderMain() ran) and not a stale node, and
    // proving the value round-trip guard did not somehow revert or ignore
    // the change.
    expect(info.value).toBe(CATEGORY);
  } finally {
    // Remove the synthetic transaction and reset the filter. ytdData.transactions
    // was never sent to the server in this test (saveYtdTransactions() was
    // never called), so the seeded row only ever existed in this page's
    // in-memory state -- but push the cleaned list explicitly anyway, mirroring
    // the Holdings spec's precedent, in case anything else in a shared test
    // run were to trigger a save before teardown.
    await page.evaluate((category) => {
      window.ytdCategoryFilter = '';
      window.resetYtdTxnPage();
      if (window.ytdData && Array.isArray(window.ytdData.transactions)) {
        window.ytdData.transactions = window.ytdData.transactions.filter(
          (r) => r.Category !== category,
        );
      }
      window.renderMain();
    }, CATEGORY);
  }
});
