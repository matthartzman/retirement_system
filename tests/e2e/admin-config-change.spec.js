// Item 2.14 (finding Q4): the admin/System Configuration UI
// (frontend/js/admin.js, served at /admin) had zero browser coverage --
// every other spec in this suite exercises the CLIENT dashboard only.
//
// Changes a real system_config.csv setting (max_build_seconds) through the
// actual admin UI, verifies it round-trips through a real save + reload
// from disk, then restores the original value in a finally block --
// following the same real-save-then-restore pattern
// test_sync_config_backends_snapshot_freshness_regression.py already
// established for the client-side config editor. max_build_seconds is a
// safe field to mutate: it only bounds how long a future build subprocess
// is allowed to run (src/server/workbook_routes.py's build_start route),
// it is not read anywhere on the request/response path this suite's other
// specs exercise, and it is restored before the test ends either way.
import { test, expect } from '@playwright/test';

test('a real system_config.csv setting round-trips through the admin UI save/reload path', async ({ page }) => {
  await page.goto('/admin');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /Build timeout/ }).first().click();
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: 'Expand all' }).click();

  const input = page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
  await expect(input).toBeVisible({ timeout: 10_000 });
  const originalValue = await input.inputValue();
  expect(originalValue, 'expected a real numeric max_build_seconds value to already be configured').toMatch(/^\d+$/);

  // A distinctive figure vanishingly unlikely to already be the configured
  // value, so a stale-read bug (save appears to succeed but the reload
  // shows the old number) is unambiguous.
  const NEW_VALUE = '2653';

  try {
    await input.fill(NEW_VALUE);
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    // saveActiveEditor() (frontend/js/admin.js) shows "<title> saved.
    // Restart the app if you changed startup-only settings." via the same
    // msg() banner used elsewhere, but then immediately calls
    // `await loadCsvEditor(...)` to repopulate the page from what was
    // actually just written to disk -- and loadCsvEditor's own last line is
    // `msg(activeEditor.title + " loaded")`, which stomps the "saved" text
    // the instant that reload finishes. Root-caused directly (2026-09-01)
    // against a real flaky failure: on a fast/idle server the reload's own
    // GET can resolve before this assertion's next poll, so the "saved"
    // text is not a bug in the app, it's just never reliably observable --
    // whether an E2E run catches it is pure luck of the poll timing, not a
    // real distinguishing signal. The toHaveValue() check below already
    // proves the same real round trip (save -> disk -> reload) far more
    // robustly, since it polls until the reload actually lands rather than
    // trying to catch a message in the middle of being overwritten.
    const reloadedInput = page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
    await expect(reloadedInput).toHaveValue(NEW_VALUE, { timeout: 10_000 });

    // A second, independent full page reload -- proves the value is
    // genuinely on disk (system_config.csv), not merely held in the
    // in-memory activeEditor.rows this same page session already trusts.
    await page.goto('/admin');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: /Build timeout/ }).first().click();
    await page.waitForTimeout(500);
    await page.getByRole('button', { name: 'Expand all' }).click();
    const freshInput = page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
    await expect(freshInput).toHaveValue(NEW_VALUE, { timeout: 10_000 });
  } finally {
    // saveActiveEditor() (frontend/js/admin.js) re-renders #editorBody via
    // loadCsvEditor() on every save, and that fresh render always starts
    // every <details> section CLOSED -- the "Expand all" click above has no
    // lasting effect once any save happens. toHaveValue() above doesn't
    // require visibility, so that step passes even on a collapsed row and
    // never surfaces this; only an action requiring visibility (fill/click)
    // does. Root-caused directly (2026-09-01) against a CI failure on this
    // exact line: under slower conditions, the row can still be collapsed
    // here even though the try block's own second "Expand all" (above)
    // succeeded moments earlier -- re-click it immediately before acting so
    // there's no window for a save-triggered render to have silently
    // reclosed it in between.
    const expandAll = page.getByRole('button', { name: 'Expand all' });
    if (await expandAll.count()) await expandAll.click();
    const restoreInput = page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
    if (await restoreInput.count()) {
      await restoreInput.fill(originalValue);
      const saveButton = page.getByRole('button', { name: 'Save', exact: true });
      if (await saveButton.count()) {
        await saveButton.click();
        // See the try block's comment above on why this waits for the
        // reloaded value rather than the fleeting "saved" toast text.
        await expect(restoreInput).toHaveValue(originalValue, { timeout: 10_000 });
      }
    }
  }
});
