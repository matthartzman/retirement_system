// Item 2.14 (finding Q4): a genuinely FAILED build must be visible to the
// user, not just a successful one -- build-and-results.spec.js only covers
// the happy path, and a real failing build takes the same ~90-110s a
// successful one does (see helpers.js's triggerBuildAndWaitForOverlay),
// which would make this spec too slow to run routinely.
//
// Instead of running a real failing build, this intercepts the two API
// calls buildWithProgress() makes (frontend/js/dashboard_decomp_build_lifecycle.js)
// -- POST /api/build/start and GET /api/build/progress/<job_id> -- and
// returns a synthetic FAILED job, shaped exactly like a real one from
// server_services/build_job_service.py's run_build_progress_job (see
// tests/test_build_failure_error_path_integration.py, item 2.13, which
// locks in that exact shape on the Python side). This exercises the real
// frontend failure-handling code path (buildWithProgress's polling loop,
// the overlay reaching "Build failed", and the toast surfacing the real
// error message) without spending ~90s on the real build subprocess and
// without touching the shared E2E server's actual plan data at all.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, triggerBuildAndWaitForOverlay } from './helpers.js';

test('a failed build surfaces "Build failed" and the real error message, not a silent hang', async ({ page }) => {
  const FAKE_JOB_ID = 'e2e-synthetic-failed-job';
  const FAKE_ERROR = 'ValueError: household config is missing plan_start (synthetic E2E failure)';

  await page.route('**/api/build/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, job_id: FAKE_JOB_ID, progress: 0, phase: 'Preparing build' }),
    });
  });

  await page.route(`**/api/build/progress/${FAKE_JOB_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        job: {
          job_id: FAKE_JOB_ID,
          status: 'failed',
          progress: 100,
          phase: 'Build failed',
          detail: 'Build process returned an error.',
          result: { success: false, returncode: 1, error: FAKE_ERROR },
        },
      }),
    });
  });

  await openCurrentPlan(page);

  const finalTitle = await triggerBuildAndWaitForOverlay(page);
  expect(finalTitle).toBe('Build failed');

  // buildWithProgress() throws new Error(result.error) on job.status ===
  // "failed", and the outer catch in runBuild() (dashboard_decomp_row_model.js)
  // shows it via showMessage("Error building: " + e.message, "error") --
  // the ONE place the real backend error text reaches the user, since the
  // overlay's own detail line is overwritten by an elapsed-time ticker (see
  // dashboard_decomp_build_lifecycle.js's refreshBuildOverlayTimer) rather
  // than ever showing job.detail/result.error.
  const toast = page.locator('#actionMessage');
  await expect(toast).toContainText(FAKE_ERROR, { timeout: 5_000 });

  // UX-003 (system review 2026-09-25, WI-504): the error is announced
  // (role=alert) and stays until dismissed instead of vanishing after the
  // old 10 s auto-hide. The raw "ValueError: ..." text now sits in the
  // toast's Technical details disclosure (still part of its text, above).
  await expect(toast).toHaveAttribute('role', 'alert');
  await page.waitForTimeout(11_000);
  await expect(toast).toBeVisible();
});

// ARC-004 / UX-009 (system review 2026-09-25, Wave 1 item WI-106):
// buildWithProgress()'s fallback to the legacy synchronous /api/build
// endpoint used to be a catch wrapping the ENTIRE polling loop, keyed on
// free-text-matching the error message for "404"/"not found" -- so a real
// build failure whose own error text happens to contain "not found" (e.g.
// "Plan Data folder not found: ...") was
// indistinguishable from the /api/build/start endpoint itself being
// missing, and triggered a second, fully synchronous build instead of
// surfacing the real failure. This pins that a job that reports "failed"
// with a "not found" message never issues that second POST /api/build,
// once a job_id has already been returned.
test('a failed job whose error mentions "not found" does not trigger a fallback build', async ({ page }) => {
  const FAKE_JOB_ID = 'e2e-synthetic-not-found-failed-job';
  const FAKE_ERROR = 'Plan Data folder not found: input/missing_plan';
  let fallbackBuildCalled = false;

  await page.route('**/api/build/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, job_id: FAKE_JOB_ID, progress: 0, phase: 'Preparing build' }),
    });
  });

  await page.route(`**/api/build/progress/${FAKE_JOB_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        job: {
          job_id: FAKE_JOB_ID,
          status: 'failed',
          progress: 100,
          phase: 'Build failed',
          detail: 'Build process returned an error.',
          result: { success: false, returncode: 1, error: FAKE_ERROR },
        },
      }),
    });
  });

  // The legacy fallback endpoint -- must never be called from this scenario.
  await page.route('**/api/build', async (route) => {
    if (route.request().method() === 'POST') {
      fallbackBuildCalled = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
      return;
    }
    await route.continue();
  });

  await openCurrentPlan(page);

  const finalTitle = await triggerBuildAndWaitForOverlay(page);
  expect(finalTitle).toBe('Build failed');

  const toast = page.locator('#actionMessage');
  await expect(toast).toContainText(FAKE_ERROR, { timeout: 5_000 });
  expect(fallbackBuildCalled).toBe(false);
});
