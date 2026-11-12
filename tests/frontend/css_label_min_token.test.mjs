// W2-11 / UX-006: results table headers and status chips use one minimum label-size token (>= 11px), and the
// text-size control reaches 200%. The stylesheet is read as data: each named rule must take the token.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const css = fs.readFileSync(new URL("../../frontend/css/dashboard.css", import.meta.url), "utf8");

test("--label-min is declared on :root and is at least 11px", () => {
  const m = css.match(/:root\{[^}]*--label-min:(\d+(?:\.\d+)?)px/);
  assert.ok(m, "--label-min token missing");
  assert.ok(Number(m[1]) >= 11 && Number(m[1]) <= 12, `token is ${m[1]}px`);
});

const MUST_USE_TOKEN = [".impact-headline-label", ".spend-level-pill", ".spend-merch-count", ".spend-bar-header", ".detail-col-group-th small",
  ".closeout-status", ".check-status", ".nav-badge", ".nf-tag", ".recommendation-level"];

test("results headers and status chips take the minimum label token, never a smaller literal", () => {
  for (const sel of MUST_USE_TOKEN) {
    const start = css.indexOf(sel + "{");
    assert.ok(start >= 0, `${sel} rule not found`);
    const body = css.slice(start, css.indexOf("}", start));
    assert.match(body, /font-size:\s*var\(--label-min\)/, `${sel} does not use --label-min`);
  }
});

test("no font-size literal under 11px remains on a rule that also styles a chip or a pill", () => {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const m of bare.matchAll(/([^{}]*(?:pill|chip|badge|status)[^{}]*)\{([^}]*)\}/g)) {
    const small = m[2].match(/font-size:\s*(\d+(?:\.\d+)?)px/);
    if (small) assert.ok(Number(small[1]) >= 11, `${m[1].trim()} uses ${small[1]}px`);
  }
});

test("text size reaches 200%", async () => {
  const src = fs.readFileSync(new URL("../../frontend/js/text_size.js", import.meta.url), "utf8");
  assert.match(src, /TEXT_SIZE_OPTIONS = \[100, 115, 130, 150, 200\]/);
  const html = fs.readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");
  assert.match(html, /<option value="150">150%<\/option><option value="200">200%<\/option>/);
});
