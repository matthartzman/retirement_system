// Ticket 285, fix round 2: the finding-1 empirical sweep (task-2-report.md,
// "Fix round 1") measured the YTD transaction search box as still falling
// back to <body> after an edit -- it has the exact same "autosave, then
// synchronous renderMain()" shape as the Workbook Formatting width field and
// the Holdings account-select (dashboard_decomp_ytd_and_plan_folder_io.js:655,
// oninput="ytdTxSearch=this.value;resetYtdTxnPage();renderMain()"), but was
// never opted into the data-focus-key mechanism. The human reviewed the sweep
// evidence and chose to opt this field in now.
//
// This field is a much higher-frequency path than a width edit or an
// account-select change: renderMain() re-renders (destroying and rebuilding
// the whole #mainPane subtree, including this exact input) on EVERY
// keystroke, not just on blur. The scenario this test exists to catch is the
// specific failure mode the whole fix is guarded against: focus stealing /
// fighting fast typing -- if capture-and-restore raced with the next
// keystroke, or restored a stale caret position, typing several characters
// quickly could visibly stutter, drop characters, or misplace the cursor.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('typing in the YTD transaction search box survives the per-keystroke re-render, including under fast typing', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'spending_core', 'Spending Model');
  await page.getByRole('tab', { name: 'Actual Spending (YTD)' }).click();
  await expect(page.getByRole('tab', { name: 'Actual Spending (YTD)' })).toHaveClass(/active/);

  const search = page.locator('input[data-focus-key="ytd:tx-search"]');
  await expect(search, 'search box is missing its data-focus-key -- the round-2 opt-in did not ship').toHaveCount(1);

  try {
    await search.focus();

    // A single edit first, matching the shape of the other focus-restore
    // specs: renderMain() fires synchronously inside this one oninput, and
    // focus must survive it.
    await search.press('a');
    let info = await page.evaluate(() => {
      const el = document.activeElement;
      return {
        tag: el ? el.tagName : null,
        key: el && el.getAttribute ? el.getAttribute('data-focus-key') : null,
        value: el ? el.value : null,
        selStart: el ? el.selectionStart : null,
      };
    });
    expect(info.tag, 'the synchronous per-keystroke renderMain() destroyed focus').toBe('INPUT');
    expect(info.key).toBe('ytd:tx-search');
    expect(info.value).toBe('a');
    expect(info.selStart, 'caret did not land after the typed character').toBe(1);

    // Now type several more characters back-to-back with a short delay
    // (Playwright's .type() dispatches real, separately-processed keydown/
    // input events per character, matching a human typing quickly -- each one
    // triggers its own full #mainPane innerHTML replace). If capture/restore
    // fought the next keystroke, dropped a character, duplicated one, or
    // mis-restored the caret mid-sequence, the final value or caret position
    // would not match what was actually typed.
    await page.keyboard.type('bcde', { delay: 15 });

    info = await page.evaluate(() => {
      const el = document.activeElement;
      return {
        tag: el ? el.tagName : null,
        key: el && el.getAttribute ? el.getAttribute('data-focus-key') : null,
        value: el ? el.value : null,
        selStart: el ? el.selectionStart : null,
        selEnd: el ? el.selectionEnd : null,
      };
    });
    expect(info.tag, 'fast typing lost focus to the page at some point').toBe('INPUT');
    expect(info.key).toBe('ytd:tx-search');
    expect(info.value, 'fast typing produced a value other than exactly what was typed -- a dropped/duplicated keystroke or a restore racing input').toBe('abcde');
    expect(info.selStart, 'caret was not left at the end of the typed text').toBe(5);
    expect(info.selEnd).toBe(5);
  } finally {
    // ytdTxSearch is pure client-side filter state (never sent to the
    // server -- see saveYtdTransactions(), which only ever PUTs
    // ytdData.transactions) and a fresh openCurrentPlan() in any later test
    // re-fetches everything from scratch, so nothing here can leak into the
    // shared saved plan. Reset it anyway for hygiene, matching the cleanup
    // precedent applied to every other spec in this focus-restoration set.
    await page.evaluate(() => {
      window.ytdTxSearch = '';
      window.resetYtdTxnPage();
      window.renderMain();
    });
  }
});
