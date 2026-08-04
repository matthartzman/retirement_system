// J3: navigate the guided-step sidebar without a dead end, and regression-test
// the jump-to-field fix (Wave 1.4, `revealAndFocus` in frontend/js/dashboard.js)
// against a REAL browser instead of the synthetic DOM probe used to verify it
// interactively. System review 2026-08-04, finding
// `no-browser-execution-testing` / `ui-accordion-breaks-jump-to-field`.
import { test, expect } from '@playwright/test';

// Loading the frozen plan is a two-step real-user action, discovered by
// driving the actual app rather than assuming an API call is enough:
// visiting `/` alone leaves the app on the "Start a plan" welcome screen with
// no plan data loaded into frontend state (data-step-id nav buttons exist,
// but setStep() no-ops back to 'start' while getPlanLoaded() is false).
// "Open Current Plan" loads the backend's plan data into that state; only
// after that does client-side navigation to any other step actually work.
async function openCurrentPlan(page) {
  await page.goto('/');
  await expect(page.locator('#appStatus')).toHaveText('Ready', { timeout: 30_000 });
  await page.getByRole('button', { name: 'Open Current Plan' }).click();
  // A stale "unsaved changes" exit-confirmation modal can appear on this
  // click in a fresh session; dismiss it if present rather than let it block
  // every subsequent step navigation in this spec.
  const keepEditing = page.getByRole('button', { name: 'Keep Editing' });
  if (await keepEditing.isVisible({ timeout: 1000 }).catch(() => false)) {
    await keepEditing.click();
  }
  // Loading the plan fires a batch of async fetches (config rows, holdings,
  // liabilities, YTD status, ...); window.setStep() silently no-ops back to
  // 'start' while the app's internal getPlanLoaded() is still false. Calling
  // setStep() right after the click (a fixed short wait was tried first and
  // was flaky) raced that load and landed back on the Plan Status step
  // instead of the one requested. networkidle is the reliable signal.
  await page.waitForLoadState('networkidle');
}

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
// tests. This is not just cheaper -- it is more correct: this app is a
// stateful desktop-style tool, not a stateless per-request API, and reopening
// "Open Current Plan" a second time against the SAME already-running backend
// session (which Playwright's webServer intentionally reuses across every
// test in the file, matching how the real app is used) was observed to behave
// differently the second time -- the plan never finished loading and the step
// never rendered. Chasing that server-session interaction is out of scope
// here; one continuous session sidesteps it and matches real usage anyway.
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
  await page.evaluate(() => window.setStep('lifestyle_spending'));
  await expect(page.getByRole('heading', { name: 'Other Spending' })).toBeVisible({ timeout: 10_000 });

  // Real target on the frozen fixture: row 361 is the DAF "Enabled" toggle,
  // rendered inside a closed <details>Donor-Advised Fund (DAF)</details>
  // accordion by renderLifestyleSpending() -- exactly the Travel/Large
  // Discretionary/DAF class of field the original bug affected. Confirmed
  // interactively before writing this spec: data-row="361" resolves to a
  // <label> wrapping the checkbox, not the checkbox itself.
  const detailsBefore = await page
    .locator('[data-row="361"]')
    .evaluate((el) => el.closest('details')?.open);
  expect(detailsBefore, 'fixture drifted: row 361 is expected to start inside a CLOSED accordion').toBe(false);

  await page.evaluate(() => window.jumpRecommendationSource('lifestyle_spending', 361));

  // jumpRecommendationSource defers its scroll/reveal/focus work via its own
  // internal setTimeout(..., 80) (frontend/js/dashboard.js), so a check made
  // synchronously right after calling it races that delay. waitForFunction
  // polls until the real condition is true instead of guessing a fixed wait.
  await page.waitForFunction(
    () => document.querySelector('[data-row="361"]')?.closest('details')?.open === true,
    { timeout: 5000 },
  );
  const detailsAfter = await page
    .locator('[data-row="361"]')
    .evaluate((el) => el.closest('details')?.open);
  expect(detailsAfter, 'revealAndFocus did not open the containing <details>').toBe(true);

  // .focus() on a <label> moves focus to its associated form control in
  // Chrome (confirmed interactively) -- so the correct assertion is that
  // focus landed somewhere INSIDE the revealed accordion, not on the exact
  // label element itself.
  const focusInsideAccordion = await page.evaluate(() => {
    const details = document.querySelector('[data-row="361"]')?.closest('details');
    return !!details && details.contains(document.activeElement);
  });
  expect(focusInsideAccordion, 'focus did not land inside the revealed accordion').toBe(true);
});
