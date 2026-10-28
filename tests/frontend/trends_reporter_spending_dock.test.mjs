// Spending dock: Pin/Unpin must not close the panels, and the wiring lives in spending_dock.js.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isOutsideClick, initSpendingDock } from "../../financial_trends_reporter/frontend/spending_dock.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(HERE, "..", "..", "financial_trends_reporter", "frontend", "index.html"), "utf8");
const el = (connected, inside) => ({ isConnected: connected, closest: () => (inside ? {} : null) });

test("a click on a button removed by re-render is not an outside click", () => {
  assert.equal(isOutsideClick(el(false, false)), false);
});
test("a click inside the chart or dock is not outside", () => { assert.equal(isOutsideClick(el(true, true)), false); });
test("a click elsewhere is outside", () => { assert.equal(isOutsideClick(el(true, false)), true); });
test("index.html wires the dock from the module", () => {
  assert.match(html, /import \{[^}]*initSpendingDock[^}]*\} from "\.\/spending_dock\.js"/);
  assert.match(html, /initSpendingDock\(\{ doc: document, win: window, getModel: \(\) => categoryModel, getRange: currentRange \}\)/);
  assert.ok(!html.includes("function pinRow("));   // moved, not duplicated
});

test("index.html still defines the popup helpers the rollover and account popups use", () => {
  // MARGIN and fitVertically stay in index.html: showRollover and the account popup call them.
  assert.match(html, /const MARGIN = \d+;/);
  assert.match(html, /function fitVertically\(el, desiredTop\)/);
});

// --- Transactions panel (third level) ---------------------------------------------------------
import { transactionsUrl, transactionsPanelHtml, detailPopupHtml } from "../../financial_trends_reporter/frontend/charts.js";

