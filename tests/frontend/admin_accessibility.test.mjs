// UX-006 / WI-013: Admin / Control Center controls have accessible names and
// #msg is a live region. Runs the real admin.js source against a minimal stub.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend");
const src = fs.readFileSync(path.join(ROOT, "js", "admin.js"), "utf8");
const html = fs.readFileSync(path.join(ROOT, "admin.html"), "utf8");

const noop = () => {};
const el = () => ({ style: {}, classList: { add: noop, remove: noop, toggle: noop, contains: () => false }, setAttribute: noop, addEventListener: noop, querySelectorAll: () => [], querySelector: () => null });
const sandbox = {
  document: { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: noop, createElement: el, body: el() },
  localStorage: { getItem: () => null, setItem: noop }, fetch: () => Promise.reject(new Error("no")),
  setTimeout: noop, setInterval: noop, console,
};
sandbox.addEventListener = noop;
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);
const run = (c) => vm.runInContext(c, sandbox);

const controls = (h) => [...h.matchAll(/<(input|select|textarea)\b([^>]*)>/g)].map((m) => m[2]);
const hasName = (a) => /\saria-label="[^"]+"/.test(" " + a) || /\saria-labelledby="[^"]+"/.test(" " + a);

test("grid inputs and selects carry an aria-label with column and row", () => {
  const rows = [["Symbol", "Weight"], ["VTI", "50"], ["BND", "50"]];
  const out = run(`buildDataGrid(${JSON.stringify(rows)}, "generic")`);
  const ctl = controls(out).filter((a) => a.includes("grid-input"));
  assert.equal(ctl.length, 4);
  for (const a of ctl) assert.ok(hasName(a), a);
  assert.match(out, /aria-label="Symbol row 1"/);
  assert.match(out, /aria-label="Weight row 2"/);
});

test("every control literal in admin.js is named by aria-label or label-for id", () => {
  for (const m of src.matchAll(/<(input|select|textarea)\b[^>]*>/g)) {
    const a = m[0];
    if (/type="checkbox"/.test(a)) continue;
    assert.ok(hasName(a) || /id="\$\{settingControlId/.test(a), a);
  }
});

test("#msg is a live region and errors switch to role=alert", () => {
  assert.match(html, /id="msg"[^>]*role="status"/);
  assert.match(html, /id="msg"[^>]*aria-live="polite"/);
  const attrs = {};
  const m = { textContent: "", classList: { toggle: noop, contains: () => false }, setAttribute: (k, v) => (attrs[k] = v) };
  sandbox.document.getElementById = (id) => (id === "msg" ? m : null);
  run(`msg("Pricing tester error: x", true)`);
  assert.equal(attrs.role, "alert");
  assert.equal(attrs["aria-live"], "assertive");
  run(`msg("ok")`);
  assert.equal(attrs.role, "status");
});

test("unsaved-change announcement is not repeated per keystroke; no native confirm", () => {
  let writes = 0;
  let text = "";
  const m = { get textContent() { return text; }, set textContent(v) { writes++; text = v; }, classList: { toggle: noop, contains: () => false }, setAttribute: noop };
  sandbox.document.getElementById = () => m;
  for (let i = 0; i < 5; i++) run(`announceUnsaved("System Config")`);
  assert.equal(writes, 1);
  assert.ok(!/\bconfirm\(/.test(src.replace(/adminConfirm/g, "")));
});

test("DOC-007 stale 'single local Plan Data folder' text is gone", () => {
  assert.ok(!src.includes("single local Plan Data folder"));
});
