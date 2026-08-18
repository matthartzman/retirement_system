// Ticket 285: Tab/Shift+Tab between Workbook-Formatting column-width fields.
//
// wfWidthInputKeydown (frontend/js/dashboard_decomp_workbook_formatting.js)
// already implements the traversal -- this is not "add it", it is "it does
// not work". Root cause, confirmed by direct measurement (not just the
// diagnosis in the ticket): editing a width field autosaves on blur
// (setWorkbookColWidth), which calls renderMain() -- and renderMain does
// `#mainPane.innerHTML = content`, destroying and rebuilding every node in
// the pane, including whatever the Tab handler just focused. Browsers run
// blur/change/focusout with document.activeElement reading as <body> for
// their entire duration (verified directly against real Chromium, not
// assumed), and the change handler that calls renderMain() fires exactly
// during that window -- so the FIRST renderMain() call happens while
// nothing is resolvable as "the field to refocus" at all. A SECOND
// renderMain() call happens later in setWorkbookColWidth's `finally`, once
// the autosave's network round trip resolves; that one is a plain async
// continuation with no blur in flight, which is what the general fix in
// dashboard.js's renderMain() (a `data-focus-key` capture/restore around the
// innerHTML write) actually targets. The first, synchronous case is instead
// handled at the source: wfWidthInputKeydown re-resolves its Tab target by
// `data-focus-key` and retries focus/select once the render has settled.
// See both functions' own comments for the full mechanism.
//
// This is a real, full-build test (matching workbook-format-stale-cache.spec.js's
// precedent) because Workbook Formatting has nothing to show until a
// workbook has actually been built once -- see tools/e2e_server.py, which
// stages an isolated workspace with no prior build. All cases below share
// the ONE build triggered in the first test: Playwright's shared server
// process (playwright.config.js: `fullyParallel: false, workers: 1`)
// persists the built workbook on disk for the life of the run, so later
// tests in this file can navigate straight to Workbook Formatting without
// paying for a second ~110s+ build. test.describe.serial keeps that build
// ordered first and the suite from being reordered/parallelized underneath
// that assumption.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep, triggerBuildAndWaitForOverlay } from './helpers.js';

// Sheet/table <details> are collapsed by default and their open/closed state
// is tracked in a JS Set (wfOpen) that a re-render regenerates the <details>
// HTML from -- setting the DOM's .open property directly does not survive a
// re-render. Real clicks on <summary> go through wfToggle(), which updates
// wfOpen itself, matching workbook-format-stale-cache.spec.js's own
// expandFirstColumn() helper. This version opens EVERY table layer inside a
// given sheet (not just the first), so a field deep inside a multi-table
// sheet is reachable by real Playwright actions (hidden/collapsed elements
// fail Playwright's actionability checks).
async function expandSheet(page, sheetIndex) {
  const sheet = page.locator('.workbook-format-panel .wf-sheet').nth(sheetIndex);
  await sheet.locator('> summary').click();
  const tableSummaries = sheet.locator('.wf-table > summary');
  const n = await tableSummaries.count();
  for (let i = 0; i < n; i++) {
    await tableSummaries.nth(i).click();
  }
}

// Reads the (sheet, col) pair a width input's onchange handler was rendered
// with, so a cleanup step can call setWorkbookColWidth directly to restore
// the original value without depending on further UI interaction.
async function sheetColOf(locator) {
  return locator.evaluate((el) => {
    const m = (el.getAttribute('onchange') || '').match(
      /setWorkbookColWidth\('([^']*)','([^']*)'/,
    );
    return m ? { sheet: m[1], col: m[2] } : null;
  });
}

async function restoreWidth(page, sheetCol, value) {
  if (!sheetCol) return;
  await page.evaluate(
    ({ sheet, col, value }) => window.setWorkbookColWidth(sheet, col, value),
    { ...sheetCol, value },
  );
}

async function activeElementInfo(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    return {
      tag: el ? el.tagName : null,
      key: el && el.getAttribute ? el.getAttribute('data-focus-key') : null,
    };
  });
}