test("transactionsUrl encodes every part", () => {
  assert.equal(transactionsUrl({ from: "2026-01-01", to: "2026-10-27" }, { type: "Core", group: "Food & Drink", category: "Groceries", merchant: "Trader Joe's" }),
    "/api/spending/transactions?from=2026-01-01&to=2026-10-27&type=Core&group=Food%20%26%20Drink&category=Groceries&merchant=Trader%20Joe's");
});
test("transactions panel rows, notes and total", () => {
  const out = transactionsPanelHtml("Costco", { transactions: [{ date: "2026-10-02", account: "Visa", merchant: "Costco", amount: 1400, notes: "TV" }], total: 1400 });
  assert.match(out, /2026-10-02/); assert.match(out, /Visa/); assert.match(out, /title="TV"/); assert.match(out, /Total[\s\S]*\$1,400/);
});
test("transactions panel escapes imported text", () => {
  const out = transactionsPanelHtml("<b>", { transactions: [{ date: "d", account: "<i>", merchant: "A&B", amount: 1, notes: '"><script>' }], total: 1 });
  assert.ok(!out.includes("<script>") && !out.includes("<i>") && !out.includes("<b>"));
  assert.match(out, /A&amp;B/);
});
test("empty panel text", () => { assert.match(transactionsPanelHtml("X", { transactions: [], total: 0 }), /No transactions found\./); });
test("merchant rows carry an index only when asked", () => {
  assert.match(detailPopupHtml("t", [["A", 1]], undefined, { indexAttr: "merchant" }), /data-merchant="0"/);
  assert.ok(!detailPopupHtml("t", [["A", 1]]).includes("data-merchant"));
});
test("index.html has the third panel and its empty text", () => {
  assert.match(html, /id="detailPopup3"/); assert.match(html, /Hover a merchant for its transactions\./);
  assert.match(html, /#detailPopup, #detailPopup2, #detailPopup3 \{ flex: 1 1 0;/);
  assert.match(html, /@media \(max-width: 700px\)[^\n]*#detailPopup3/);
});

// Minimal fake DOM: elements hold listeners; dispatching a row event passes {target} with closest/dataset.
function makeEl() {
  const l = {};
  return { innerHTML: "", scrollTop: 0, classList: { add() {}, remove() {}, contains: () => true, toggle() {} },
    addEventListener(t, f) { (l[t] = l[t] || []).push(f); }, fire(t, e) { (l[t] || []).forEach(f => f(e)); },
    querySelectorAll: () => [], querySelector: () => null, contains: () => false };
}
function setup() {
  const ids = ["detailPopup", "detailPopup2", "detailPopup3", "spendDock", "chartCategories"];
  const els = Object.fromEntries(ids.map(i => [i, makeEl()]));
  const docL = {};
  const doc = { getElementById: i => els[i], addEventListener(t, f) { (docL[t] = docL[t] || []).push(f); } };
  let now = 0, timers = [], nextId = 1;
  const fetches = [];
  const win = {
    setTimeout(fn, ms) { const id = nextId++; timers.push({ id, at: now + ms, fn }); return id; },
    clearTimeout(id) { timers = timers.filter(t => t.id !== id); },
    fetch(url) { return new Promise((res, rej) => fetches.push({ url, resolve: d => res({ ok: true, json: async () => d }), fail: () => rej(new Error("net")) })); },
  };
  const advance = (ms) => { now += ms; const due = timers.filter(t => t.at <= now); timers = timers.filter(t => t.at > now); due.forEach(t => t.fn()); };
  const row = { name: "Core", detailTitle: "Core", categories: [{ name: "Groceries", group: "Food", value: 5, merchants: [["Kroger", 3], ["Aldi", 2]] },
    { name: "Pharmacy", group: "Health", value: 1, merchants: [["CVS", 1]] }] };
  const row2 = { name: "Flex", detailTitle: "Flex", categories: [{ name: "Fun", group: "Play", value: 1, merchants: [["Cinema", 1]] }] };
  const model = { totalDetail: { detailTitle: "Total", detail: [] }, rows: [row, row2] };
  let range = { from: "2026-01-01", to: "2026-10-27" };
  const dock = initSpendingDock({ doc, win, getModel: () => model, getRange: () => range });
  // Open the row, then the category.
  const label = { closest: s => (s === ".row-label" ? { closest: () => ({ dataset: { row: "1" } }) } : null) };
  els.chartCategories.fire("mouseover", { target: label });
  els.detailPopup.fire("mouseover", { target: { closest: () => ({ dataset: { cat: "0" } }) } });
  const mrow = (i) => ({ closest: () => ({ dataset: { merchant: String(i) }, contains: () => false }) });
  const over = (i) => els.detailPopup2.fire("mouseover", { target: mrow(i) });
  const labelFor = (n) => ({ closest: s => (s === ".row-label" ? { closest: () => ({ dataset: { row: String(n) } }) } : null) });
  const catOver = (c) => els.detailPopup.fire("mouseover", { target: { closest: () => ({ dataset: { cat: String(c) } }) } });
  return { els, labelFor, catOver, win, fetches, advance, over, mrow, dock, setRange: r => { range = r; } };
}
const flush = () => new Promise(r => setImmediate(r));
const payload = (m) => ({ transactions: [{ date: "2026-10-02", account: "Visa", merchant: m, amount: 3, notes: "" }], total: 3 });

test("passing over a merchant for under 200 ms makes no request", () => {
  const t = setup();
  t.over(0); t.advance(199);
  t.els.detailPopup2.fire("mouseout", { target: t.mrow(0), relatedTarget: null });
  t.advance(500);
  assert.equal(t.fetches.length, 0);
  assert.equal(t.els.detailPopup3.innerHTML, "");
});
test("resting 200 ms fetches the merchant's transactions", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  assert.equal(t.fetches.length, 1);
  assert.match(t.fetches[0].url, /type=Core&group=Food&category=Groceries&merchant=Kroger$/);
  t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Kroger/);
});
test("out-of-order responses do not overwrite the current merchant", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.over(1); t.advance(200);
  assert.equal(t.fetches.length, 2);
  t.fetches[1].resolve(payload("Aldi")); await flush();
  t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Aldi/);
  assert.ok(!t.els.detailPopup3.innerHTML.includes("Kroger"));
});
test("a stale merchant line shows No transactions found.", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  t.fetches[0].resolve({ transactions: [], total: 0 }); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /No transactions found\./);
});
test("a click pins at once and hovering another merchant no longer replaces it", async () => {
  const t = setup();
  t.els.detailPopup2.fire("click", { target: t.mrow(0) });
  assert.equal(t.fetches.length, 1);                       // no 200 ms wait
  t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Pinned/);
  t.over(1); t.advance(500);
  assert.equal(t.fetches.length, 1);
});
test("Enter pins from the keyboard", () => {
  const t = setup(); let prevented = false;
  t.els.detailPopup2.fire("keydown", { key: "Enter", target: t.mrow(1), preventDefault() { prevented = true; } });
  assert.equal(t.fetches.length, 1); assert.ok(prevented);
});
test("changing the date range while pinned empties the panel and the cache misses", async () => {
  const t = setup();
  t.els.detailPopup2.fire("click", { target: t.mrow(0) });
  t.fetches[0].resolve(payload("Kroger")); await flush();
  t.setRange({ from: "2025-01-01", to: "2025-12-31" });
  t.dock.onRangeChange();
  assert.equal(t.els.detailPopup3.innerHTML, "");
  // The range change closed every panel; reopen row and category, then hover works again.
  t.els.chartCategories.fire("mouseover", { target: t.labelFor(1) }); t.catOver(0);
  t.over(0); t.advance(200);
  assert.equal(t.fetches.length, 2);
  assert.match(t.fetches[1].url, /from=2025-01-01/);
});
test("a response that lands after a range change is dropped", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  t.dock.onRangeChange();
  t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.equal(t.els.detailPopup3.innerHTML, "");
});
test("the same line is served from cache the second time", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.fetches[0].resolve(payload("Kroger")); await flush();
  t.over(1); t.advance(200); t.fetches[1].resolve(payload("Aldi")); await flush();
  t.over(0); t.advance(200);
  assert.equal(t.fetches.length, 2);
  assert.match(t.els.detailPopup3.innerHTML, /Kroger/);
});

