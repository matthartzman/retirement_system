// J3: navigate the guided-step sidebar without a dead end, and regression-test
// the jump-to-field fix (Wave 1.4, `revealAndFocus` in frontend/js/dashboard.js)
// against a REAL browser instead of the synthetic DOM probe used to verify it
// interactively. System review 2026-08-04, finding
// `no-browser-execution-testing` / `ui-accordion-breaks-jump-to-field`.
import { test, expect } from '@playwright/test';
import { openCurrentPlan } from './helpers.js';

// Steps that fetch build/results-derived data as part of their own render
// (economic_tax_assumptions previews Results Explorer data) legitimately
// 404 on /api/detailed-results and /api/summary when no build has run yet --
// which is true throughout this spec, since it never triggers one (that's
// J2, tests/e2e/build-and-results.spec.js). Confirmed by isolating exactly
// which step triggers each URL before allow-listing it: this is expected
// pre-build behavior, not a broken link, and the step's own copy says
// "rebuild ... to see the full result." A change that makes an UNRELATED
// step 404, or 404s a URL not in this list, should still fail the test.
const EXPECTED_PRE_BUILD_404_PATHS = ['/api/detailed-results', '/api/summary'];

function isExpectedPreBuild404(url) {
  return EXPECTED_PRE_BUILD_404_PATHS.some((path) => url.includes(path));
}

// A single continuous session covers both checks, rather than two independent
// tests -- more representative of how this stateful, desktop-style app is
// actually used (one continuous session), and it avoids paying the
// open-the-plan flow's cost twice.
test('guided-step navigation has no dead ends, and jump-to-field opens a closed accordion', async ({ page }) => {
  const consoleErrors = [];
  const unexpected404s = [];
  page.on('console', (msg) => {
    // "Failed to load resource" carries no URL in msg.text(), so it can't be
    // attributed to a specific request here -- the response listener below
    // does that precisely instead. Keep this signal for genuine JS runtime
    // errors (a broken handler, a render-time exception), which is what this
    // assertion is actually meant to catch.
    if (msg.type() === 'error' && !msg.text().includes('Failed to load resource')) {
      consoleErrors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => consoleErrors.push(String(err)));
  page.on('response', (res) => {
    if (res.status() === 404 && !isExpectedPreBuild404(res.url())) unexpected404s.push(res.url());
  });

  await openCurrentPlan(page);

  // --- Part 1: every top-level nav step renders without a dead end -------
  const stepIds = await page.locator('[data-step-id]').evaluateAll((els) =>
    [...new Set(els.map((el) => el.getAttribute('data-step-id')))],
  );
  expect(stepIds.length).toBeGreaterThan(10); // sanity: the nav actually has steps

  for (const stepId of stepIds) {
    await page.evaluate((id) => window.setStep(id), stepId);
    const mainPane = page.locator('#mainPane');
    await expect(mainPane).not.toBeEmpty();
    // A step rendering only its own eyebrow/title (no body content) is the
    // "blank pane" failure mode this test exists to catch.
    const text = await mainPane.innerText();
    expect(text.length, `step "${stepId}" rendered too little content`).toBeGreaterThan(20);
  }

  expect(consoleErrors, `console errors while visiting: ${consoleErrors.join(' | ')}`).toEqual([]);
  expect(unexpected404s, `unexpected 404s while visiting: ${unexpected404s.join(' | ')}`).toEqual([]);

  // --- Part 2: jump-to-field opens a closed accordion and focuses it -----
  // Discover a real (step, row) target at runtime instead of hardcoding one.
  //
  // This originally pinned row 361 -- the DAF "Enabled" toggle inside the
  // Donor-Advised Fund accordion on Other Spending. #269 removed that
  // duplicate section (its canonical home is now the Charitable Giving step),
  // so the locator matched nothing and the test hung to its 120s timeout.
  // Other Spending in fact has NO [data-row] fields left at all: Travel and
  // Large Items are budget-line tables. A row index is just a position in the
  // plan-data CSV and shifts whenever rows are added or removed, so scanning
  // for the behaviour keeps this honest across UI moves rather than pinning a
  // coordinate that silently rots.
  const target = await page.evaluate((ids) => {
    for (const stepId of ids) {
      window.setStep(stepId);
      for (const d of document.querySelectorAll('details:not([open])')) {
        const row = d.querySelector('[data-row]');
        if (row) return { stepId, row: Number(row.getAttribute('data-row')) };
      }
    }
    return null;
  }, stepIds);
  expect(
    target,
    'no step has a [data-row] inside a closed accordion -- jump-to-field reveal is no longer exercisable',
  ).not.toBeNull();

  const targetRow = target.row;
  await page.evaluate((stepId) => window.setStep(stepId), target.stepId);

  const detailsBefore = await page
    .locator(`[data-row="${targetRow}"]`)
    .evaluate((el) => el.closest('details')?.open);
  expect(
    detailsBefore,
    `${target.stepId} row ${targetRow} is expected to start inside a CLOSED accordion`,
  ).toBe(false);

  await page.evaluate(
    ({ stepId, row }) => window.jumpRecommendationSource(stepId, row),
    target,
  );

  // jumpRecommendationSource defers its scroll/reveal/focus work via its own
  // internal setTimeout(..., 80) (frontend/js/dashboard.js), so a check made
  // synchronously right after calling it races that delay. waitForFunction
  // polls until the real condition is true instead of guessing a fixed wait.
  await page.waitForFunction(
    (row) => document.querySelector(`[data-row="${row}"]`)?.closest('details')?.open === true,
    targetRow,
    { timeout: 5000 },
  );
  const detailsAfter = await page
    .locator(`[data-row="${targetRow}"]`)
    .evaluate((el) => el.closest('details')?.open);
  expect(detailsAfter, 'revealAndFocus did not open the containing <details>').toBe(true);

  // .focus() on a <label> moves focus to its associated form control in
  // Chrome (confirmed interactively) -- so the correct assertion is that
  // focus landed somewhere INSIDE the revealed accordion, not on the exact
  // label element itself.
  const focusInsideAccordion = await page.evaluate((row) => {
    const details = document.querySelector(`[data-row="${row}"]`)?.closest('details');
    return !!details && details.contains(document.activeElement);
  }, targetRow);
  expect(focusInsideAccordion, 'focus did not land inside the revealed accordion').toBe(true);
});
