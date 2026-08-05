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
// household_people step, a plain text input wired
// oninput="editValue(28,this.value,this)" onblur="finishEdit(28,this)".
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

  await field.fill(EDITED_VALUE);
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
});