test("onRangeChange closes every panel and a stale merchant hover fetches nothing", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.fetches[0].resolve(payload("Kroger")); await flush();
  t.dock.onRangeChange();
  for (const k of ["detailPopup", "detailPopup2", "detailPopup3"]) assert.equal(t.els[k].innerHTML, "");
  t.over(0); t.advance(500);
  assert.equal(t.fetches.length, 1);
  assert.equal(t.els.detailPopup3.innerHTML, "");
});
test("a stale in-flight response cannot refill the cleared cache", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  t.dock.onRangeChange();
  t.fetches[0].resolve(payload("Kroger")); await flush();
  // Reopen the same row/category (same URL) - must fetch again rather than read a stale cache entry.
  t.els.chartCategories.fire("mouseover", { target: t.labelFor(1) }); t.catOver(0);
  t.over(0); t.advance(200);
  assert.equal(t.fetches.length, 2);
});
test("a failed load shows the error, keeps it across Pin, and retries on the same merchant", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  t.fetches[0].fail(); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Couldn't load transactions/);
  const pinBtn = { closest: () => ({ dataset: { dock: "pin" } }) };
  t.els.detailPopup3.contains = () => true;
  t.els.spendDock.fire("click", { target: pinBtn });
  assert.match(t.els.detailPopup3.innerHTML, /Pinned/);
  assert.match(t.els.detailPopup3.innerHTML, /Couldn't load transactions/);
  assert.ok(!t.els.detailPopup3.innerHTML.includes("Loading"));
  t.els.detailPopup2.fire("click", { target: t.mrow(0) });          // same merchant again: retry
  assert.equal(t.fetches.length, 2);
  t.fetches[1].resolve(payload("Kroger")); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Kroger/);
});
test("re-hovering a merchant whose load failed retries", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.fetches[0].fail(); await flush();
  t.over(0); t.advance(200);
  assert.equal(t.fetches.length, 2);
});
test("clicking a merchant whose request is already in flight does not fetch twice", async () => {
  const t = setup();
  t.over(0); t.advance(200);
  t.els.detailPopup2.fire("click", { target: t.mrow(0) });
  assert.equal(t.fetches.length, 1);
  t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.match(t.els.detailPopup3.innerHTML, /Pinned/);
  assert.match(t.els.detailPopup3.innerHTML, /Kroger/);
});
test("changing category clears the transactions panel", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.fetches[0].resolve(payload("Kroger")); await flush();
  assert.notEqual(t.els.detailPopup3.innerHTML, "");
  t.catOver(1);
  assert.equal(t.els.detailPopup3.innerHTML, "");
  assert.match(t.els.detailPopup2.innerHTML, /CVS/);
});
test("changing the tracking type clears the merchants and transactions panels", async () => {
  const t = setup();
  t.over(0); t.advance(200); t.fetches[0].resolve(payload("Kroger")); await flush();
  t.els.chartCategories.fire("mouseover", { target: t.labelFor(2) });
  assert.equal(t.els.detailPopup2.innerHTML, "");
  assert.equal(t.els.detailPopup3.innerHTML, "");
});
