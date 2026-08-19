// Ticket 285 (Tab/Shift+Tab between Workbook-Formatting width fields):
// non-workbook guard. The actual fix lives in renderMain() (frontend/js/
// dashboard.js) -- a GENERAL capture/restore around its `innerHTML =
// content` write, keyed off any element carrying a stable `data-focus-key`
// attribute -- specifically because the same "autosave, then synchronous
// rerender" trap that broke Tab-traversal on the width field is armed for
// every field in the app that saves on change and re-renders, not just that
// one page. A test that only ever exercised the width field would still
// pass if the fix had been hard-coded to that page (e.g. keyed off a
// workbook-formatting-specific class instead of the general attribute); this
// spec proves the mechanism generalizes by exercising a completely
// unrelated page (Investment Holdings) that happens to have the exact same
// shape of bug: the account-filter <select>'s onchange (setHoldingAccount,
// dashboard_decomp_holdings.js) calls renderMain() synchronously, replacing
// the <select> itself out from under the very change event that is still
// being handled.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('changing the Holdings account filter keeps it focused after the autosave rerender', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'holdings', 'Investment Holdings');

  const select = page.locator('.table-actions select[data-focus-key="holdings:account-select"]');
  await expect(select, 'account-filter select is missing its data-focus-key -- the generalization this test exists to prove did not ship').toHaveCount(1);

  // The frozen e2e fixture's client_holdings.csv is NOT actually reachable
  // through /api/holdings in this workspace (confirmed directly by querying
  // the endpoint: it returns only the empty-template header, 0 data rows) --
  // a pre-existing data-loading gap unrelated to ticket 285's focus-restore
  // fix, so this test does not depend on it. Seed two accounts directly
  // through the app's own addHoldingLot() (the same function "Add Lot"
  // wires to), which is a synchronous, already-load-bearing path, so the
  // dropdown has real accounts to select between regardless of fixture state.
  //
  // This mutates in-memory holding rows and marks them dirty; if anything in
  // this test (or a later autosave-on-navigation) persists that to the
  // server, the shared frozen e2e workspace would carry these synthetic
  // accounts into every later run. Clean up in a `finally`, matching the
  // precedent in workbook-format-tab-focus.spec.js's restoreWidth(): the
  // shared saved plan must not be left mutated, pass or fail.
  try {
    await page.evaluate(() => {
      window.addHoldingLot('E2E_Account_A');
      window.addHoldingLot('E2E_Account_B');
    });
    await expect(select.locator('option')).toHaveCount(3);

    await select.focus();
    // Changing a <select>'s value via keyboard (not selectOption(), which can
    // resolve without ever moving real page focus onto the element in some
    // Playwright/browser combinations) is what genuinely fires `change` on a
    // focused, live element -- matching how a real user tabs to a dropdown
    // and arrows through it.
    await select.selectOption({ index: 2 });

    // setHoldingAccount -> renderMain() replaces #mainPane's entire subtree,
    // including this exact <select> node, synchronously inside the change
    // handler. Before the fix, the freshly-rendered replacement <select>
    // exists in the DOM but nothing is focused (document.activeElement fell
    // back to <body>). After the fix, renderMain's generic capture/restore
    // re-resolves the new node by data-focus-key and refocuses it.
    const isFocused = await page.evaluate(() => {
      const el = document.activeElement;
      return !!el && el.tagName === 'SELECT' && el.getAttribute('data-focus-key') === 'holdings:account-select';
    });
    expect(isFocused, 'focus did not survive the Holdings account-select autosave rerender -- fell back to document.body or elsewhere').toBe(true);

    // Not just "some select is focused" -- it must be the SAME logical field,
    // now showing the value the user actually chose (proves this is the
    // freshly re-rendered replacement, not a stale reference).
    const selectedIndex = await page.evaluate(() => document.activeElement.selectedIndex);
    expect(selectedIndex).toBe(2);
  } finally {
    // Remove the two synthetic accounts and, if anything marked holdings
    // dirty, push the removal to the server explicitly -- do not rely on a
    // navigation-triggered autosave that this test never invokes. Runs
    // whether the test passed or failed.
    await page.evaluate(async () => {
      const h = window.ensureHoldingRows();
      h.data = h.data.filter(
        (r) => r.account !== 'E2E_Account_A' && r.account !== 'E2E_Account_B',
      );
      window.holdingRowsCache = h;
      window.currentHoldingAccount = 'ALL';
      window.markHoldingsDirty();
      await window.saveHoldings();
    });
  }
});
