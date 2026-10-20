// WI-014 (system review 2026-10-19, UX-007): the shared focus token and the
// switch off-state track must meet WCAG 1.4.11 non-text contrast (>= 3:1).
// Token values are read from :root in dashboard.css, so editing a token to a
// failing colour fails here.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CSS = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "css", "dashboard.css"),
  "utf8",
);

function token(name) {
  const m = CSS.match(new RegExp("--" + name + ":\\s*(#[0-9a-fA-F]{3,6})\\b"));
  assert.ok(m, "token --" + name + " not found");
  let h = m[1].slice(1);
  if (h.length === 3) h = h.replace(/./g, (c) => c + c);
  return h;
}
function lum(hex) {
  const c = [0, 2, 4].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const HEADER_BG = "1c2f4a"; // header{background:#1c2f4a}
const pairs = [
  ["focus", "surface", "focus ring on white card"],
  ["focus", "bg", "focus ring on page background"],
  ["focus", "soft", "focus ring on soft card"],
  ["track-off", "surface", "switch off-state track on white"],
  ["accent", "surface", "switch on-state track (accent) on white"],
  ["ok", "surface", "yes/no toggle on-state track on white"],
];

for (const [fg, bg, label] of pairs) {
  test(label + " >= 3:1", () => {
    const r = ratio(token(fg), token(bg));
    assert.ok(r >= 3, label + ": " + r.toFixed(2));
  });
}

test("focus ring on the dark header >= 3:1", () => {
  const r = ratio(token("focus-dark"), HEADER_BG);
  assert.ok(r >= 3, r.toFixed(2));
});

test("the old pale ring would have failed (guards the calculator)", () => {
  assert.ok(ratio("bfdbfe", "ffffff") < 3);
});
