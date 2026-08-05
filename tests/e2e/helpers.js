// Shared helpers for the Playwright E2E suite (tests/e2e/). Extracted after
// both J1 and J3 independently hit the same flaky pattern: openCurrentPlan()
// resolves (networkidle fires) before window.planLoaded -- a closure-private
// variable in frontend/js/dashboard.js, not exposed for a test to poll
// directly -- has actually flipped true. window.setStep() silently no-ops
// back to 'start' while it is still false, so a single setStep() call right
// after opening the plan can land on the wrong page.
//
// This was reproducible ~25% of the time in this suite's own field-save-persist
// spec specifically on its SECOND openCurrentPlan() call within one test (the
// reload-and-verify step, after a real save had just happened) -- rare enough
// to pass a single verification run and still break CI. A minimal repro of
// "open the plan twice in two separate tests" was reliable, which narrowed
// the flake to timing around the load-after-save path specifically, not an
// inherent one-open-per-session limitation.
import { expect } from '@playwright/test';

export async function openCurrentPlan(page) {
  await page.goto('/');
  await expect(page.locator('#appStatus')).toHaveText('Ready', { timeout: 30_000 });
  await page.getByRole('button', { name: 'Open Current Plan' }).click();
  const keepEditing = page.getByRole('button', { name: 'Keep Editing' });
  if (await keepEditing.isVisible({ timeout: 1000 }).catch(() => false)) {
    await keepEditing.click();
  }
  await page.waitForLoadState('networkidle');
}

// Navigates to `stepId` and waits for `headingText` to actually appear,
// RETRYING window.setStep() rather than calling it once and hoping the plan
// finished loading. setStep() is idempotent and safe to call repeatedly, so
// this is robust to the timing regardless of what exactly delays
// planLoaded -- it succeeds as soon as the real condition is true instead of
// guessing how long to wait first.
export async function navigateToStep(page, stepId, headingText) {
  const heading = page.getByRole('heading', { name: headingText });
  const deadline = Date.now() + 10_000;
  let lastError;
  while (Date.now() < deadline) {
    await page.evaluate((id) => window.setStep(id), stepId);
    try {
      await expect(heading).toBeVisible({ timeout: 500 });
      return;
    } catch (e) {
      lastError = e;
    }
  }
  throw lastError ?? new Error(`navigateToStep("${stepId}") never showed heading "${headingText}"`);
}

// Clicks "Build Reports" and waits for the build overlay to reach a TERMINAL
// title ("Build complete" or "Build failed") -- not merely for it to leave
// its "active" CSS state, which turned out to be an unreliable signal:
// runBuild() calls hideBuildOverlay() (removing .active) BEFORE awaiting the
// "Preflight Warnings" confirmation modal that appears on a first-ever build
// (no output package exists yet, frontend/js/dashboard.js), so ".active"
// goes away at that intermediate pause too, not just at real completion. A
// first version of this helper waited for "not .active" and returned
// immediately with the overlay still reading "Checking build preflight" --
// passing the wait without the build ever actually running.
export async function triggerBuildAndWaitForOverlay(page) {
  await page.getByRole('button', { name: 'Build Reports' }).first().click();

  // locator.isVisible({timeout}) does NOT poll -- it is a one-shot immediate
  // check (Playwright resolves the element handle within `timeout`, but
  // returns false right away if the element simply doesn't exist YET rather
  // than waiting for it to appear). Using it here always returned false,
  // since preflight (a real API round-trip computing warnings) hadn't
  // resolved yet at the moment of the check, and the build then stalled the
  // full 60s at "Checking build preflight" with the modal never clicked.
  // waitFor() is the actual polling primitive.
  const continueBuild = page.locator('.inapp-confirm', { hasText: 'Continue Build' });
  const modalAppeared = await continueBuild
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => true)
    .catch(() => false);
  if (modalAppeared) {
    await continueBuild.click();
  }

  const title = page.locator('.build-overlay .build-progress-title');
  // The real build (Monte Carlo + 27 workbook sheets, even with the reduced
  // sim counts tools/e2e_server.py sets) took ~26s in isolation but ran past
  // 60s under repeated-run system load while still genuinely progressing
  // (observed reaching the late-stage "Finalizing workbook" phase, not stuck
  // at the start) -- 80s leaves headroom under Playwright's own 90s test
  // timeout without that margin evaporating under load.
  await expect(title, 'build overlay never reached a terminal state').toHaveText(
    /^Build (complete|failed)$/,
    { timeout: 80_000 },
  );
  return title.innerText();
}
