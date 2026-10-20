// WI-014 (system review 2026-10-19; UX-005, UX-013 confirmed by rendering
// before the fix): the 3-column grid forced a 700px content minimum, so the
// page scrolled horizontally at 1280px with help open and at 130% text size;
// and a persistent message was a fixed pill over the header Save button.
import { test, expect } from './fixtures.js';
import { openCurrentPlan } from './helpers.js';

const MATRIX = [[1460, 800], [1280, 800], [1100, 800], [800, 800], [390, 800]];

for (const [width, height] of MATRIX) {
  for (const size of ['100', '130']) {
    test(`no horizontal scroll at ${width}px, text ${size}%, help open`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await openCurrentPlan(page);
      await page.evaluate((v) => {
        const s = document.getElementById('textSizeSelect');
        s.value = v;
        s.dispatchEvent(new Event('change', { bubbles: true }));
        document.body.classList.add('help-open');
      }, size);
      const { sw, cw } = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
      }));
      expect(sw).toBeLessThanOrEqual(cw);
    });

    test(`persistent message does not cover Save at ${width}px, text ${size}%`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await openCurrentPlan(page);
      await page.evaluate((v) => {
        const s = document.getElementById('textSizeSelect');
        s.value = v;
        s.dispatchEvent(new Event('change', { bubbles: true }));
        const e = document.getElementById('actionMessage');
        e.className = 'message bad persistent';
        e.innerHTML = '<span class="msg-text">Persistent error that must not cover header actions</span><button class="msg-dismiss">x</button>';
      }, size);
      await expect(page.locator('#actionMessage')).toHaveCSS('position', 'static');
      const overlap = await page.evaluate(() => {
        const m = document.getElementById('actionMessage').getBoundingClientRect();
        const s = document.getElementById('saveChangesBtn').getBoundingClientRect();
        return !(m.right <= s.left || m.left >= s.right || m.bottom <= s.top || m.top >= s.bottom);
      });
      expect(overlap).toBe(false);
    });
  }
}
