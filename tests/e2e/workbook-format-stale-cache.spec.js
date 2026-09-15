// Reported live: edit a column width on the Workbook Formatting page,
// rebuild, navigate away and back to the same page (no full app reload) --
// the page kept showing the PRE-rebuild "Last built" width and the
// overrides-stale banner, even though the rebuild had genuinely applied the
// edit (independently confirmed by reading the built .xlsx directly). Root
// cause: workbookFormatData is fetched once and cached client-side;
// loadWorkbookFormat() only refetches on an explicit force=true, and nothing
// invalidated that cache after a build completed or on navigation.
// dashboard_decomp_workbook_formatting.js's invalidateWorkbookFormatCache()
// is the fix; dashboard_decomp_row_model.js's build-success handler calls it.
//
// This is a real, ~90s full-build test (matching build-and-results.spec.js's
// precedent) rather than a unit test: the bug is specifically about client
// state surviving across a real build + navigation cycle, which a Node vm
// sandbox test (see tests/frontend/) cannot exercise -- that harness only
// targets pure functions with no shared state or network dependency, and
// this fix is neither.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep, triggerBuildAndWaitForOverlay, ensureWorkbookBuilt } from './helpers.js';

// This file used to fork its own copy of helpers.js's triggerBuildAndWaitForOverlay
// (a "more patient" version, on the theory that this test's build could run
// under heavier concurrent load than every other spec's). E2E efficiency
// review (2026-09-15): with per-worker isolated servers (fixtures.js) that
// contention no longer applies -- this test's build competes with, at most,
// the small number of OTHER workers' builds, the same as any other
// build-triggering spec -- so the fork bought nothing but a second place for
// this exact retry/force-dirty logic to drift out of sync with the shared
// one. Use the shared helper.

// Sheet/table <details> are collapsed by default, and their open/closed
// state is tracked in a JS Set (wfOpen) that a re-render regenerates the
// <details> HTML from -- setting the DOM's .open property directly does not
// survive the next render (this app polls checkAppStatus every 15s, and a
// two-full-build test runs long enough to hit that). Real clicks on
// <summary> go through wfToggle(), which updates wfOpen itself, so the
// expansion survives.
async function expandFirstColumn(page) {
  await page.locator('.wf-sheet > summary').first().click();
  const tableSummary = page.locator('.wf-table > summary').first();
  if (await tableSummary.isVisible().catch(() => false)) {
    await tableSummary.click();
  }
  return page.locator('.wf-col-row').first();
}

test('a rebuilt column width replaces the stale "Last built" value after navigating away and back', async ({ page }) => {
  // This test always triggers one real build itself below -- the actual
  // cache-invalidation regression under test. If it also happens to be the
  // first spec Playwright schedules onto a fresh worker, ensureWorkbookBuilt()
  // pays for a SECOND real build first (Workbook Formatting has nothing to
  // show, and no "Last built" baseline to compare against, until one
  // exists). Budget for both in the worst case.
  test.setTimeout(500_000);

  await openCurrentPlan(page);
  await ensureWorkbookBuilt(page);
  await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');

  const firstRow = await expandFirstColumn(page);
  const input = firstRow.locator('input[type=number]');
  const onchange = await input.getAttribute('onchange');
  const match = onchange.match(/setWorkbookColWidth\('([^']*)','([^']*)'/);
  expect(match, `could not parse sheet/col out of onchange="${onchange}"`).not.toBeNull();
  const [, sheet, col] = match;

  const originalWidth = await input.inputValue();
  const testWidth = (parseFloat(originalWidth) + 3).toFixed(2);

  await input.fill(testWidth);
  await input.blur();
  await expect(page.locator('.message')).toContainText(`Column ${col} width saved.`);

  // Edited-but-not-yet-rebuilt state: the stale banner appears, and "Last
  // built" still shows the OLD width -- both correct at this point.
  await expect(page.locator('.workbook-format-panel .section-note.warn').first()).toContainText(
    'saved overrides were edited after the workbook shown below was built',
  );
  await expect(firstRow.locator('.wf-col-default')).toHaveText(`Last built: ${originalWidth}`);

  try {
    const finalTitle = await triggerBuildAndWaitForOverlay(page);
    expect(finalTitle).toBe('Build complete');

    // The actual regression: navigate away, then back, with no page reload.
    await navigateToStep(page, 'reports_and_review', 'Reports & Review');
    await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');
    await expandFirstColumn(page);

    const rowAfter = page.locator('.wf-col-row', {
      has: page.locator(`input[onchange*="setWorkbookColWidth('${sheet}','${col}'"]`),
    });
    // Compare the NUMBER, not the formatted string: testWidth is built with
    // toFixed(2) ("15.00") but the page renders the width unpadded ("15"), so
    // a literal toHaveText fails on formatting even when the behaviour under
    // test is correct. expect.poll keeps the retry semantics toHaveText had.
    await expect
      .poll(
        async () => {
          // textContent, not innerText: innerText returns "" for anything not
          // visible, and a background re-render (checkAppStatus polls every
          // 15s -- see expandFirstColumn's note) can collapse the containing
          // <details> mid-poll, which turned the parse into NaN forever.
          const text = (await rowAfter.locator('.wf-col-default').textContent()) ?? '';
          return parseFloat(text.replace(/[^0-9.]/g, ''));
        },
        {
          message:
            'Last built still shows the pre-rebuild width -- the client-side cache was not invalidated after the build',
          timeout: 5_000,
        },
      )
      .toBeCloseTo(parseFloat(testWidth), 2);
    await expect(page.locator('.workbook-format-panel .section-note.warn')).toHaveCount(0);
  } finally {
    // Restore the original width regardless of pass/fail so this test never
    // leaves the shared saved plan's overrides file mutated.
    await page.evaluate(
      ([s, c, w]) => window.setWorkbookColWidth(s, c, w),
      [sheet, col, originalWidth],
    );
  }
});
