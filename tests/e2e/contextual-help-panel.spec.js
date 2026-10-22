// Contextual Help Panel, Phase 4: the right-hand panel is the home for explanation, so the browser-level
// behaviour has to hold, not just the registry data: it opens by default on a pre-build page, follows field
// focus without taking focus, becomes a slide-over sheet at 1000px, and is usable from the keyboard alone.
// (Registry data and wiring are covered by tests/frontend/help_panel_follow_focus.test.mjs.)
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

const panel = (page) => page.locator('#helpPanel');
const helpOpen = (page) => page.evaluate(() => document.body.classList.contains('help-open'));

test('the panel opens by default on a pre-build page and stays closed on a post-build page', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');
  await expect(page.locator('body')).toHaveClass(/help-open/);
  await expect(panel(page)).toBeVisible();
  await expect(panel(page).locator('.help-title')).not.toHaveText('');
  // The page summary comes from the registry record, not from prose in the center panel.
  await expect(page.locator('#mainPane .question, #mainPane .pane-head p')).toHaveCount(0);

  await navigateToStep(page, 'reports_and_review', 'Build & Results');
  await expect(page.locator('body')).not.toHaveClass(/help-open/);
});

test('the panel follows field focus and never takes focus from the field', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');
  const before = await panel(page).innerText();
  const field = page.locator('#mainPane .field input:not([disabled])').first();
  await field.focus();
  await expect.poll(async () => panel(page).innerText()).not.toBe(before);
  await expect(field).toBeFocused();
  // Leaving the field keeps its help until the user changes context, and still does not move focus.
  await page.keyboard.press('Tab');
  await expect(panel(page)).toBeVisible();
  expect(await page.evaluate(() => !!document.activeElement.closest('#helpPanel'))).toBe(false);
});

test('at 1000px the panel is a slide-over sheet opened by the "?" button', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 });
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');
  // Never auto-opens below 1180px: it would cover the page.
  expect(await helpOpen(page)).toBe(false);
  await expect(page.locator('#helpPane')).toHaveCSS('position', 'fixed');

  await page.locator('.page-help-btn').first().click();
  await expect(page.locator('body')).toHaveClass(/help-open/);
  await expect(panel(page)).toBeVisible();
  // The sheet slides in (transform transition), so poll until it has settled inside the viewport.
  await expect(async () => {
    const box = await page.locator('#helpPane').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(1000 + 1);
  }).toPass({ timeout: 3000 });
});

test('keyboard only: "?" opens the sheet, focus stays put, Escape closes it and returns to the "?"', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 800 });
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');
  const help = page.locator('.page-help-btn').first();
  await help.focus();
  await expect(help).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('body')).toHaveClass(/help-open/);
  // Opening the panel does not move focus into it.
  await expect(help).toBeFocused();
  await expect(panel(page)).toBeVisible();

  await page.keyboard.press('Escape');
  await expect(page.locator('body')).not.toHaveClass(/help-open/);
  await expect(help).toBeFocused();
});

test('rendered section-note / small nodes are one-line state or warning messages', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await openCurrentPlan(page);
  const stray = [];
  for (const [id, title] of [
    ['household_people', 'Household & People'],
    ['income_work', 'Work Income'],
    ['spending_core', 'Spending'],
    ['holdings', 'Investment Holdings'],
    ['estate', 'Estate'],
  ]) {
    await navigateToStep(page, id, new RegExp(title));
    const found = await page.evaluate(() =>
      Array.from(document.querySelectorAll('#mainPane .section-note, #mainPane .small'))
        // Prose only: skip control names, table cells (plan data and readouts), widgets that hold a control and figures such as "YTD $0 · Budget $5".
        .filter((n) => !n.closest('button, label, td, th') && !n.querySelector('input, select, button') && !/[\d$%]/.test(n.textContent || ''))
        .filter((n) => (n.textContent || '').trim().split(/\s+/).length >= 3)
        .filter((n) => !/^(state|warn)$/.test(n.getAttribute('data-kind') || '') || n.textContent.trim().length > 140)
        .map((n) => n.textContent.trim().slice(0, 70)),
    );
    stray.push(...found.map((t) => `${id}: ${t}`));
  }
  expect(stray, 'prose in the centre panel belongs in help_registry.js').toEqual([]);
});
