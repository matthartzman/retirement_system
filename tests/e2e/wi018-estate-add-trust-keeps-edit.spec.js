// WI-018 / UX-001: a field edited on the Estate page but not yet saved must survive
// "Add trust account" (which used to call loadAll() and silently drop the dirty map).
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

async function rowsByIndex(page) {
  const resp = await page.request.get('/api/config/rows', { headers: { 'X-User-Role': 'admin' } });
  return Object.fromEntries((await resp.json()).rows.map((r) => [String(r.row_index), r]));
}

test('an unsaved Estate edit survives Add trust account', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');

  // First plain text/number field on the page that is not part of the trust table.
  const field = page.locator('#mainPane input[data-row]:not([type=checkbox]):not([type=hidden])').first();
  await expect(field).toBeVisible();
  const rowIndex = await field.getAttribute('data-row');
  const before = (await rowsByIndex(page))[rowIndex];
  const original = await field.inputValue();
  const edited = /^[\d,.\s$%-]*$/.test(original) && original.trim() ? String(Number(original.replace(/[^\d.-]/g, '')) + 1) : original + ' wi018';

  try {
    await field.fill(edited);
    await field.blur();
    await expect(page.locator('#saveChangesBtn')).toBeEnabled();

    await page.getByRole('button', { name: 'Add trust account' }).click();
    await page.locator('.inapp-modal-input').fill('WI018 Test Trust');
    await page.locator('.inapp-confirm').click();
    // Trust type prompt (free text or select, depending on the build).
    const typeInput = page.locator('.inapp-modal-input');
    await expect(typeInput).toBeVisible();
    await page.locator('.inapp-confirm').click();

    await expect(page.locator('#actionMessage')).toContainText(/Added WI018 Test Trust trust account/);

    // The edit was saved before the trust was added, and is still on screen.
    const after = (await rowsByIndex(page))[rowIndex];
    expect(String(after.value), 'staged edit was dropped by Add trust account').not.toBe(String(before.value));
    await expect(page.locator(`[data-row="${rowIndex}"]`)).not.toHaveValue(original);
  } finally {
    // Best-effort revert of the edited row (each worker has its own workspace, so the trust stays).
    try {
      await page.request.post('/api/config/rows', {
        headers: { 'X-User-Role': 'admin' },
        data: { updates: [{ row_index: Number(rowIndex), value: before.value }] },
      });
    } catch (_e) {
      /* cleanup must never outrank the real assertion */
    }
  }
});
