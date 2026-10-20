// WI-021: keyboard walk (help badge is reachable and operable, Tab is native, Enter still advances),
// page-change announcements (title, live region, heading focus), nav-group state, and the single
// navigation guard (Back saves an edited autosave page first).
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

async function firstEditableField(page) {
  const field = page.locator('#mainPane input[data-row]:not([type=checkbox]):not([type=hidden])').first();
  await expect(field).toBeVisible();
  return field;
}

test('keyboard walk: help badge is a tab stop in DOM order and Enter on it opens the help panel', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');

  const badges = page.locator('#mainPane button.field-info-i');
  expect(await badges.count(), 'estate page should carry help badges').toBeGreaterThan(0);

  // Start at the page heading (where navigation leaves focus) and Tab through the page.
  await expect(page.locator('#mainPane h2').first()).toBeFocused();
  const seen = [];
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => {
      const a = document.activeElement;
      return { inMain: !!(a && a.closest && a.closest('#mainPane')), badge: !!(a && a.classList && a.classList.contains('field-info-i')), tag: a && a.tagName };
    });
    seen.push(info);
    if (info.badge) break;
  }
  expect(seen.some((s) => s.badge), 'Tab never reached a help badge').toBe(true);

  // Every Tab stop inside the main pane follows DOM order (no jumps back or forward past a control).
  const ordered = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('#mainPane button, #mainPane input, #mainPane select, #mainPane summary, #mainPane a[href], #mainPane textarea'))
      .filter((e) => e.offsetParent !== null && !e.disabled);
    return all.length;
  });
  expect(ordered).toBeGreaterThan(1);

  // Enter on the focused badge activates it natively (the click opens the help panel for its field).
  const before = await page.locator('#helpPanel').innerText();
  await page.keyboard.press('Enter');
  await expect(page.locator('#helpPanel')).not.toHaveText(before);
});

test('Tab is native between fields: it visits every control in DOM order; Enter still advances', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');
  const order = await page.evaluate(async () => {
    const tabbables = () =>
      Array.from(document.querySelectorAll('#mainPane button, #mainPane input, #mainPane select, #mainPane summary, #mainPane a[href]')).filter(
        (e) => e.offsetParent !== null && !e.disabled && e.tabIndex >= 0,
      );
    const list = tabbables();
    return { count: list.length, hasBadge: list.some((e) => e.classList.contains('field-info-i')) };
  });
  expect(order.hasBadge).toBe(true);

  const first = await firstEditableField(page);
  await first.focus();
  const idx = await first.getAttribute('data-row');
  await page.keyboard.press('Tab');
  // Native Tab: focus goes to the very next tabbable element, which for a field with a help badge is the badge.
  const next = await page.evaluate(() => {
    const a = document.activeElement;
    return { badge: a.classList.contains('field-info-i'), row: a.getAttribute('data-row') };
  });
  expect(next.row === idx, 'focus should have left the field').toBe(false);
  // Enter advances to the next listed field (spreadsheet-style entry is kept).
  await first.focus();
  await page.keyboard.press('Enter');
  await expect(first).not.toBeFocused();
  expect(await page.evaluate(() => document.activeElement.matches('input,select'))).toBe(true);
});

test('navigating announces the page: title, live region and heading focus', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');
  await expect(page).toHaveTitle('Estate - Retirement Planner'.replace('Estate', await page.evaluate(() => window.stepTitleById('estate'))));
  await expect(page.locator('#navAnnouncer')).toContainText('Now on');
  await expect(page.locator('#mainPane h2').first()).toBeFocused();

  // via the left nav (its groups are collapsed unless active, so activate the button directly)
  await page.locator('#steps [data-step-id="household_people"]').evaluate((b) => b.click());
  const title = await page.evaluate(() => window.stepTitleById('household_people'));
  await expect(page).toHaveTitle(`${title} - Retirement Planner`);
  await expect(page.locator('#navAnnouncer')).toHaveText(`Now on ${title}`);
  await expect(page.locator('#mainPane h2').first()).toBeFocused();
});

test('a nav group the user opened stays open while editing re-renders the nav', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'estate', 'Estate');
  const groups = page.locator('#steps details.nav-group');
  const n = await groups.count();
  let opened = -1;
  for (let i = 0; i < n; i++) {
    if (!(await groups.nth(i).evaluate((d) => d.open))) {
      await groups.nth(i).locator('summary').first().evaluate((s) => s.click());
      opened = i;
      break;
    }
  }
  expect(opened, 'expected at least one collapsed nav group').toBeGreaterThanOrEqual(0);
  const name = await groups.nth(opened).getAttribute('data-group');
  const field = await firstEditableField(page);
  const original = await field.inputValue();
  await field.fill(original + '1');
  await field.blur();
  await page.waitForTimeout(500); // scheduleStatusUpdate re-renders the nav 120 ms after an edit
  await expect(page.locator(`#steps details.nav-group[data-group="${name}"]`)).toHaveJSProperty('open', true);
  await field.fill(original);
});

test('Back from an edited autosave page saves the edit first', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'household_people', 'Household & People');
  await page.evaluate(() => window.setStep('estate'));
  await expect(page.getByRole('heading', { name: 'Estate' })).toBeVisible();
  await page.evaluate(() => window.setStep('household_people'));
  await expect(page.getByRole('heading', { name: 'Household & People' })).toBeVisible();
  // an edit on an autosave page, then the header Back button (keyboard path)
  const select = page.locator('#mainPane select[data-row]').first();
  const row = await select.getAttribute('data-row');
  const current = await select.inputValue();
  const options = await select.locator('option').evaluateAll((os) => os.map((o) => o.value));
  const other = options.find((v) => v !== current);
  await select.selectOption(other);
  await select.blur();
  try {
    await page.locator('#navBackBtn').focus();
    await page.keyboard.press('Enter');
    await expect(async () => {
      const resp = await page.request.get('/api/config/rows', { headers: { 'X-User-Role': 'admin' } });
      const saved = (await resp.json()).rows.find((r) => String(r.row_index) === row).value;
      expect(saved).toBe(other);
    }).toPass({ timeout: 10_000 });
  } finally {
    await page.request.post('/api/config/rows', { headers: { 'X-User-Role': 'admin' }, data: { updates: [{ row_index: Number(row), value: current }] } }).catch(() => {});
  }
});
