// The Category/Merchant/Account cells in the Transactions table are
// <input list=...> fields. A browser only offers datalist options matching the
// text already in the box, so a filled cell used to show just its own value.
// The cell now clears on focus (so every existing value is offered) and
// restores its value on blur when nothing was chosen.
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('transaction Category cell offers every existing value and restores its text on blur', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'actual_spending', 'Actual Spending');
  await page.getByRole('tab', { name: 'This year' }).click();

  await page.evaluate(() => {
    window.addYtdTxn();
    window.updateYtdTxn(0, 'Category', 'E2E_List_Category_A');
    window.addYtdTxn();
    window.updateYtdTxn(0, 'Category', 'E2E_List_Category_B');
    window.renderMain();
  });

  const cell = page.locator('input.ytd-existing-select[list="ytd-existing-category"]').first();
  await expect(cell).toHaveValue('E2E_List_Category_B');

  await cell.focus();
  await expect(cell, 'focusing the cell should clear it so the whole list is offered').toHaveValue('');
  const options = await page.evaluate(() => {
    const id = 'ytd-existing-category';
    return [...document.querySelectorAll(`datalist#${id} option`)].map((o) => o.value);
  });
  expect(options).toEqual(expect.arrayContaining(['E2E_List_Category_A', 'E2E_List_Category_B']));

  await cell.evaluate((el) => el.blur());
  await expect(cell, 'leaving the cell without choosing must restore its value').toHaveValue('E2E_List_Category_B');
});
