// Finding QUA-301 (system review 2026-09-07, Wave 5 item W5-5): the Monarch
// auto-update card (frontend/js/dashboard_decomp_monarch_autoupdate.js)
// exercises the exact fetch/module/global-bridge pattern that previously
// caused a real production outage (see script-order-spike.spec.js), with
// zero e2e coverage of its own. This exercises the real page: load the
// Data & Maintenance step, flip the enable checkbox (autosave, no Save
// button -- W5-8/UX-103), verify it persisted across a fresh navigation,
// then trigger "Import now" and verify the status line changes.
//
// Sequenced after W5-8 so this exercises the corrected autosave flow, not
// the old manual-save one. Writing this spec surfaced two real bugs:
//
// 1. saveMonarchAutoUpdatePolicy() called renderMain() synchronously before
//    its save request resolved, which rebuilt the checkbox from the still-
//    stale pre-save policy -- visibly snapping a just-checked box back to
//    unchecked (while disabled) the instant a user toggled it. Fixed by
//    capturing the user's actual in-flight selection
//    (monarchAutoUpdatePendingPolicy) before that busy-state render, so it
//    reflects what was just submitted, not the last-saved server value.
//
// 2. The source_dir default ("Monarch Extractor/output") doesn't exist in a
//    fresh workspace, so a real "Import now" click there returns
//    success:false (a missing-folder error, not a benign empty-folder
//    skip) -- and the server route maps success:false to HTTP 400, which
//    api()/RetirementApiClient throws on, so runMonarchAutoUpdateNow()'s
//    catch swallows it without ever updating monarchAutoUpdateStatus. That
//    behavior is correct (a genuinely missing configured folder should
//    surface as an error, not silently look like nothing happened) but it
//    means this spec must point source_dir at a directory that actually
//    exists to exercise the success path -- "input" always exists in any
//    staged workspace and holds no Monarch export files, so it exercises
//    the real success+"no_rows" skip branch (mau.write_status runs, the
//    status line changes) without needing real Monarch Extractor output.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('Monarch settings card: toggle persists via autosave, and Import now updates status', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'system_configuration', 'Data & Maintenance');

  const card = page.locator('.monarch-autoupdate-card');
  await expect(card).toBeVisible({ timeout: 10_000 });

  // W5-8 removed the manual "Save setting" button in favor of autosave --
  // this is the regression QUA-301/W5-5 exists to catch if it ever comes back.
  await expect(card.getByRole('button', { name: /^Save/ })).toHaveCount(0);

  const checkbox = card.locator('#monarchAutoUpdateEnabled');
  const sourceDirInput = card.locator('#monarchAutoUpdateSourceDir');
  const statusLine = page.locator('.monarch-autoupdate-card p', { hasText: 'Status:' });
  const originalChecked = await checkbox.isChecked();
  const originalSourceDir = await sourceDirInput.inputValue();

  try {
    // "Import now" is only interesting to verify while enabled -- the status
    // line always reads "Off" while disabled (monarchAutoUpdateStatusLine()),
    // regardless of whether a run just happened, so exercise both the
    // autosave-persistence contract and the import round trip against the
    // enabled state rather than toggling to whatever the opposite of
    // whatever state the card happened to load in.
    await checkbox.setChecked(true);

    // No save click -- onchange (dashboard_decomp_monarch_autoupdate.js)
    // fires saveMonarchAutoUpdatePolicy() directly. Wait for the busy
    // indicator to clear so the request has actually round-tripped before
    // asserting persistence.
    await expect(card.getByText('Saving…')).toHaveCount(0, { timeout: 10_000 });

    // Point source_dir at a directory that genuinely exists (see header
    // comment) so the upcoming "Import now" exercises the real success path.
    await sourceDirInput.fill('input');
    await sourceDirInput.blur();
    await expect(card.getByText('Saving…')).toHaveCount(0, { timeout: 10_000 });

    // Independent proof both values are on disk/DB, not just the in-memory
    // policy this same page session already trusts: a fresh navigation
    // away and back re-fetches monarch-autoupdate status from the server.
    await navigateToStep(page, 'start', 'Retirement planning workspace');
    await navigateToStep(page, 'system_configuration', 'Data & Maintenance');
    const reloadedCheckbox = page.locator('.monarch-autoupdate-card #monarchAutoUpdateEnabled');
    const reloadedSourceDir = page.locator('.monarch-autoupdate-card #monarchAutoUpdateSourceDir');
    await expect(reloadedCheckbox).toHaveJSProperty('checked', true, { timeout: 10_000 });
    await expect(reloadedSourceDir).toHaveValue('input', { timeout: 10_000 });

    const importButton = page.locator('.monarch-autoupdate-card').getByRole('button', { name: /Import now|Importing…/ });
    const statusBefore = await statusLine.innerText();
    await importButton.click();

    // A real, successful (if uneventful -- "input" holds no Monarch export
    // files) run: what matters here is that the fetch/render round trip
    // works end to end and write_status() records a real run, changing the
    // status line from whatever it read before the click.
    await expect(statusLine, 'status line never updated after Import now').not.toHaveText(statusBefore, {
      timeout: 15_000,
    });
    await expect(importButton).toHaveText('Import now', { timeout: 15_000 });
  } finally {
    await sourceDirInput.fill(originalSourceDir);
    await sourceDirInput.blur();
    await expect(card.getByText('Saving…')).toHaveCount(0, { timeout: 10_000 });
    await checkbox.setChecked(originalChecked);
    await expect(card.getByText('Saving…')).toHaveCount(0, { timeout: 10_000 });
    await expect(checkbox).toHaveJSProperty('checked', originalChecked, { timeout: 10_000 });
  }
});
