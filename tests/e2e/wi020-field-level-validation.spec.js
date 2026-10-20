// WI-020 / UX-004 / UX-010: a rejected save marks the field (aria-invalid + message through
// aria-describedby), lists it with a link in the error summary, and the add-trust prompt is a
// labelled dialog with a trust-type <select>. The save endpoint is stubbed with a 422 so no real
// plan data is touched.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('a 422 save marks the field, shows its message and an error summary with a link', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');

  const field = page.locator('#mainPane input[data-row]:not([type=checkbox]):not([type=hidden])').first();
  await expect(field).toBeVisible();
  const rowIndex = Number(await field.getAttribute('data-row'));
  const MESSAGE = 'must be a plausible value (stubbed WI-020 error)';

  await page.route('**/api/config/rows', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    return route.fulfill({
      status: 422,
      contentType: 'application/json',
      body: JSON.stringify({
        success: false,
        error: 'Plan Data validation failed',
        errors: [`('Household', 'x', 'y'): ${MESSAGE}; got 'z'`],
        field_errors: [{ row_index: rowIndex, section: 'Household', subsection: 'x', label: 'y', message: MESSAGE, got: "'z'", raw: 'r' }],
      }),
    });
  });

  const original = await field.inputValue();
  await field.fill(original + '1');
  await field.blur();
  // (dispatch: at this viewport the help drawer overlaps the header buttons)
  await page.locator('#saveChangesBtn').dispatchEvent('click');

  const summary = page.locator('#saveErrorSummary');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText('1 problem');
  await expect(summary).toContainText(MESSAGE);
  await expect(summary).toBeFocused();

  const control = page.locator(`#field-${rowIndex}-ctl`);
  await expect(control).toHaveAttribute('aria-invalid', 'true');
  const describedBy = await control.getAttribute('aria-describedby');
  expect(describedBy.split(' ')).toContain(`field-${rowIndex}-err`);
  await expect(page.locator(`#field-${rowIndex}-err`)).toContainText(MESSAGE);

  // The summary link takes the user to the field.
  await summary.getByRole('button').first().click();
  await expect(control).toBeFocused();

  // Fixing the field removes its own error.
  await control.fill(original);
  await expect(page.locator(`#field-${rowIndex}-err`)).toHaveCount(0);
  await expect(summary).toBeHidden();
  await page.unroute('**/api/config/rows');
});

test('Add trust account opens a labelled dialog with a trust-type select', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');
  await page.getByRole('button', { name: 'Add trust account' }).click();

  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-modal', 'true');
  const name = dialog.locator('input.inapp-modal-input');
  await expect(name).toBeFocused();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  // focus returns to the button that opened it
  await expect(page.getByRole('button', { name: 'Add trust account' })).toBeFocused();

  await page.getByRole('button', { name: 'Add trust account' }).click();
  await page.locator('.inapp-modal-input').fill('WI020 Trust');
  await page.locator('.inapp-confirm').click();
  const typeSelect = page.locator('select.inapp-modal-input');
  await expect(typeSelect).toBeVisible();
  await expect(typeSelect.locator('option')).toHaveText(['Revocable', 'Irrevocable', 'Credit Shelter', 'QTIP', 'Special Needs', 'Other']);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
