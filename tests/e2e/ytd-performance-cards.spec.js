// This Year Performance: every chart line is labeled, and the shaded note boxes
// show their full text (nothing clipped with an ellipsis).
import { test, expect } from './fixtures.js';
import { openCurrentPlan, navigateToStep } from './helpers.js';

test('YTD charts are labeled and the breakdown notes are not truncated', async ({ page }) => {
  await openCurrentPlan(page);
  await navigateToStep(page, 'actual_spending', 'Actual Spending');
  await page.getByRole('tab', { name: 'This year' }).click();

  // Import a few current-year transactions so the performance cards render.
  await page.evaluate(async () => {
    const y = new Date().getFullYear();
    const csv = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n' +
      `${y}-01-02,Employer,Paychecks,Checking,PAYROLL,,5000,,Household\n` +
      `${y}-01-03,Grocer,Groceries,Checking,GROCER,,-150,,Household\n` +
      `${y}-01-04,IRS,Income Tax,Checking,IRS,,-900,,Household\n`;
    await window.api('/api/ytd/transactions/upload', { method: 'POST', body: JSON.stringify({ mode: 'replace', csv_text: csv }) });
    await window.loadYtdStatus();
    window.renderMain();
  });
  // The cards live on the Analysis tab once a spending taxonomy exists; render
  // the same summary markup directly so this test needs no budget setup.
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.id = 'e2eYtdSummary';
    host.style.cssText = 'width:1000px;background:#fff';
    host.innerHTML = window.renderYtdSummary();
    document.querySelector('#mainPane').prepend(host);
  });

  await expect(page.locator('#e2eYtdSummary .ytd-window-line')).toBeVisible();
  const charts = page.locator('#e2eYtdSummary .ytd-metric .ytd-chart');
  await expect(charts).toHaveCount(3);
  for (let i = 0; i < 3; i++) {
    await expect(charts.nth(i).locator('text', { hasText: 'Actual' }).first()).toBeVisible();
  }
  await expect(charts.first().locator('text', { hasText: 'Expected YTD' })).toHaveCount(1);

  const notes = page.locator('#e2eYtdSummary .ytd-breakdown');
  await expect(notes).toHaveCount(3);
  for (let i = 0; i < 3; i++) {
    const clipped = await notes.nth(i).evaluate((el) => el.scrollWidth > el.clientWidth + 1 || getComputedStyle(el).textOverflow === 'ellipsis');
    expect(clipped, `breakdown note ${i} is clipped`).toBe(false);
  }
});
