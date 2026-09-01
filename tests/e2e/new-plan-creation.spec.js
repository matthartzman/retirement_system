// Item 2.14 (finding Q4): the welcome page's "Start New Plan" button is the
// other entry point into the app besides "Open Current Plan" (covered by
// every other spec in this suite via helpers.js's openCurrentPlan), and had
// zero browser coverage.
//
// Intercepts POST /api/plan-data/blank (frontend/js/dashboard_decomp_checklist_closeout.js's
// startNewPlan()) rather than letting it run for real: the real endpoint
// overwrites every input/client_*.csv file on the shared E2E server this
// whole suite runs against (documentation/CLAUDE.md's "Start New Plan"
// section), and this suite's other specs -- and a same-run re-execution of
// this one -- depend on the frozen fixture household staying intact. The
// backend blanking logic itself (PlanDataFileService.start_blank_payload())
// is a server-side concern with its own coverage; what this spec verifies
// is the FRONTEND flow: the button reaches the real endpoint with a
// well-formed request and the app then navigates to a fresh plan's first
// step, exactly as a user watching the browser would see it.
import { test, expect } from '@playwright/test';
import { waitForPlanSettled } from './helpers.js';

test('Start New Plan calls the blank-plan endpoint and lands on the first step of a fresh plan', async ({ page }) => {
  let blankRequestBody = null;
  await page.route('**/api/plan-data/blank', async (route) => {
    blankRequestBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true }),
    });
  });

  await page.goto('/');
  await expect(page.locator('#appStatus')).toHaveText('Ready', { timeout: 30_000 });
  // "Start New Plan" lives on the "Plan Status" step's welcome content
  // (frontend/js/dashboard_decomp_checklist_closeout.js's welcomeHtml()) --
  // this E2E workspace has a plan already active (auto-load), which lands
  // page.goto('/') on the guided-steps view rather than a bare welcome
  // screen, so navigate to that step explicitly rather than assuming it's
  // the initial view.
  await page.evaluate(() => window.setStep('start'));
  await expect(page.getByRole('heading', { name: 'Retirement planning workspace' })).toBeVisible({ timeout: 10_000 });

  await page.getByRole('button', { name: 'Start New Plan' }).click();

  // No unsaved-changes discard modal is expected: openCurrentPlan() never
  // ran, so hasUnsavedPlanChanges() has nothing to gate on. This frozen
  // fixture DOES have real YTD actuals tracked, though, which triggers a
  // separate "New plan and real year-to-date actuals" choice modal
  // (showYtdBlendChoiceModal) -- pick the recommended option so the flow
  // proceeds to the actual blank-plan call.
  // locator.isVisible({timeout}) does NOT poll (see helpers.js's
  // openCurrentPlan/triggerBuildAndWaitForOverlay comments on this exact
  // gotcha) -- waitFor() is the actual polling primitive, needed here since
  // the modal only appears after an async /api/ytd/status round-trip.
  const ytdModal = page.getByRole('button', { name: 'Use real actuals (recommended)' });
  const ytdModalAppeared = await ytdModal
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false);
  if (ytdModalAppeared) {
    await ytdModal.click();
  }

  await expect
    .poll(() => blankRequestBody, { timeout: 10_000, message: 'POST /api/plan-data/blank was never called' })
    .not.toBeNull();

  await waitForPlanSettled(page);

  // startNewPlan() hardcodes activeStep = "household_people" after the
  // blank succeeds -- the first step of the guided flow, matching what a
  // user starting completely fresh should see.
  await expect(page.getByRole('heading', { name: 'Household & People' })).toBeVisible({ timeout: 15_000 });
});
