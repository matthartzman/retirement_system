// J2: trigger a build, poll status, view real results in Results Explorer.
// System review 2026-08-04, finding `no-browser-execution-testing`.
//
// This spec found a genuine, previously-undetected server-side bug while
// being written, not a test-infrastructure issue: see the "Build failed"
// section below.
import { test, expect } from '@playwright/test';
import { openCurrentPlan, navigateToStep, triggerBuildAndWaitForOverlay } from './helpers.js';

test('triggering a build renders real results in Results Explorer', async ({ page }) => {
  // A real build measures ~110s (see triggerBuildAndWaitForOverlay), so this
  // cannot run inside the project default 120s per-test timeout -- the build
  // alone consumes it before the Results Explorer assertions even start.
  test.setTimeout(420_000);
  await openCurrentPlan(page);

  // --- Build -------------------------------------------------------------
  const finalTitle = await triggerBuildAndWaitForOverlay(page);

  // This assertion FAILED against the real app before src/server/workbook_routes.py
  // was fixed in this same change: /api/build/start computed output_dir via
  // workspace_output_dir(workspace_id, BASE_DIR), where BASE_DIR
  // (app_core.py) is Path(__file__).resolve().parents[2] -- the real package
  // directory, fixed at import time and never redirected by
  // RETIREMENT_SYSTEM_WORKSPACE_ROOT. The build subprocess correctly
  // inherited the redirected root (env=os.environ.copy()) and wrote a
  // genuinely successful build -- workbook, PDF, results model, all present,
  // terminal net worth matching the frozen fixture's known-good pins -- to
  // the ISOLATED workspace. The route then checked for plan_summary.json in
  // the WRONG (real) directory, found nothing, and reported "Build
  // completed, but no current plan_summary.json was produced" -- shown to
  // the user as "Build failed" on a build that had, in fact, fully
  // succeeded. Confirmed via /api/build/status and /api/build/progress/<id>
  // (whose event log showed every workbook sheet being written, then a
  // failure event with output_dir pointing at the repo, not the workspace)
  // before touching any source. This would affect any real deployment with
  // a custom RETIREMENT_SYSTEM_WORKSPACE_ROOT, not just this test harness.
  expect(finalTitle, 'the build failed -- see this spec file\'s comment for the bug this line guards against').toBe('Build complete');

  // --- Results -------------------------------------------------------------
  await navigateToStep(page, 'detailed_results', 'Reports & Review');
  await page.getByRole('button', { name: 'Results', exact: true }).click();

  // Real content from the real build, not a placeholder/empty state. The
  // sheet list and the "N rows" summaries only appear once
  // results_explorer_model.json has actually been parsed and rendered.
  await expect(page.getByText(/\d+ result sheets from retirement_plan\.xlsx/)).toBeVisible({ timeout: 15_000 });

  // "1A. Executive Summary" legitimately appears more than once (the left
  // nav's own jump-list, plus the results sheet picker) and some of those
  // matches are inside elements Playwright's locator visibility model treats
  // as hidden (e.g. an unopened <select>'s <option>) even though the text is
  // genuinely on screen via a different element. #mainPane.innerText mirrors
  // what a user actually sees (like the browser's own innerText, it already
  // excludes hidden content) without needing to pick the "right" one of
  // several duplicate matches -- this test cares that the content rendered,
  // not which specific DOM node carries it.
  const mainPaneText = await page.locator('#mainPane').innerText();
  expect(mainPaneText).toContain('1A. Executive Summary');
  expect(mainPaneText).toMatch(/Executive Summary\s*\n?\s*\d+ rows/);

  // The empty-state failure mode this test exists to catch: a build that
  // "succeeds" per the overlay but leaves Results Explorer showing nothing
  // useful (a JS exception mid-render, a model the UI can't parse, ...).
  expect(mainPaneText.length, 'Results Explorer rendered too little content for a completed build').toBeGreaterThan(300);
});
