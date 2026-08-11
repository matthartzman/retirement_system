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
  // "Build Reports" is rendered contextually (onclick="runBuild(false)"), not
  // by the app shell -- the home page has one, the Workbook Formatting page
  // does not. This test's SECOND build is triggered while sitting on Workbook
  // Formatting, whose only build affordance is a "Rebuild now" button that is
  // pure navigation (data-step-id="reports_and_review"), not a trigger. The
  // previous unconditional click therefore auto-waited on a button that page
  // never renders, silently consuming the entire test budget and surfacing as
  // a timeout inside the finally block rather than a missing-button error --
  // which is why raising the timeout from 700s to 1800s changed nothing.
  // Go where the page's own "Rebuild now" shortcut points, then build.
  //
  // The click-and-verify loop below exists because of a real DOM race, not
  // timing that a longer wait fixes: right after openCurrentPlan() resolves,
  // the header banner (the thing that decides whether "Build Reports" exists
  // at all) is still catching up to two of loadAll()'s deliberately
  // un-awaited tail promises (refreshBuildStatus(), fetchCurrentSummaryKpi()
  // -- see #201's comment on loadAll() for why they're fire-and-forget).
  // openCurrentPlan() waits for window.planLoaded, which is necessary but
  // not sufficient: the banner can still re-render (a raw innerHTML swap,
  // not a framework with stable element identity) in the same window
  // Playwright resolves "Build Reports" as visible and dispatches the click.
  // When that lands badly, .click() succeeds against a DOM node whose
  // onclick reference is detached microtasks later, runBuild() never starts,
  // and the overlay sits on "Loading plan" (loadAll()'s own title) for the
  // rest of the test's budget -- reproduced directly by instrumenting this
  // exact sequence; no single flag to await closes the window. So each
  // attempt below confirms the click actually landed (the overlay going
  // active, or the preflight-warnings modal appearing, are only possible
  // once runBuild() has genuinely started) and retries the full find+click
  // cycle if it didn't, rather than trusting one click blindly.
  const build = page.getByRole('button', { name: 'Build Reports' }).first();
  const overlay = page.locator('#buildOverlay.active');
  const continueBuild = page.locator('.inapp-confirm', { hasText: 'Continue Build' });
  const deadline = Date.now() + 60_000;
  let started = false;
  while (Date.now() < deadline) {
    if (!(await build.isVisible().catch(() => false))) {
      await navigateToStep(page, 'reports_and_review', 'Reports & Review');
      // Reports & Review is a tabbed workspace (Preflight | Build | Impact |
      // Results | Downloads | Plan Data Review) that does NOT open on Build,
      // so arriving on the step is not enough -- "Build Reports" only exists
      // once the Build tab is selected. exact:true so this does not match
      // the "Build Reports" button itself.
      const buildTab = page.getByRole('button', { name: 'Build', exact: true }).first();
      if (await buildTab.isVisible().catch(() => false)) {
        await buildTab.click();
      }
    }
    if (!(await build.isVisible().catch(() => false))) {
      await page.waitForTimeout(500);
      continue;
    }
    await build.click();
    started = await Promise.race([
      overlay.waitFor({ state: 'visible', timeout: 3_000 }).then(() => true),
      continueBuild.waitFor({ state: 'visible', timeout: 3_000 }).then(() => true),
    ]).catch(() => false);
    if (started) break;
  }
  // Bounded wait so a genuinely missing button fails fast and legibly instead
  // of hanging until the test timeout.
  if (!started) {
    await expect(build, 'clicking "Build Reports" never started a build').toBeVisible({
      timeout: 5_000,
    });
  }
  if (await continueBuild.isVisible().catch(() => false)) {
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
