// J1: edit a field, save, reload, confirm persisted. System review
// 2026-08-04, finding `no-browser-execution-testing` -- "the only way to
// catch a broken onclick handler [or] a JS exception on render." This is the
// core data-entry loop every other feature sits on top of, and it had zero
// browser-level coverage before this suite.
//
// Mechanics below (which field, which events, which button, what confirms a
// save happened) were verified interactively against the real running app
// before being encoded here -- see the harness verification in the Wave 2.1
// scoping pass, not assumed from reading the source.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

// Real target on the frozen fixture: row 28 is "Residence State" on the
// household_people step -- a <select> of the 50 states + DC (#260,
// dashboard_decomp_state_inputs.js), not the plain text input it used to be.
// household_people is one of the AUTOSAVE_STEPS (navigation.js), but this
// test uses the header's "Save Changes" button instead of navigating away --
// that button calls saveAll(true), the same saveWorkingCopy() both the
// autosave and manual-save paths share, so it exercises the identical save
// mechanism without depending on navigation-triggered autosave timing.
const FIELD_ROW = 28;
const ORIGINAL_VALUE = 'Illinois';
const EDITED_VALUE = 'Wisconsin';

test('editing a field, saving, and reloading persists the change', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');

  const field = page.locator(`[data-row="${FIELD_ROW}"]`);
  await expect(field).toHaveValue(ORIGINAL_VALUE);

  const saveButton = page.locator('#saveChangesBtn');
  await expect(saveButton).toBeDisabled(); // nothing dirty yet

  try {
    await field.selectOption(EDITED_VALUE);
    await field.blur();
    await expect(saveButton, 'editing a field did not enable the Save button').toBeEnabled();
    await expect(page.locator('#unsavedStatus')).toBeVisible();

    await saveButton.click();
    await expect(page.locator('#actionMessage'), 'no save confirmation appeared').toContainText('Changes saved.');
    await expect(saveButton, 'Save button did not return to disabled after a successful save').toBeDisabled();
    await expect(page.locator('#unsavedStatus')).toBeHidden();

    // The real regression check: reload from scratch (a fresh network request
    // cycle, not just in-memory state) and confirm the edit actually reached
    // the backend rather than only updating the DOM.
    await openCurrentPlan(page);
    await navigateToStep(page, 'household_people', 'Household & People');
    await expect(
      page.locator(`[data-row="${FIELD_ROW}"]`),
      'edited value did not survive a full page reload',
    ).toHaveValue(EDITED_VALUE);
  } finally {
    // Revert regardless of pass/fail: this spec runs against the SAME shared
    // e2e workspace database as every other spec file, and EDITED_VALUE
    // ('Wisconsin') is not in reference_data/state_tax.csv's supported list
    // -- left in place, it fails the next real build any LATER spec in the
    // run triggers with "Unsupported residence_state 'Wisconsin'", a
    // completely unrelated-looking error nowhere near this file. Confirmed
    // directly: workbook-format-stale-cache.spec.js failed this way when run
    // after this spec in the full suite.
    // Every step here is individually best-effort. When the body above fails,
    // the page is often already closing, and an unguarded call in a `finally`
    // REPLACES the real assertion error with its own -- this block used to
    // report "locator.selectOption: Target page, context or browser has been
    // closed" after burning the full 120s test timeout, which is what the
    // actual CI failure looked like for days while the real cause (the Save
    // button never enabling) was only visible on the retry that happened to
    // fail differently. Cleanup must never be able to outrank the diagnosis.
    const current = await field.inputValue().catch(() => null);
    if (current !== null && current !== ORIGINAL_VALUE) {
      await field.selectOption(ORIGINAL_VALUE, { timeout: 5_000 }).catch(() => {});
      await field.blur().catch(() => {});
      await saveButton.click({ timeout: 5_000 }).catch(() => {});
      await expect(page.locator('#actionMessage')).toContainText('Changes saved.', { timeout: 10_000 }).catch(() => {});
    }
  }
});
