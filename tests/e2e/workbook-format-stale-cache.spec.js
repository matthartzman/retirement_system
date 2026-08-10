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
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

// helpers.js's triggerBuildAndWaitForOverlay hard-codes an 80s wait, sized
// for a build running in isolation. Under concurrent load (multiple build
// subprocesses contending for the same machine -- observed directly while
// writing this test) a real build can run well past that without being
// stuck, just slow, so this test polls with its own more patient timeout
// instead of adopting the shared helper's budget for every other spec too.
async function triggerBuildAndWaitPatiently(page) {
  await page.getByRole('button', { name: 'Build Reports' }).first().click();
  const continueBuild = page.locator('.inapp-confirm', { hasText: 'Continue Build' });
  if (await continueBuild.waitFor({ state: 'visible', timeout: 15_000 }).then(() => true).catch(() => false)) {
    await continueBuild.click();
  }
  const title = page.locator('.build-overlay .build-progress-title');
  await expect(title, 'build overlay never reached a terminal state').toHaveText(
    /^Build (complete|failed)$/,
    { timeout: 300_000 },
  );
  return title.innerText();
}

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
  // Two full builds in this one test (the isolated e2e workspace starts with
  // no workbook at all, so Workbook Formatting has nothing to show until one
  // exists; the second is the actual regression this test guards), each
  // potentially slow under load -- see triggerBuildAndWaitPatiently above.
  test.setTimeout(700_000);

  await openCurrentPlan(page);
  expect(await triggerBuildAndWaitPatiently(page)).toBe('Build complete');

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
    const finalTitle = await triggerBuildAndWaitPatiently(page);
    expect(finalTitle).toBe('Build complete');

    // The actual regression: navigate away, then back, with no page reload.
    await navigateToStep(page, 'reports_and_review', 'Reports & Review');
    await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');
    await expandFirstColumn(page);

    const rowAfter = page.locator('.wf-col-row', {
      has: page.locator(`input[onchange*="setWorkbookColWidth('${sheet}','${col}'"]`),
    });
    await expect(
      rowAfter.locator('.wf-col-default'),
      'Last built still shows the pre-rebuild width -- the client-side cache was not invalidated after the build',
    ).toHaveText(`Last built: ${testWidth}`);
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