test.describe.serial('Workbook Formatting: Tab/Shift+Tab column-width traversal survives autosave rerenders', () => {
  test('building the workbook once so Workbook Formatting has data to show', async ({ page }) => {
    test.setTimeout(300_000);
    await openCurrentPlan(page);
    const finalTitle = await triggerBuildAndWaitForOverlay(page);
    expect(finalTitle).toBe('Build complete');
  });

  test('Tab after editing a width moves focus (and selects the value) in the next field, surviving both the synchronous and the async autosave rerender', async ({ page }) => {
    await openCurrentPlan(page);
    await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');
    await expandSheet(page, 0);

    const inputs = page.locator('.workbook-format-panel .wf-col-width input[type=number]');
    expect(
      await inputs.count(),
      'first sheet needs at least 2 width fields for a Tab-traversal test',
    ).toBeGreaterThan(1);

    const first = inputs.nth(0);
    const second = inputs.nth(1);
    const firstKey = await first.getAttribute('data-focus-key');
    const secondKey = await second.getAttribute('data-focus-key');
    expect(firstKey).toBeTruthy();
    expect(secondKey).toBeTruthy();
    expect(secondKey).not.toBe(firstKey);
    const firstSheetCol = await sheetColOf(first);
    const originalFirstWidth = await first.inputValue();

    try {
      await first.fill((parseFloat(originalFirstWidth) + 2).toFixed(2));
      await first.press('Tab');

      // This is the exact assertion Step 2.1 of the ticket brief requires to
      // FAIL (activeElement === body) before any fix is applied -- proving
      // the diagnosis before writing one line of fix code.
      const afterTab = await activeElementInfo(page);
      expect(afterTab.tag, 'Tab did not move focus into an <input> after an edited width autosaved').toBe('INPUT');
      expect(afterTab.key, 'focus landed on the wrong field after Tab').toBe(secondKey);

      // Prove the field is actually SELECTED, not just focused: type over
      // it and confirm the whole previous value was replaced, not appended
      // to. (input[type=number] does not expose selectionStart/selectionEnd
      // in Chromium -- confirmed directly against real Chromium, not
      // assumed -- so this behavioral check is the reliable way to verify
      // selection here, not a direct property read.)
      const originalSecondWidth = await second.inputValue();
      await page.keyboard.type('9');
      expect(await second.inputValue()).toBe('9');
      await second.fill(originalSecondWidth); // undo the '9' probe

      // The autosave triggered by editing the FIRST field may still be in
      // flight -- wait for its confirmation toast, which only appears after
      // setWorkbookColWidth's `await api(...)` resolves and its `finally`
      // block's SECOND renderMain() has already run. Without the general
      // fix in renderMain(), that second re-render destroys focus again
      // even if the first (synchronous) one were fixed.
      await expect(page.locator('.message')).toContainText(
        `Column ${firstSheetCol.col} width saved.`,
        { timeout: 10_000 },
      );

      const afterAutosave = await activeElementInfo(page);
      expect(afterAutosave.tag, 'the SECOND (async, post-autosave) renderMain() destroyed focus').toBe('INPUT');
      expect(afterAutosave.key, 'the SECOND (async, post-autosave) renderMain() moved focus to the wrong field').toBe(secondKey);
    } finally {
      // Never leave the shared saved plan's overrides mutated, pass or fail.
      await restoreWidth(page, firstSheetCol, originalFirstWidth);
    }
  });

  test('Shift+Tab moves focus (and selects the value) back to the previous field', async ({ page }) => {
    await openCurrentPlan(page);
    await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');
    await expandSheet(page, 0);

    const inputs = page.locator('.workbook-format-panel .wf-col-width input[type=number]');
    const first = inputs.nth(0);
    const second = inputs.nth(1);
    const firstKey = await first.getAttribute('data-focus-key');
    const secondSheetCol = await sheetColOf(second);
    const originalSecondWidth = await second.inputValue();

    try {
      await second.fill((parseFloat(originalSecondWidth) + 1).toFixed(2));
      await second.press('Shift+Tab');

      const afterShiftTab = await activeElementInfo(page);
      expect(afterShiftTab.tag).toBe('INPUT');
      expect(afterShiftTab.key, 'Shift+Tab did not land on the previous field').toBe(firstKey);

      const originalFirstWidth = await first.inputValue();
      await page.keyboard.type('7');
      expect(await first.inputValue()).toBe('7');
      await first.fill(originalFirstWidth); // undo the '7' probe
    } finally {
      await restoreWidth(page, secondSheetCol, originalSecondWidth);
    }
  });

  test('Tab from the last field of a collapsed sheet opens the next sheet and focuses its first field', async ({ page }) => {
    await openCurrentPlan(page);
    await navigateToStep(page, 'workbook_formatting', 'Workbook Formatting');

    // .count() does not auto-wait the way .click()/.toBeVisible() do, and
    // this page's data (workbookFormatData) loads via an async API call
    // kicked off on first render -- openCurrentPlan() above did a fresh
    // page.goto('/'), so that cache is empty and the fetch may still be in
    // flight the instant this test's own code starts running. Wait for at
    // least one sheet to actually be visible before counting, or this reads
    // a transient 0 during the "Loading workbook layout…" state rather than
    // the real fixture sheet count.
    const sheetsLocator = page.locator('.workbook-format-panel .wf-sheet');
    await expect(sheetsLocator.first()).toBeVisible({ timeout: 15_000 });
    const sheetCount = await sheetsLocator.count();
    expect(sheetCount, 'fixture needs at least 2 sheets for a cross-sheet traversal test').toBeGreaterThan(1);

    // Sheet 0 fully expanded (needed for a real Playwright interaction with
    // its last field); sheet 1 stays collapsed -- the traversal itself must
    // open it, which is exactly what this test is proving.
    await expandSheet(page, 0);
    const sheet0Inputs = page
      .locator('.workbook-format-panel .wf-sheet')
      .nth(0)
      .locator('.wf-col-width input[type=number]');
    const lastOfSheet0 = sheet0Inputs.last();
    const allInputs = page.locator('.workbook-format-panel .wf-col-width input[type=number]');
    const lastOfSheet0Key = await lastOfSheet0.getAttribute('data-focus-key');
    const allKeys = await allInputs.evaluateAll((els) => els.map((e) => e.getAttribute('data-focus-key')));
    const boundaryIdx = allKeys.indexOf(lastOfSheet0Key);
    expect(boundaryIdx, 'could not locate the last field of sheet 0 in document order').toBeGreaterThan(-1);
    const nextKey = allKeys[boundaryIdx + 1];
    expect(nextKey, 'no field exists after the last field of sheet 0 -- fixture needs a non-empty second sheet').toBeTruthy();

    const sheet1 = page.locator('.workbook-format-panel .wf-sheet').nth(1);
    expect(
      await sheet1.evaluate((el) => el.open),
      'sheet 1 should start collapsed for this test to be meaningful',
    ).toBe(false);

    await lastOfSheet0.focus();
    await lastOfSheet0.press('Tab');

    const after = await page.evaluate(() => {
      const el = document.activeElement;
      return {
        tag: el ? el.tagName : null,
        key: el && el.getAttribute ? el.getAttribute('data-focus-key') : null,
      };
    });
    expect(after.tag).toBe('INPUT');
    expect(after.key, `expected focus on the next sheet's first field (key ${nextKey}), got ${after.key}`).toBe(nextKey);

    const sheet1OpenAfter = await sheet1.evaluate((el) => el.open);
    expect(
      sheet1OpenAfter,
      'Tab across the sheet boundary should have expanded the collapsed <details> for sheet 1',
    ).toBe(true);
  });
});
