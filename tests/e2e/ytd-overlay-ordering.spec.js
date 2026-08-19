// Ticket 290: Actual Spending (YTD) hung behind a locked screen -- a long
// delay with no progress overlay, followed by an overlay whose elapsed timer
// never left 0:00. Root-caused (task-3-report.md) to ordering, not raw
// speed: goToStrategyTab() called setStep(step) -- which runs a full
// synchronous renderMain() -- BEFORE loadYtdStatus(false) ever showed the
// progress overlay, so the expensive first render always ran on a bare
// screen. A second bug compounded it: loadYtdStatus(false).then(renderMain)
// let loadYtdStatus's own `finally` hide the overlay BEFORE that .then()
// callback ran the second (real-data) render, so even the initial overlay
// disappeared before the render it was supposed to cover.
//
// The fix (frontend/js/navigation.js's new `id==='spending_core'` branch,
// mirroring the existing #222 all_assumptions precedent; and
// frontend/js/dashboard.js's goToStrategyTab, which now owns the overlay
// across both the load AND the post-load render) makes the overlay the
// FIRST thing to happen, before either renderMain() call. That ordering is
// deterministic and cheap to assert directly, unlike a wall-clock stopwatch
// on an unpredictable render duration -- see this file's own comment above
// the assertions for why a pure timing check was rejected.
//
// Drives goToStrategyTab() directly from a cheap, unrelated starting step
// (Household & People) rather than first landing on the Spending Model tab
// via the UI: that tab kicks off several independent async loaders
// (loadTaxonomy/loadMappingRules/loadTaxonomyBudget/loadSpendingModel in
// dashboard_decomp_spending_taxonomy.js) that each re-render the whole
// #mainPane as they resolve -- a real, pre-existing (not introduced by this
// fix) cascade unrelated to what this test is checking. Calling
// goToStrategyTab() with the YTD tab directly exercises the exact code path
// ticket 290 was filed against without that unrelated noise.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('the overlay is shown before Actual Spending (YTD)\'s render runs, not after', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');

  // Instrument BEFORE the call: wrap renderMain so the first invocation
  // records whether #buildOverlay already had .active at that moment. This
  // is an ordering check, not a stopwatch -- it is true or false regardless
  // of how long the render itself takes on whatever machine runs this.
  await page.evaluate(() => {
    window.__t290FirstRenderSawOverlayActive = null;
    window.__t290RenderCount = 0;
    const orig = window.renderMain;
    window.renderMain = function (...args) {
      window.__t290RenderCount += 1;
      if (window.__t290FirstRenderSawOverlayActive === null) {
        const overlay = document.getElementById('buildOverlay');
        window.__t290FirstRenderSawOverlayActive = !!(overlay && overlay.classList.contains('active'));
      }
      return orig.apply(this, args);
    };
  });

  // The overlay must become visible fast -- our fix shows it synchronously
  // inside goToStrategyTab, well before the (possibly slow) render starts,
  // so this should never be a close call even under load. A real (generous)
  // wall-clock bound per the ticket's own "within 500ms" ask, separate from
  // the deterministic ordering check below.
  //
  // goToStrategyTab is itself async and, once the fix lands, resolves only
  // AFTER the overlay has been shown, the render has run, the YTD data has
  // loaded, and the overlay has been hidden again -- awaiting it here before
  // checking #buildOverlay would check AFTER that whole cycle, by which
  // point .active is already gone (this was verified empirically: an
  // earlier version of this test awaited the call directly and failed
  // exactly this way against a correctly-working fix, not a broken one).
  // Fire it without awaiting the returned promise so this can observe the
  // overlay WHILE the operation is still in flight.
  await page.evaluate(() => {
    window.goToStrategyTab('spending_core', 'Actual Spending (YTD)');
  });
  await expect(page.locator('#buildOverlay')).toHaveClass(/active/, { timeout: 500 });

  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/, { timeout: 15_000 });
  await expect(page.locator('.workspace-tab-body')).not.toBeEmpty();

  const result = await page.evaluate(() => ({
    firstRenderSawOverlayActive: window.__t290FirstRenderSawOverlayActive,
    renderCount: window.__t290RenderCount,
  }));
  expect(result.renderCount, 'renderMain was never called -- the instrumentation missed the navigation').toBeGreaterThan(0);
  expect(
    result.firstRenderSawOverlayActive,
    'the FIRST renderMain() after goToStrategyTab() ran before the progress overlay was shown -- this is the ticket 290 regression (locked screen, no overlay)',
  ).toBe(true);
});
