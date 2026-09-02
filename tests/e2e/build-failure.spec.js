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
import { test, expect } from '@playwright/test';
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
});
