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

    // saveActiveEditor() shows "<title> saved. Restart the app if you
    // changed startup-only settings." via the same msg() banner seen as
    // "Build timeout loaded" earlier, then calls loadCsvEditor() to
    // repopulate the page from what was actually just written to disk --
    // this is a real round trip, not an optimistic client-side echo.
    await expect(page.getByText(/Build timeout saved/)).toBeVisible({ timeout: 10_000 });

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
    const restoreInput = page.locator('tr', { hasText: 'Max Build Seconds' }).locator('input.cfg-input');
    if (await restoreInput.count()) {
      await restoreInput.fill(originalValue);
      const saveButton = page.getByRole('button', { name: 'Save', exact: true });
      if (await saveButton.count()) {
        await saveButton.click();
        await expect(page.getByText(/Build timeout saved/)).toBeVisible({ timeout: 10_000 });
      }
    }
  }
});
