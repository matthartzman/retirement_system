// WI-015 / ARC-007: navigation baseline across ALL guided steps.
//
// Records, for every [data-step-id] in the nav, the step id, the first heading
// rendered in #mainPane, and whether it rendered meaningful content without
// console/page errors. The result is compared with the committed baseline
// tests/e2e/baselines/wi015-navigation-baseline.json so WI-035 (replacing the
// renderMain/showStepHelp wrapper chain with a hook registry) can show that
// navigation is unchanged before and after.
//
// Data source: the frozen sample plan that tools/e2e_server.py stages (same as
// nav-integrity.spec.js). Re-record intentionally with:
//   WI015_RECORD=1 npx playwright test tests/e2e/wi015-navigation-baseline.spec.js
import { test, expect } from './fixtures.js';
import { openCurrentPlan } from './helpers.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BASELINE = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  'baselines',
  'wi015-navigation-baseline.json',
);

test('navigation baseline: every step renders the same heading and no errors', async ({ page }) => {
  test.setTimeout(240_000);
  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !msg.text().includes('Failed to load resource')) errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(String(err)));

  await openCurrentPlan(page);
  const stepIds = await page.locator('[data-step-id]').evaluateAll((els) =>
    [...new Set(els.map((el) => el.getAttribute('data-step-id')))],
  );
  expect(stepIds.length).toBeGreaterThan(10);

  const steps = [];
  for (const stepId of stepIds) {
    const before = errors.length;
    await page.evaluate((id) => window.setStep(id), stepId);
    const pane = page.locator('#mainPane');
    await expect(pane).not.toBeEmpty();
    // The pane re-renders asynchronously after setStep; reading the heading at once can return the
    // previous step's heading. Take it once it is stable across two reads.
    const readHeading = () =>
      pane
        .locator('h1, h2, h3')
        .first()
        .innerText()
        .then((t) => t.trim().replace(/\s+/g, ' '))
        .catch(() => null);
    let heading = await readHeading();
    for (let i = 0; i < 20; i++) {
      await page.waitForTimeout(150);
      const again = await readHeading();
      if (again === heading) break;
      heading = again;
    }
    const text = await pane.innerText();
    steps.push({
      stepId,
      heading,
      hasContent: text.length > 20,
      errors: errors.length - before,
    });
  }

  const actual = { stepCount: steps.length, steps };
  if (process.env.WI015_RECORD === '1') {
    fs.mkdirSync(path.dirname(BASELINE), { recursive: true });
    fs.writeFileSync(BASELINE, JSON.stringify(actual, null, 2) + '\n');
  }
  expect(errors, `console errors: ${errors.join(' | ')}`).toEqual([]);
  const expected = JSON.parse(fs.readFileSync(BASELINE, 'utf8'));
  expect(actual).toEqual(expected);
});
