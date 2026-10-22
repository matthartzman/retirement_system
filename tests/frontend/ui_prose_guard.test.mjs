// Contextual Help Panel, Phase 4 guard: explanation lives in the right panel (help_registry.js), so the center
// panel may only carry one-line state or warning messages. Every `section-note` / `small` node that carries
// static prose must be tagged data-kind="state|warn" and fit on one line, so prose cannot creep back.
//
// Scope of the static scan (see also tests/e2e/contextual-help-panel.spec.js for the rendered DOM):
//   - nodes with fewer than 3 words of static text are data fragments ("—", "Help", "0.00%") and are skipped;
//   - nodes whose text interpolates a value (`${...}`) are data readouts, not prose, and only the length rule applies;
//   - <button> and <label> carry control names, not messages, and are skipped.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

export const MAX_LINE_CHARS = 120;
const KINDS = /data-kind=\\?["'](state|warn|\$\{)/;
const SKIP_TAGS = new Set(["button", "label"]);
const TAG = /<(\w+)\b((?:[^<>"'`]|"[^"]*"|'[^']*')*?\bclass=\\?(["'])([^"'\\]*)\\?\3[^>]*)>/g;
const HOLE = "\u0000";

// The node's text: everything up to its closing tag, nested tags stripped, interpolated values and
// string concatenations replaced by HOLE (so a node that shows a value is recognised as a readout).
function nodeText(src, from, tag) {
  const close = src.indexOf(`</${tag}>`, from);
  let raw = src.slice(from, close >= 0 && close - from < 900 ? close : from + 300);
  raw = raw.replace(/\$\{(?:[^{}]|\{[^{}]*\})*\}/g, HOLE).replace(/['"`]\s*\+[\s\S]*?\+\s*['"`]/g, HOLE);
  raw = raw.split(/['"`]\s*[,;)]|\n\s*['"`]/)[0].replace(/<[^>]*>/g, " ");
  return raw;
}

export function scanSource(src, file) {
  const found = [];
  let m;
  TAG.lastIndex = 0;
  while ((m = TAG.exec(src))) {
    const tag = m[1].toLowerCase();
    const classes = m[4].split(/\s+/);
    if (SKIP_TAGS.has(tag) || !(classes.includes("section-note") || classes.includes("small"))) continue;
    const raw = nodeText(src, m.index + m[0].length, tag);
    const dynamic = raw.includes(HOLE);
    const text = raw.replace(/\u0000/g, "").replace(/&[a-z#0-9]+;/gi, " ").replace(/\s+/g, " ").trim();
    const words = (text.match(/[A-Za-z]{2,}/g) || []).length;
    if (words < 3) continue;
    const line = src.slice(0, m.index).split("\n").length;
    const where = `${file}:${line}`;
    if (text.length > MAX_LINE_CHARS) found.push(`${where} is ${text.length} chars (max ${MAX_LINE_CHARS}): "${text.slice(0, 60)}..."`);
    if (!dynamic && !KINDS.test(m[2])) found.push(`${where} lacks data-kind="state|warn": "${text.slice(0, 60)}"`);
  }
  return found;
}

function frontendSources() {
  const files = fs.readdirSync("frontend/js").filter((f) => f.endsWith(".js")).map((f) => `frontend/js/${f}`);
  return files.concat(["frontend/index.html", "frontend/admin.html"]);
}

test("guard catches prose without data-kind and lines over the limit", () => {
  assert.equal(scanSource(`'<div class="section-note">Explains how this works.</div>'`, "x.js").length, 1);
  assert.equal(scanSource(`'<p class="small">Explains how this works.</p>'`, "x.js").length, 1);
  assert.equal(scanSource(`"<p class=\\"small\\">Explains how this works.</p>"`, "x.js").length, 1);
  assert.equal(scanSource(`'<div class="section-note" data-kind="state">No rows yet.</div>'`, "x.js").length, 0);
  assert.equal(scanSource(`'<div class="section-note warn" data-kind="warn">Rebuild first.</div>'`, "x.js").length, 0);
  assert.equal(scanSource(`'<div class="section-note" data-kind="state">${"word ".repeat(30)}</div>'`, "x.js").length, 1);
  // data fragments, readouts and control names are not prose
  assert.equal(scanSource(`'<span class="small">—</span>'`, "x.js").length, 0);
  assert.equal(scanSource("`<span class=\"small\">YTD ${a} · Budget ${b}</span>`", "x.js").length, 0);
  assert.equal(scanSource(`'<label class="small">Start year <input></label>'`, "x.js").length, 0);
});

test("every section-note / small prose node in the frontend is a one-line state or warning", () => {
  const violations = frontendSources().flatMap((f) => scanSource(fs.readFileSync(f, "utf8"), f));
  assert.deepEqual(violations, [], `Move explanation into help_registry.js (class A) or shorten and tag it:\n${violations.join("\n")}`);
});
