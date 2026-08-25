// Shared helpers for the Playwright E2E suite (tests/e2e/). Extracted after
// both J1 and J3 independently hit the same flaky pattern: openCurrentPlan()
// resolves (networkidle fires) before window.planLoaded -- a closure-private
// variable in frontend/js/dashboard.js -- has actually flipped true.
// window.setStep() silently no-ops back to 'start' while it is still false,
// so a single setStep() call right after opening the plan can land on the
// wrong page.
//
// This was reproducible ~25% of the time in this suite's own field-save-persist
// spec specifically on its SECOND openCurrentPlan() call within one test (the
// reload-and-verify step, after a real save had just happened) -- rare enough
// to pass a single verification run and still break CI. A minimal repro of
// "open the plan twice in two separate tests" was reliable, which narrowed
// the flake to timing around the load-after-save path specifically, not an
// inherent one-open-per-session limitation.
//
// The comment above described the race correctly but this function never
// actually closed it -- there was no wait for planLoaded at all, only
// networkidle. Confirmed directly (2026-08-11): the dashboard.js ES-module
// conversion's generated window bridge means window.planLoaded IS readable
// now (Object.defineProperty accessor for every externally-referenced
// top-level variable), so "not exposed for a test to poll directly" is
// stale -- the fix below was possible the whole time. Root-caused via a
// second-openCurrentPlan build hanging 30+ minutes in CI
// (workbook-format-stale-cache.spec.js): runBuild()'s internal
// saveWorkingCopy() call checks `if (!planLoaded) return false;` FIRST, so
// clicking Build Reports inside this race makes runBuild() silently return
// false having never called preflight -- the build overlay is left showing
// whatever loadAll() last set ("Loading plan"/"Saving current plan"), and a
// test that only waits for a TERMINAL overlay title waits forever for a
// build that never started.
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
  await page.waitForFunction(() => window.planLoaded === true, { timeout: 15_000 });
  // planLoaded flipping true does not mean loadAll() is done -- see
  // waitForPlanSettled's own comment below for the full root cause (a second
  // overlapping loadAll, e.g. the boot load from page.goto() racing the one
  // "Open Current Plan" starts, can still be mid-flight and about to reset
  // planLoaded back to false). navigateToStep() already guards its own
  // callers this way; a caller that goes straight from openCurrentPlan() into
  // an action gated on planLoaded (e.g. triggerBuildAndWaitForOverlay's
  // "Build Reports" click, whose runBuild() silently no-ops if planLoaded is
  // false) needs the same guarantee, so give it here too instead of leaving
  // every such caller to remember it separately.
  await waitForPlanSettled(page);
}

// Waits until no loadAll() is still in flight, which `planLoaded` above does
// NOT establish on its own.
//
// Why this exists (root-caused 2026-08-12 against the running app, not
// inferred): loadAll() in dashboard_decomp_row_model.js ends with, in this
// order, `dirty.clear()`, `planLoaded = true`, then `renderMain()`. So
// planLoaded flips true BEFORE the re-render, and more importantly a SECOND
// overlapping loadAll (the boot load kicked off by page.goto('/'), then the
// one the "Open Current Plan" click starts) can still be mid-flight when the
// first one's planLoaded satisfies the wait above. When that second load
// lands it clears `dirty` and replaces every row node -- silently discarding
// an edit the test had already made and re-disabling the Save button.
//
// That is exactly how field-save-persist.spec.js was failing: observed
// directly in the browser, the edit registered correctly (dirty=1, Save
// enabled), then ~300ms later the row node was replaced, the value snapped
// back to its original, and dirty returned to 0 -- so
// `expect(saveButton).toBeEnabled()` failed 5s later against a button that
// had genuinely been enabled a moment earlier.
//
// networkidle does not cover it: loadAll's tail fires
// fetchCurrentSummaryKpi() and refreshBuildStatus() as unawaited promises, so
// the network can be idle with the re-render still pending.
//
// The signal used here is the one that actually matters to a caller about to
// edit a field: the first [data-row] element has been the SAME DOM node for an
// uninterrupted quiet window. renderMain() is the LAST thing loadAll does
// (after dirty.clear()), and it replaces every row node -- so row-node
// identity holding steady is proof that no loadAll is still pending, and it
// stays correct regardless of which of the two planLoaded bindings a given
// build wires to window.
//
// Deliberately does NOT also require `dirty` to be empty: callers navigate
// with unsaved edits in hand, and an edit the test just made legitimately
// leaves dirty non-empty. Gating on that would hang those callers forever.
// Node identity alone already covers the clobber, since dirty.clear() cannot
// reach a test without the re-render that follows it.
//
// A null probe (steps that render no rows at all) is treated as a stable
// state rather than a failure -- there are no row nodes to be clobbered.
export async function waitForPlanSettled(page, { quietMs = 750, timeout = 20_000 } = {}) {
  await page.waitForFunction(
    (quiet) => {
      const probe = document.querySelector('[data-row]');
      if (window.__e2eSettleNode !== probe) {
        window.__e2eSettleNode = probe;
        window.__e2eSettleSince = Date.now();
        return false;
      }
      return Date.now() - window.__e2eSettleSince >= quiet;
    },
    quietMs,
    { timeout },
  );
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
      // The heading appearing does not mean the page is done changing: a
      // loadAll() still in flight will re-render every row underneath it and
      // clear `dirty`, discarding an edit a caller makes in that window. See
      // waitForPlanSettled below for the full root cause.
      await waitForPlanSettled(page);
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
  // Measured 2026-08-10 on an otherwise-idle machine: one full build through
  // src.build_entry.run_build against the same frozen workspace this server
  // stages takes 106s, and 110s with the reduced RETIREMENT_MC_SIMS=16 /
  // RETIREMENT_MC_SENSITIVITY_SIMS=3 that tools/e2e_server.py sets -- i.e.
  // Monte Carlo is NOT the cost here, so those reductions buy nothing. The
  // previous 80s ceiling (written when a build was ~26s) therefore could not
  // pass even on an idle machine: the overlay was consistently observed at
  // the late-stage "Writing workbook pages" when the deadline hit, still
  // progressing rather than stuck. 240s is ~2x the measured build so a loaded
  // CI runner still clears it; callers must raise their own test timeout to
  // match, since the project default is 120s.
  await expect(title, 'build overlay never reached a terminal state').toHaveText(
    /^Build (complete|failed)$/,
    { timeout: 240_000 },
  );
  return title.innerText();
}
