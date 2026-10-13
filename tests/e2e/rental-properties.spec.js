// WP12.6: the Rental Properties page in a real browser. The nav entry appears only while the
// feature is on (or properties are kept: then the page shows its off state), a property can be
// added, edited across the tabs, duplicated and removed, "Show advanced" reveals the Expert
// fields (active participation is a Standard field), Convert my home asks for rent only, and a
// phone-width window shows cards instead of the table. Every route is the real one
// (/api/rental/*); the plan is restored afterwards because a worker's server is shared.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

const H = { 'X-User-Role': 'admin' };
const KEY = 'rental_property_income';

async function post(page, path, data) {
  const resp = await page.request.post(path, { headers: H, data });
  expect(resp.ok(), `${path} -> ${resp.status()} ${await resp.text()}`).toBeTruthy();
  return resp.json();
}

async function wipeRentals(page) {
  const list = await (await page.request.get('/api/rental/properties', { headers: H })).json();
  for (const p of list.properties) await post(page, '/api/rental/property/delete', { name: p.name });
}

const navEntry = (page) => page.locator('[data-step-id="rental_properties"]');

test('rental properties page: add, edit, advanced fields, convert, duplicate, remove, off state, phone cards', async ({ page }) => {
  test.setTimeout(240_000);
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('Failed to load resource')) errors.push(m.text());
  });

  await openCurrentPlan(page);
  try {
    // Off with nothing entered: the page is not in the nav.
    await expect(navEntry(page)).toHaveCount(0);

    // The Advanced tier switches the feature on; the nav entry appears under Investments & Property.
    await post(page, '/api/plan/tier', { tier: 'advanced' });
    await openCurrentPlan(page);
    await expect(navEntry(page)).toHaveCount(1);
    await expect(navEntry(page).locator('xpath=ancestor::details//summary')).toContainText('Investments & Property');
    await navigateToStep(page, 'rental_properties', 'Rental Properties');
    const pane = page.locator('#mainPane');
    await expect(pane).toContainText('No rental properties yet');

    // Add a property: Standard fields only (Show advanced is off on an Advanced plan).
    await page.getByRole('button', { name: '+ Add property' }).click();
    await expect(page.getByRole('button', { name: 'Save property' })).toBeVisible();
    await page.getByLabel('Name', { exact: true }).fill('Maple duplex');
    await page.getByLabel('Purchase price').fill('350000');
    await page.getByLabel('Purchase date').fill('2018-06');
    await page.getByLabel('Current value').fill('450000');
    await expect(page.locator('#rpDirtyBadge')).toBeVisible();
    await page.getByRole('tab', { name: 'Income' }).click();
    await page.getByLabel('Monthly rent').fill('2850');
    await page.getByLabel('Vacancy').fill('5');
    await page.getByRole('tab', { name: 'Expenses' }).click();
    await expect(page.getByLabel('Property tax growth')).toHaveCount(0); // Expert field
    await page.getByLabel('Property tax (per year)').fill('4900');

    // Tax tab: active participation is Standard; the rest is Expert behind Show advanced.
    await page.getByRole('tab', { name: 'Tax' }).click();
    await expect(page.getByLabel('Active participation')).toHaveValue('yes');
    await expect(page.getByLabel('Placed in service')).toHaveCount(0);
    await page.getByLabel('Show advanced').check();
    await expect(page.getByLabel('Placed in service')).toBeVisible();
    await expect(pane.locator('.badge.exp').first()).toBeVisible();
    await page.getByRole('button', { name: '+ Add improvement' }).click();
    await page.getByLabel('Improvement 1 year').fill('2024');
    await page.getByLabel('Improvement 1 amount').fill('14000');
    await page.getByRole('tab', { name: 'Overrides' }).click();
    await expect(pane).toContainText('Per-year overrides');
    await page.getByLabel('Show advanced').uncheck();
    await expect(pane).toContainText('Expert feature');

    // A bad save shows the parser's message and keeps the form.
    await page.getByRole('tab', { name: 'Basics' }).click();
    await page.getByLabel('Purchase price').fill('');
    await page.getByRole('button', { name: 'Save property' }).click();
    await expect(page.locator('#actionMessage')).toContainText('purchase_price is required');
    await page.getByLabel('Purchase price').fill('350000');
    await page.getByRole('button', { name: 'Save property' }).click();
    await expect(page.locator('#actionMessage')).toContainText('Saved Maple duplex.');

    // Back to the list: summary strip, table row, saved values.
    await page.getByRole('button', { name: /Back to list/ }).click();
    await expect(pane.locator('.rp-strip .review-card')).toHaveCount(4);
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(1);
    await expect(pane.locator('.rp-table')).toContainText('Maple duplex');
    await expect(pane.locator('.rp-table')).toContainText('$34,200/yr');
    await expect(pane).toContainText('Estimate from your property entries');
    let saved = await (await page.request.get('/api/rental/property?name=Maple duplex', { headers: H })).json();
    expect(saved.property).toMatchObject({ purchase_price: 350000, monthly_rent: 2850, vacancy_rate: 0.05, property_tax: 4900 });
    expect(saved.property.improvements).toEqual([{ year: 2024, amount: 14000 }]);

    // Duplicate and remove (with the confirm dialog).
    await pane.getByRole('button', { name: 'Duplicate' }).click();
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(2);
    await expect(pane.locator('.rp-table')).toContainText('Maple duplex (copy)');
    await pane.locator('.rp-table tbody tr', { hasText: 'Maple duplex (copy)' }).getByRole('button', { name: 'Remove' }).click();
    await page.getByRole('button', { name: 'Remove', exact: true }).last().click();
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(1);

    // Convert my home: pre-filled from the plan's home, asks for rent only (no suggestion).
    await page.getByRole('button', { name: 'Convert my home to a rental' }).click();
    const rent = page.getByLabel('Monthly rent');
    await expect(rent).toHaveValue('');
    await expect(page.getByLabel('Conversion year')).not.toHaveValue('');
    await expect(page.getByLabel('Value at conversion')).not.toHaveValue('');
    await expect(pane).toContainText('Move to Schedule E');
    await page.getByRole('button', { name: 'Create converted home' }).click();
    await expect(page.locator('#actionMessage')).toContainText('Enter the monthly rent');
    await rent.fill('3200');
    await page.getByRole('button', { name: 'Create converted home' }).click();
    await expect(pane.getByRole('heading', { name: 'Primary residence (converted home)' })).toBeVisible();
    await expect(pane).toContainText('Converted home only');
    await page.getByRole('button', { name: /Back to list/ }).click();
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(2);
    await expect(page.getByRole('button', { name: 'Convert my home to a rental' })).toBeDisabled(); // one home only

    // Phone width: cards replace the table.
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(pane.locator('.rp-table')).toBeHidden();
    await expect(pane.locator('.rp-card')).toHaveCount(2);
    await page.setViewportSize({ width: 1280, height: 900 });

    // Off with data kept: the entry stays, the page shows "Off . 2 rows entered" and a preview.
    await post(page, '/api/plan/feature', { key: KEY, on: false });
    await openCurrentPlan(page);
    await expect(navEntry(page)).toHaveCount(1);
    await navigateToStep(page, 'rental_properties', 'Rental Properties');
    await expect(pane).toContainText('Off · 2 rows entered');
    await expect(pane.getByRole('button', { name: '+ Add property' })).toHaveCount(0);
    await pane.getByRole('button', { name: 'Preview what it would add' }).click();
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(2);
    await expect(pane.locator('.rp-table').getByRole('button', { name: 'Open' })).toHaveCount(0); // read only
    await pane.getByRole('button', { name: 'Turn on Rental Properties' }).click();
    await expect(pane.getByRole('button', { name: '+ Add property' })).toBeVisible();
    await expect(pane.locator('.rp-table tbody tr')).toHaveCount(2);

    expect(errors, `JS errors: ${errors.join(' | ')}`).toEqual([]);
  } finally {
    await wipeRentals(page).catch(() => {});
    await post(page, '/api/plan/tier', { tier: 'expert' }).catch(() => {});
    await post(page, '/api/plan/feature', { key: KEY, on: false }).catch(() => {});
  }
});
