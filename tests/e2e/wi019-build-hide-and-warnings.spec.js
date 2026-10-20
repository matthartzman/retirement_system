// WI-019 / UX-002 / ARC-003: the build overlay offers Hide (not a fake Cancel), a hidden build does
// not pull the user to another page when it finishes, and swallowed-step warnings (WI-007's
// config_contract_warnings, carried as `warnings` on the build result) are visible.
// The build API is intercepted (like build-failure.spec.js) so this does not run a real ~100s build.
import { test, expect } from './fixtures.js';
import { openCurrentPlan } from './helpers.js';

const JOB = 'e2e-wi019-job';
const WARNINGS = ['PlanResult contract build failed: synthetic', 'ReportSpec contract build failed: synthetic'];

async function mockBuild(page) {
  const gate = { release: false };
  await page.route('**/api/build/start', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, job_id: JOB, progress: 0, phase: 'Preparing build' }) }),
  );
  await page.route(`**/api/build/progress/${JOB}`, (route) => {
    const job = gate.release
      ? {
          job_id: JOB,
          status: 'done',
          progress: 100,
          phase: 'Build complete',
          detail: 'QC: 1 / 1 PASS',
          result: { success: true, qc_result: 'QC: 1 / 1 PASS', kpi: { qc_result: 'QC: 1 / 1 PASS', lcv: 1000000 }, warnings: WARNINGS, admin_changes: [] },
        }
      : { job_id: JOB, status: 'running', progress: 20, phase: 'Running projection', detail: 'Working...' };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, job }) });
  });
  return gate;
}

async function startBuild(page) {
  await page.evaluate(() => window.setStep('reports_and_review'));
  await page.evaluate(() => {
    window.liabilitiesChanged = true; // enable Build Reports exactly as a user edit would
    window.renderMain();
  });
  await page.getByRole('button', { name: 'Build Reports' }).first().click();
  const proceed = page.getByRole('button', { name: 'Continue Build' });
  await proceed.click({ timeout: 8_000 }).catch(() => {});
  await expect(page.locator('#buildOverlay')).toHaveClass(/active/, { timeout: 15_000 });
}

test('hiding a running build: honest button, no forced navigation, warnings shown', async ({ page }) => {
  const gate = await mockBuild(page);
  await openCurrentPlan(page);
  await startBuild(page);

  await expect(page.getByRole('button', { name: /^Cancel/ })).toHaveCount(0);
  await page.getByRole('button', { name: /Hide/ }).first().click();
  await expect(page.locator('#buildOverlay')).not.toHaveClass(/active/);
  await expect(page.locator('#buildRunningChip')).toBeVisible();
  await expect(page.locator('#actionMessage')).not.toContainText(/cancel/i);

  // The user moves on to a data-entry page while the build is still running.
  await page.evaluate(() => window.setStep('household_people'));
  await expect(page.getByRole('heading', { name: 'Household & People' })).toBeVisible();
  gate.release = true;

  const msg = page.locator('#actionMessage');
  await expect(msg).toContainText('finished with 2 warnings', { timeout: 20_000 });
  await expect(msg).toContainText('PlanResult contract build failed: synthetic');
  await expect(page.locator('#buildRunningChip')).toBeHidden();
  // Still on the page the user moved to: no auto-navigation to Impact & Build History.
  await expect(page.getByRole('heading', { name: 'Household & People' })).toBeVisible();
  expect(await page.evaluate(() => window.activeStep)).toBe('household_people');

  // The action opens the results (with the warnings banner) on request.
  // (keyboard activation: at this viewport the help drawer overlaps the toast's right edge)
  const viewResults = page.getByRole('button', { name: 'View Impact & Build History' });
  await viewResults.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.build-warnings')).toContainText('ReportSpec contract build failed: synthetic');
});

test('not hiding: the finished build opens Impact & Build History with the warnings banner', async ({ page }) => {
  const gate = await mockBuild(page);
  gate.release = true;
  await openCurrentPlan(page);
  await startBuild(page).catch(() => {});
  await expect(page.locator('.build-warnings')).toContainText('PlanResult contract build failed: synthetic', { timeout: 20_000 });
  await expect(page.locator('#actionMessage')).toContainText('2 warnings');
});
