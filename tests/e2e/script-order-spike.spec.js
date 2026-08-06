// Empirical spike for docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md
// Task 2: confirms real browser behavior for classic-vs-module script
// execution order BEFORE relying on any assumption about it when
// frontend/js/dashboard.js is converted to type="module" (Task 4/5).
import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test('classic scripts run before module scripts, both before DOMContentLoaded', async ({ page }) => {
  const fixture = path.resolve(__dirname, '../../tools/js_codemod/fixtures/script_order_spike.html');
  await page.goto('file://' + fixture);
  const log = await page.locator('#log').textContent();
  const order = log.split(',');

  expect(order.indexOf('classic-early')).toBeLessThan(order.indexOf('classic-late'));
  expect(order.indexOf('classic-late')).toBeLessThan(order.indexOf('module-before-tag'));
  expect(order.indexOf('module-before-tag')).toBeLessThan(order.indexOf('module-after-tag'));
  expect(order.indexOf('module-after-tag')).toBeLessThan(order.indexOf('dom-content-loaded'));
});
