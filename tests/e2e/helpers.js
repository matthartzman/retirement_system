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
