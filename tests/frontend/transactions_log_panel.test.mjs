// Transaction log panel (dashboard_decomp_transactions_log.js): start, add/revise/void, transfer, drift banner.
import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
let hist = { rows: [], held: [] }; // what GET /api/transactions?… (the history view) returns
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  globalThis.document = { getElementById: () => null };
  globalThis.confirm = () => true;
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/transactions/log") return LOG;
    if (url.startsWith("/api/transactions?")) return hist;
    return { success: true };
  };
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
  await import("../../frontend/js/dashboard_decomp_transactions.js");
  m = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
});
// Swap window.confirm for one test and always put the original back (no leakage into later tests).
async function withConfirm(fn, body) {
  const orig = globalThis.confirm;
  globalThis.confirm = fn;
  try { await body(); } finally { globalThis.confirm = orig; }
}
beforeEach(() => { calls.length = 0; });

const LOG = {
  started: true,
  rows: [{ txn_id: 7, txn_date: "2026-05-12", account: "Member_1_IRA", type: "buy", symbol: "TOTL", shares: 10, price: 100, source: "manual", note: "<i>x</i>" }],
  open: [{ lot_txn_id: 7, account: "Member_1_IRA", symbol: "TOTL", purchase_date: "2026-05-12", price: 100, shares: 4 }],
  drift: [{ account: "Member_1_IRA", symbol: "ZZZ", purchase_date: "2024-06-01", holdings_shares: 9, log_shares: 7, reason: "the holdings have more shares than the log" }],
};

test("not started shows the start button only", () => {
  const h = m.tlHtml({ started: false, rows: [], open: [], drift: [] });
  assert.match(h, /Start the transaction log/);
  assert.doesNotMatch(h, /Add transaction/);
});

test("started log shows friendly names, drift banner, and escapes notes", () => {
  const h = m.tlHtml(LOG);
  assert.match(h, /Matt's IRA/);
  assert.match(h, /The log and the holdings differ/);
  assert.doesNotMatch(h, /<i>x<\/i>/);
  assert.match(m.tlHtml({ ...LOG, drift: [] }), /agrees with the holdings/);
});

test("start posts backfill; add and edit post the right routes", async () => {
  await m.tlStart();
  assert.equal(calls[0][0], "/api/transactions/backfill");
  calls.length = 0;
  m.tlSetForm("txn_date", "2026-06-01"); m.tlSetFormAccount("Member_1_IRA"); m.tlSetForm("symbol", "TOTL"); m.tlSetForm("shares", "2"); m.tlSetForm("price", "101");
  await m.tlSave();
  assert.equal(calls[0][0], "/api/transactions");
  assert.equal(calls[0][2].shares, "2");
  await m.tlLoad(); calls.length = 0;
  m.tlEditRow(7);
  m.tlSetForm("shares", "12");
  await m.tlSave();
  assert.equal(calls[0][0], "/api/transactions/7/revise");
});

test("void asks to confirm then posts; transfer lists only the source account's open lots", async () => {
  await m.tlLoad(); calls.length = 0;
  await m.tlVoid(7);
  assert.equal(calls[0][0], "/api/transactions/7/void");
  m.tlSetXferFrom("Member_1_IRA");
  assert.match(m.tlHtml(LOG), /TOTL 2026-05-12 @ 100/);
  m.tlSetXferTo("Member_1_Roth"); m.tlSetXfer("symbol", "TOTL"); m.tlSetXfer("txn_date", "2026-07-01"); m.tlPick(7, "3");
  calls.length = 0;
  await m.tlTransfer();
  assert.deepEqual(calls[0][2].allocation, { 7: 3 });
  assert.equal(calls[0][0], "/api/transactions/transfer");
});

test("managed toggle shows each account's state and posts the route", async () => {
  const h = m.tlHtml({ ...LOG, managed: ["Member_1_IRA"] });
  assert.match(h, /data-managed="Member_1_IRA" checked/);
  await m.tlLoad(); calls.length = 0;
  await m.tlSetManaged("Member_1_IRA", true);
  assert.equal(calls[0][0], "/api/transactions/accounts/Member_1_IRA/managed");
  assert.equal(calls[0][1], "POST");
  assert.deepEqual(calls[0][2], { managed: true });
  assert.doesNotMatch(m.tlHtml(LOG), /data-managed="Member_1_IRA" checked/);
});

test("summary: health counts drifting accounts, log counts rows, not started is bad; paint without slPublish is safe", async () => {
  const pub = {};
  globalThis.slPublish = (k, s) => { pub[k] = s; };
  await m.tlLoad();
  assert.deepEqual(pub.health, { count: 1, tone: "bad", text: "drift: 1 accounts" });
  assert.deepEqual(pub.log, { count: 1, tone: "", text: "" });
  const orig = globalThis.api;
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad();
  assert.deepEqual(pub.health, { count: 1, tone: "bad", text: "log not started" });
  delete globalThis.slPublish;
  await assert.doesNotReject(m.tlLoad());
  globalThis.api = orig;
});

const DRIFT7 = Array.from({ length: 7 }, (_, i) => ({ account: "Member_1_IRA", symbol: "S" + i, purchase_date: "2024-06-0" + (i + 1), holdings_shares: 9, log_shares: 7, reason: "differs" }));

test("health: 7 drift items show 5 rows and Show all 7; show all reveals every row", async () => {
  const h = m.tlHealthHtml({ ...LOG, drift: DRIFT7 });
  assert.match(h, /The log and the holdings differ/);
  assert.equal((h.match(/<li>/g) || []).length, 5);
  assert.match(h, /Show all 7/);
  assert.match(h, /tlFocusRow\(/);
  m.tlShowAllHealth(true);
  assert.equal((m.tlHealthHtml({ ...LOG, drift: DRIFT7 }).match(/<li>/g) || []).length, 7);
  m.tlShowAllHealth(false);
  assert.match(m.tlHealthHtml({ ...LOG, drift: [] }), /agrees with the holdings/);
});

test("managed chips mark managed accounts and keep the checkbox list in an Edit details", () => {
  const h = m.tlManagedChipsHtml({ ...LOG, managed: ["Member_1_IRA"] });
  assert.match(h, /Managed accounts \(1\)/);
  assert.match(h, /<span[^>]*>Matt's IRA · managed<\/span>/);
  assert.match(h, /· managed/);
  assert.match(h, /<details/);
  assert.match(h, /data-managed="Member_1_IRA" checked/);
  assert.doesNotMatch(m.tlManagedChipsHtml({ ...LOG, managed: [] }), /· managed/);
});

test("not-started health render has the Start button and no details; started shows drift only", async () => {
  const orig = globalThis.api;
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad();
  const h = m.renderLogHealth();
  assert.match(h, /Start the transaction log/);
  assert.match(h, /The log is not started/);
  assert.doesNotMatch(h, /<details/);
  globalThis.api = orig;
  await m.tlLoad();
  const s = m.renderLogHealth();
  assert.match(s, /id="tlHealthRoot"/);
  assert.match(s, /The log and the holdings differ/);
});

test("tlHtml default keeps drift and managed; health:false omits the drift block", () => {
  const withManaged = { ...LOG, managed: ["Member_1_IRA"] };
  assert.match(m.tlHtml(withManaged), /The log and the holdings differ/);
  const h = m.tlHtml(withManaged, undefined, undefined, undefined, { health: false });
  assert.doesNotMatch(h, /The log and the holdings differ/);
  assert.doesNotMatch(h, /agrees with the holdings/);
  assert.match(h, /Add transaction/);
});

test("tlFocusRow goes to the log via slGo when defined and is safe when not", () => {
  const seen = [];
  globalThis.slGo = (...a) => seen.push(a);
  m.tlFocusRow("Member_1_IRA", "ZZZ", "2024-06-01");
  assert.deepEqual(seen[0], ["fix", "log"]);
  delete globalThis.slGo;
  assert.doesNotThrow(() => m.tlFocusRow("Member_1_IRA", "ZZZ", "2024-06-01"));
});

// ---- Task 9: filters, pagination, drawers --------------------------------------------------------------------
const BIG = (n) => ({ started: true, drift: [], open: [], rows: Array.from({ length: n }, (_, i) => ({ txn_id: i + 1, txn_date: `${2020 + (i % 5)}-03-01`, account: i % 2 ? "Member_1_IRA" : "Member_1_Roth", type: i % 3 ? "buy" : "sell", symbol: i % 4 ? "TOTL" : "vxus", shares: 1, price: 2, source: "manual" })) });
const rowIds = (h) => [...h.matchAll(/<tr id="tlRow(\d+)"/g)].map((x) => Number(x[1]));
// A document whose elements remember innerHTML/focus so repaints and focus moves can be observed.
function fakeDom() {
  const els = {}, focused = [], live = {}, boxes = [];
  const get = (id) => (els[id] ||= { id, innerHTML: "", focus() { focused.push(id); }, scrollIntoView() { focused.push("scroll:" + id); } });
  globalThis.document = { getElementById: get, querySelectorAll: (sel) => (sel === "input[data-managed]" ? boxes : []) };
  globalThis.slAnnounce = (t) => { live.text = t; };
  return { els, focused, live, boxes, restore() { globalThis.document = { getElementById: () => null }; delete globalThis.slAnnounce; } };
}
async function loadLog(log) {
  const orig = globalThis.api;
  globalThis.api = async (url) => (url === "/api/transactions/log" ? log : { success: true });
  await m.tlLoad();
  globalThis.api = orig;
  m.tlSetFilter("account", ""); m.tlSetFilter("symbol", ""); m.tlSetFilter("year", ""); m.tlSetFilter("type", "");
}
const PLAIN = [undefined, undefined, undefined, { health: false }];

test("tlFilterRows: account exact, symbol case-insensitive, year prefix, type exact, empty = no constraint", () => {
  const rows = BIG(40).rows;
  assert.equal(m.tlFilterRows(rows, {}).length, 40);
  assert.equal(m.tlFilterRows(rows, { symbol: "VXUS" }).length, rows.filter((r) => r.symbol === "vxus").length);
  assert.ok(m.tlFilterRows(rows, { account: "Member_1_IRA" }).every((r) => r.account === "Member_1_IRA"));
  assert.ok(m.tlFilterRows(rows, { year: "2021" }).every((r) => r.txn_date.startsWith("2021")));
  assert.ok(m.tlFilterRows(rows, { type: "sell" }).every((r) => r.type === "sell"));
  assert.equal(m.tlFilterRows(rows, { account: "Member_1_ira" }).length, 0);
});

test("tlPage: first N rows and remaining clamped at zero", () => {
  assert.deepEqual(m.tlPage([1, 2, 3], 2), { rows: [1, 2], remaining: 1 });
  assert.deepEqual(m.tlPage([1, 2, 3], 25), { rows: [1, 2, 3], remaining: 0 });
  assert.deepEqual(m.tlPage([], 25), { rows: [], remaining: 0 });
});

test("0 rows keeps the empty-log text; 1 row shows Showing 1 of 1 and no Show more", async () => {
  await loadLog(BIG(0));
  assert.match(m.tlHtml(BIG(0), ...PLAIN), /The log is empty\./);
  await loadLog(BIG(1));
  const h = m.tlHtml(BIG(1), ...PLAIN);
  assert.match(h, /Showing 1 of 1/);
  assert.doesNotMatch(h, /Show 25 more/);
});

test("5,000 rows: 25 first, newest first, Show 25 more adds 25 and moves focus to the first new row, button ends", async () => {
  const log = BIG(5000);
  await loadLog(log);
  const h = m.tlHtml(log, ...PLAIN);
  const ids = rowIds(h);
  assert.equal(ids.length, 25);
  assert.equal(ids[0], 5000);
  assert.match(h, /Showing 25 of 5000/);
  assert.match(h, /Show 25 more/);
  assert.doesNotMatch(h, /max-height|overflow-y/);
  const dom = fakeDom();
  m.tlShowMore();
  assert.equal(rowIds(dom.els.tlEntries.innerHTML).length, 50);
  assert.match(dom.els.tlEntries.innerHTML, /Showing 50 of 5000/);
  assert.deepEqual(dom.focused, ["tlRow4975"]);
  assert.equal(dom.live.text, "25 more rows shown");
  for (let i = 0; i < 198; i++) m.tlShowMore();
  assert.match(dom.els.tlEntries.innerHTML, /Showing 5000 of 5000/);
  assert.doesNotMatch(dom.els.tlEntries.innerHTML, /Show 25 more/);
  dom.restore();
});

test("a filter with no match says so; changing a filter resets paging and repaints only the entries area", async () => {
  const log = BIG(200);
  await loadLog(log);
  const dom = fakeDom();
  m.tlShowMore(); m.tlShowMore();
  assert.equal(rowIds(dom.els.tlEntries.innerHTML).length, 75);
  m.tlSetFilter("type", "buy");
  assert.equal(rowIds(dom.els.tlEntries.innerHTML).length, 25);
  assert.equal(dom.els.tlRoot, undefined);
  m.tlSetFilter("symbol", "NOSUCH");
  assert.match(dom.els.tlEntries.innerHTML, /No transactions match\./);
  m.tlSetFilter("symbol", "vxus"); m.tlSetFilter("year", "2020");
  assert.ok(rowIds(dom.els.tlEntries.innerHTML).length > 0);
  dom.restore();
  await loadLog(log);
});

test("filter controls have real labels, including Filter year", async () => {
  await loadLog(BIG(3));
  const h = m.tlHtml(BIG(3), ...PLAIN);
  for (const t of ["Account", "Symbol", "Filter year", "Type"]) assert.match(h, new RegExp(`<label for="tlF[A-Za-z]+">${t} `));
});

test("layout: both drawers sit above the filters and the entries", async () => {
  const h = m.tlHtml(BIG(3), ...PLAIN);
  const at = (re) => h.search(re);
  assert.ok(at(/＋ Add transaction/) > 0 && at(/＋ Add transaction/) < at(/＋ Transfer between accounts/));
  assert.ok(at(/＋ Transfer between accounts/) < at(/class="sl-filters tl-filters"/));
  assert.ok(at(/class="sl-filters tl-filters"/) < at(/id="tlEntries"/));
  assert.ok(at(/tl-managed-chips/) < at(/＋ Add transaction/));
  assert.match(h, /<details class="drawer" id="tlAddDrawer" ontoggle/);
});

test("tlEditRow renders the drawer open before values are set, scrolls and focuses; Cancel closes it", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  m.tlEditRow(2);
  assert.match(dom.els.tlRoot.innerHTML, /<details class="drawer" id="tlAddDrawer" open/);
  assert.match(dom.els.tlRoot.innerHTML, /Revise transaction/);
  assert.ok(dom.focused.includes("scroll:tlAddDrawer"));
  assert.equal(dom.focused.at(-1), "tlFDate");
  m.tlCancel();
  assert.doesNotMatch(dom.els.tlRoot.innerHTML, /id="tlAddDrawer" open/);
  dom.restore();
  assert.doesNotThrow(() => m.tlEditRow(2));
  m.tlCancel();
});

test("tlFocusRow filters by account and symbol, resets paging and keeps the slGo call", async () => {
  await loadLog(BIG(100));
  const dom = fakeDom(), seen = [];
  globalThis.slGo = (...a) => seen.push(a);
  m.tlShowMore();
  m.tlFocusRow("Member_1_IRA", "TOTL", "2024-06-01");
  const h = dom.els.tlRoot.innerHTML;
  assert.match(h, /<option value="Member_1_IRA" selected>/);
  assert.match(h, /id="tlFSym" size="7" value="TOTL"/);
  assert.ok(rowIds(h).length <= 25);
  assert.deepEqual(seen[0], ["fix", "log"]);
  delete globalThis.slGo; dom.restore();
  await loadLog(BIG(1));
});

test("tlFocusRow arguments with an apostrophe and a backslash yield a valid, escaped handler", () => {
  const acct = "O'Brien\\IRA";
  const h = m.tlHealthHtml({ ...LOG, drift: [{ ...LOG.drift[0], account: acct, symbol: "A'B" }] });
  const attr = h.match(/onclick="(tlFocusRow\([^"]*\))"/)[1];
  const raw = attr.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
  let got;
  new Function("tlFocusRow", raw)((...a) => { got = a; });
  assert.deepEqual(got, [acct, "A'B", "2024-06-01"]);
});

test("health: Show all repaints only #tlHealthRoot and refocuses the toggle", async () => {
  await loadLog({ ...LOG, drift: DRIFT7 });
  const dom = fakeDom();
  m.tlShowAllHealth(true);
  assert.match(dom.els.tlHealthRoot.innerHTML, /Show fewer/);
  assert.equal(dom.els.tlRoot, undefined);
  assert.deepEqual(dom.focused, ["tlHealthToggle"]);
  m.tlShowAllHealth(false);
  dom.restore();
  await loadLog(LOG);
});

test("bare Start prompt shows start and load errors", async () => {
  const orig = globalThis.api;
  globalThis.api = async (url) => { if (url === "/api/transactions/log") return { started: false, rows: [], open: [], drift: [] }; throw new Error("backfill failed"); };
  await m.tlLoad();
  await m.tlStart();
  assert.match(m.renderLogHealth(), /backfill failed/);
  globalThis.api = async () => { throw new Error("load failed"); };
  await m.tlLoad();
  assert.match(m.renderLogHealth(), /load failed/);
  globalThis.api = orig;
  await m.tlLoad();
});

test("health slot: one Start button when not started, none when started; repaints on the started flip", async () => {
  const startBtns = (h) => (h.match(/Start the transaction log/g) || []).length;
  const orig = globalThis.api;
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad();
  assert.equal(startBtns(window.slHealthSlotHtml() + m.renderTransactionLog()), 1);
  globalThis.api = orig;
  await m.tlLoad();
  assert.equal(startBtns(window.slHealthSlotHtml() + m.renderTransactionLog()), 0);
  const dom = fakeDom();
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad();
  dom.els.tlHealthSlot = { innerHTML: "untouched" };
  globalThis.api = orig;
  await m.tlLoad();
  assert.notEqual(dom.els.tlHealthSlot.innerHTML, "untouched");
  dom.els.tlHealthSlot.innerHTML = "untouched";
  await m.tlLoad();
  assert.equal(dom.els.tlHealthSlot.innerHTML, "untouched");
  dom.restore();
});

test("health slot repaint replaces the slot's content only: the slot id appears once (no nested wrapper)", async () => {
  const orig = globalThis.api;
  const dom = fakeDom();
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad();
  dom.els.tlHealthSlot = { innerHTML: "untouched" };
  globalThis.api = orig;
  await m.tlLoad(); // started flips: the slot repaints
  const html = '<div id="tlHealthSlot">' + dom.els.tlHealthSlot.innerHTML + "</div>"; // what the DOM holds: the slot node plus its new content
  assert.equal(html.split('id="tlHealthSlot"').length - 1, 1);
  assert.equal(window.slHealthSlotHtml().split('id="tlHealthSlot"').length - 1, 1);
  dom.restore();
});

test("page ids stay unique after the real started-flip repaint writes the slot", async () => {
  const orig = globalThis.api;
  const dom = fakeDom();
  globalThis.api = async () => ({ started: false, rows: [], open: [], drift: [] });
  await m.tlLoad(); // tlSlotStarted = false
  const page = window.renderSalesLedger();
  const slot = dom.els.tlHealthSlot = { innerHTML: "" };
  const before = '<div id="tlHealthSlot">' + window.slHealthSlotInnerHtml() + "</div>";
  assert.ok(page.includes(before));
  globalThis.api = orig;
  await m.tlLoad(); // started flips: tlPaint writes the slot
  assert.notEqual(slot.innerHTML, "");
  const live = page.replace(before, '<div id="tlHealthSlot">' + slot.innerHTML + "</div>");
  const ids = [...live.matchAll(/\sid="([^"]*)"/g)].map((x) => x[1]);
  assert.deepEqual(ids.filter((x, i) => ids.indexOf(x) !== i), []);
  dom.restore();
});

test("start asks to confirm: cancel makes no call, OK posts once", async () => {
  const asked = [];
  let answer = false;
  await withConfirm((msg) => { asked.push(msg); return answer; }, async () => {
    await m.tlStart();
    assert.equal(calls.length, 0);
    answer = true;
    await m.tlStart();
  });
  assert.equal(calls.filter((c) => c[0] === "/api/transactions/backfill").length, 1);
  assert.deepEqual(asked, Array(2).fill("Starting the log means holdings will now be written by the log."));
});

// Task 10 review minor (a), deliberate update: cancel puts only the checkbox back; the log is not repainted, so the open
// "Edit…" details does not snap shut.
test("managed off asks to confirm: cancel posts nothing, re-checks only the checkbox and repaints nothing; OK posts once; turning on never asks", async () => {
  await loadLog({ ...LOG, managed: ["Member_1_IRA", "O'Brien\\IRA"] });
  const dom = fakeDom();
  const asked = [];
  let answer = false;
  dom.els.tlRoot = { innerHTML: "untouched" };
  const box = (a) => ({ checked: false, getAttribute: (n) => (n === "data-managed" ? a : null) });
  const ira = box("Member_1_IRA"), other = box("O'Brien\\IRA");
  dom.boxes.push(other, ira);
  try {
    await withConfirm((msg) => { asked.push(msg); return answer; }, async () => {
      calls.length = 0;
      assert.equal(await m.tlSetManaged("Member_1_IRA", false), false);
      assert.equal(calls.length, 0);
      assert.equal(ira.checked, true);
      assert.equal(other.checked, false);
      assert.equal(dom.els.tlRoot.innerHTML, "untouched");
      assert.equal(await m.tlSetManaged("O'Brien\\IRA", false), false);
      assert.equal(other.checked, true);
      answer = true;
      await m.tlSetManaged("Member_1_IRA", false);
      assert.equal(calls.filter((c) => c[0].endsWith("/managed")).length, 1);
      calls.length = 0; asked.length = 0;
      await m.tlSetManaged("Member_1_IRA", true);
      assert.equal(asked.length, 0);
    });
  } finally { dom.restore(); }
  globalThis.document = { getElementById: () => null }; // no querySelectorAll: cancel is still safe
  await withConfirm(() => false, async () => assert.equal(await m.tlSetManaged("Member_1_IRA", false), false));
});

test("managed-off confirm text is exact", async () => {
  const asked = [];
  await withConfirm((msg) => { asked.push(msg); return false; }, () => m.tlSetManaged("Member_1_IRA", false));
  assert.deepEqual(asked, ["Holdings freeze at their last state and the log stops updating them."]);
});

test("void uses the shared confirm: cancel posts nothing; no dialog available proceeds by design", async () => {
  await loadLog(LOG);
  calls.length = 0;
  await withConfirm(() => false, async () => assert.equal(await m.tlVoid(7), false));
  assert.equal(calls.length, 0);
  await withConfirm(undefined, () => m.tlVoid(7));
  assert.equal(calls.filter((c) => c[0] === "/api/transactions/7/void").length, 1);
});

test("account filter select includes the active account even when no log row has it", async () => {
  await loadLog(BIG(3));
  m.tlSetFilter("account", "Member_1_Drift");
  const h = m.tlHtml(BIG(3), ...PLAIN);
  assert.match(h, /<option value="Member_1_Drift" selected>/);
  m.tlSetFilter("account", "");
});

test("Esc only cancels with an edit or open add drawer, and ignores defaultPrevented", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  m.tlCancel();
  const inside = { inLog: true };
  dom.els.tlRoot.contains = (n) => !!(n && n.inLog);
  dom.els.tlRoot.innerHTML = "untouched";
  m.tlOnKeydown({ key: "Escape", target: inside });
  assert.equal(dom.els.tlRoot.innerHTML, "untouched");
  m.tlDrawerToggle("add", true);
  m.tlOnKeydown({ key: "Escape", defaultPrevented: true, target: inside });
  assert.equal(dom.els.tlRoot.innerHTML, "untouched");
  m.tlOnKeydown({ key: "a", target: inside });
  assert.equal(dom.els.tlRoot.innerHTML, "untouched");
  m.tlOnKeydown({ key: "Escape", target: inside });
  assert.notEqual(dom.els.tlRoot.innerHTML, "untouched");
  assert.doesNotMatch(dom.els.tlRoot.innerHTML, /id="tlAddDrawer" open/);
  dom.restore();
});

test("Esc outside the log root (another drawer, tab or page) keeps the revision in progress", async () => {
  await loadLog(LOG);
  const dom = fakeDom();
  m.tlEditRow(7);
  dom.els.tlRoot.contains = (n) => !!(n && n.inLog);
  dom.els.tlRoot.innerHTML = "untouched";
  m.tlOnKeydown({ key: "Escape", target: { inLog: false } }); // e.g. the Record-a-sale drawer or the 1099-B textarea
  m.tlOnKeydown({ key: "Escape", target: null });
  assert.equal(dom.els.tlRoot.innerHTML, "untouched");
  calls.length = 0;
  m.tlSetForm("shares", "12");
  await m.tlSave();
  assert.equal(calls[0][0], "/api/transactions/7/revise"); // still a revision, not a duplicate add
  dom.restore();
});

test("Esc with no log root mounted, or a root without contains(), does nothing", async () => {
  await loadLog(LOG);
  const dom = fakeDom();
  m.tlEditRow(7);
  dom.els.tlRoot.innerHTML = "untouched";
  m.tlOnKeydown({ key: "Escape", target: { inLog: true } }); // stub root has no contains()
  assert.equal(dom.els.tlRoot.innerHTML, "untouched");
  dom.restore();
  m.tlOnKeydown({ key: "Escape", target: { inLog: true } }); // getElementById returns null
  m.tlCancel();
});

test("tlHtml(otherLog) renders otherLog's rows, not the module's", async () => {
  await loadLog(BIG(3));
  const other = { started: true, drift: [], open: [], rows: [{ txn_id: 99, txn_date: "2019-01-01", account: "Member_1_IRA", type: "buy", symbol: "OTHR", shares: 1, price: 1, source: "manual" }] };
  assert.deepEqual(rowIds(m.tlHtml(other, ...PLAIN)), [99]);
});

// ---- Task 11: one Transaction log section with an "Edit log | History & held lots" mode toggle -------------------
const HROW = (i, symbol = "TOTL") => ({ date: `2026-0${(i % 9) + 1}-01`, account: "Member_1_IRA", type: "buy", symbol, shares: 1, price: 2, amount: -2, remaining: 1, linked: null, source: "broker" });
const HVIEW = (n, symbol) => ({ rows: Array.from({ length: n }, (_, i) => HROW(i, symbol)), held: [{ account: "Member_1_IRA", symbol: "TOTL", purchase_date: "2025-01-02", shares: 1, price: 2 }] });
const histUrls = () => calls.filter((c) => c[0].startsWith("/api/transactions?")).map((c) => c[0]);
const heads = (h) => [...(h.match(/<thead>.*?<\/thead>/s) || [""])[0].matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map((x) => x[1]);
const histRows = (h) => (((h.match(/<tbody>.*?<\/tbody>/s) || [""])[0]).match(/<tr>/g) || []).length;
async function inMode(mode, body) { // run body, then always return to edit mode with no filters (module state is shared)
  try { await body(); } finally {
    await m.tlSetMode("edit");
    for (const k of ["account", "symbol", "year", "type"]) m.tlSetFilter(k, "");
    m.tlSetFilter("held", false);
  }
}

test("mode toggle: Edit log is the default; the toggle names both modes and marks the active one", async () => {
  await loadLog(BIG(3));
  const h = m.tlHtml(BIG(3), ...PLAIN);
  assert.match(h, /<button[^>]*aria-pressed="true"[^>]*>Edit log<\/button>/);
  assert.match(h, /<button[^>]*aria-pressed="false"[^>]*>History &amp; held lots<\/button>/);
  assert.ok(h.indexOf("Edit log</button>") < h.indexOf('class="sl-filters tl-filters"'));
  assert.doesNotMatch(h, /Held only/);
});

test("history mode: Transactions columns, server called with the shared filters; switching back keeps every filter", async () => {
  await loadLog(BIG(200));
  const dom = fakeDom();
  await inMode("history", async () => {
    m.tlSetFilter("account", "Member_1_IRA"); m.tlSetFilter("symbol", "TOTL"); m.tlSetFilter("year", "2021"); m.tlSetFilter("type", "buy");
    hist = HVIEW(2); calls.length = 0;
    await m.tlSetMode("history");
    assert.deepEqual(histUrls(), ["/api/transactions?account=Member_1_IRA&symbol=TOTL&year=2021&type=buy"]);
    const root = dom.els.tlRoot.innerHTML, ent = dom.els.tlEntries.innerHTML;
    for (const re of [/<option value="Member_1_IRA" selected>/, /id="tlFSym" size="7" value="TOTL"/, /<option value="2021" selected>/, /<option value="buy" selected>/]) assert.match(root, re);
    assert.match(root, /<label for="tlFHeld"><input type="checkbox" id="tlFHeld"[^>]*> Held only<\/label>/);
    assert.match(root, /aria-pressed="true"[^>]*>History &amp; held lots/);
    assert.deepEqual(heads(ent), ["Date", "Account", "Type", "Symbol", "Shares", "Price", "Amount", "Remaining", "Sale", "Source"]);
    assert.doesNotMatch(ent, /tlVoid|tlEditRow/);
    assert.doesNotMatch(root, /<details ontoggle="trToggle/);
    await m.tlSetMode("edit");
    const back = dom.els.tlRoot.innerHTML;
    for (const re of [/<option value="Member_1_IRA" selected>/, /id="tlFSym" size="7" value="TOTL"/, /<option value="2021" selected>/, /<option value="buy" selected>/]) assert.match(back, re);
    assert.doesNotMatch(back, /Held only/);
    assert.match(back, /Showing 14 of 14/);
    assert.match(back, /tlVoid\(/);
    assert.equal(histUrls().length, 1); // edit mode filters client-side
  });
  dom.restore();
});

test("switching mode keeps the edit-mode paging", async () => {
  await loadLog(BIG(200));
  const dom = fakeDom();
  await inMode("history", async () => {
    m.tlShowMore();
    await m.tlSetMode("history");
    await m.tlSetMode("edit");
    assert.match(dom.els.tlRoot.innerHTML, /Showing 50 of 200/);
    assert.equal(rowIds(dom.els.tlRoot.innerHTML).length, 50);
  });
  dom.restore();
});

test("history mode: 0, 1 and many rows, and a filter that matches nothing, each update from the server", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  await inMode("history", async () => {
    await m.tlSetMode("history");
    for (const n of [0, 1, 30]) {
      hist = HVIEW(n); calls.length = 0;
      await m.tlSetFilter("symbol", `S${n}`);
      assert.deepEqual(histUrls(), [`/api/transactions?symbol=S${n}`]);
      const ent = dom.els.tlEntries.innerHTML;
      if (n === 0) assert.match(ent, /No transactions match\./); else assert.equal(histRows(ent), n);
    }
    hist = { rows: [], held: [] }; calls.length = 0;
    await m.tlSetFilter("type", "opening");
    assert.match(histUrls()[0], /type=opening/);
    assert.match(dom.els.tlEntries.innerHTML, /No transactions match\./);
  });
  dom.restore();
});

test("history mode: Held only lists the Lots held table; unchecked hides it", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  await inMode("history", async () => {
    await m.tlSetMode("history");
    hist = HVIEW(1); calls.length = 0;
    await m.tlSetFilter("held", true);
    assert.deepEqual(histUrls(), ["/api/transactions?held=1"]);
    const ent = dom.els.tlEntries.innerHTML;
    assert.match(ent, /<h4>Lots held<\/h4>/);
    assert.match(ent, /<th>Account<\/th><th>Symbol<\/th><th>Purchased<\/th><th class="rc-num">Shares<\/th><th class="rc-num">Price<\/th>/);
    assert.match(ent, /2025-01-02/);
    assert.match(m.tlHtml(BIG(3), ...PLAIN), /id="tlFHeld" checked/);
    await m.tlSetFilter("held", false);
    assert.doesNotMatch(dom.els.tlEntries.innerHTML, /Lots held/);
  });
  dom.restore();
});

test("a save in edit mode reloads history once (tlReloadAll), and the fresh history shows after switching", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  await inMode("history", async () => {
    await m.tlSetMode("history");
    await m.tlSetMode("edit");
    hist = HVIEW(1, "NEWX"); calls.length = 0;
    m.tlSetForm("txn_date", "2026-06-01"); m.tlSetFormAccount("Member_1_IRA"); m.tlSetForm("symbol", "NEWX"); m.tlSetForm("shares", "2");
    await m.tlSave();
    assert.equal(calls.filter((c) => c[0] === "/api/transactions" && c[1] === "POST").length, 1);
    assert.equal(histUrls().length, 1);
    assert.equal(calls.filter((c) => c[0] === "/api/transactions/log").length, 1);
    const n = calls.length;
    await m.tlSetMode("history");
    assert.equal(calls.length, n); // already fresh for these filters: no second fetch
    assert.match(dom.els.tlRoot.innerHTML, /<div id="tlEntries"><p class="muted tl-count">1 transaction<\/p><table class="rc-table">.*NEWX/s); // repainted from the cached history
  });
  dom.restore();
});

test("tlReloadAll refreshes the log and, in history mode, the history once; unknown modes fall back to edit", async () => {
  await loadLog(BIG(3));
  await inMode("history", async () => {
    await m.tlSetMode("history"); calls.length = 0;
    await m.tlReloadAll();
    assert.deepEqual(calls.map((c) => c[0]), ["/api/transactions/log", "/api/transactions?"]);
    await m.tlSetMode("bogus");
    assert.match(m.tlHtml(LOG, ...PLAIN), /aria-pressed="true"[^>]*>Edit log/);
  });
});

test("log summary is unchanged with history loaded: count = log rows, tone empty", async () => {
  const pub = {};
  globalThis.slPublish = (k, s) => { pub[k] = s; };
  try {
    await inMode("history", async () => {
      await m.tlSetMode("history");
      hist = HVIEW(9);
      await m.tlReloadAll();
      assert.deepEqual(pub.log, { count: LOG.rows.length, tone: "", text: "" });
    });
  } finally { delete globalThis.slPublish; }
});

// ---- Task 11 fix round 1: history without a started log, latest request wins, parity -----------------------------
const NOT_STARTED = { started: false, rows: [], open: [], drift: [] };
const HCOLS = ["Date", "Account", "Type", "Symbol", "Shares", "Price", "Amount", "Remaining", "Sale", "Source"];

test("not-started log: the section shows history (10 columns, held lots) with Edit log disabled; Start stays only in the health slot", async () => {
  const dom = fakeDom();
  const orig = globalThis.api;
  globalThis.api = async (url, o) => (url === "/api/transactions/log" ? NOT_STARTED : orig(url, o));
  try {
    await inMode("history", async () => {
      hist = HVIEW(2); calls.length = 0;
      await m.tlReloadAll();
      assert.deepEqual(histUrls(), ["/api/transactions?"]);
      const h = m.renderTransactionLog();
      assert.match(h, /Start it in the log health section/);
      assert.match(h, /<button[^>]*aria-pressed="false" disabled[^>]*>Edit log<\/button>/);
      assert.match(h, /aria-pressed="true"[^>]*>History &amp; held lots/);
      assert.deepEqual(heads(h.slice(h.indexOf('id="tlEntries"'))), HCOLS);
      assert.match(h, /2 transactions/);
      assert.match(h, /id="tlFHeld"/);
      assert.equal(((window.slHealthSlotHtml() + h).match(/Start the transaction log/g) || []).length, 1);
      await m.tlSetFilter("held", true);
      assert.match(histUrls().at(-1), /held=1/);
      assert.match(dom.els.tlEntries.innerHTML, /<h4>Lots held<\/h4>/);
      await m.tlSetMode("edit"); // not reachable from the UI (button disabled); still shows history
      assert.match(dom.els.tlRoot.innerHTML, /Start it in the log health section/);
      assert.doesNotMatch(dom.els.tlRoot.innerHTML, /tlVoid\(|Add transaction/);
    });
  } finally { globalThis.api = orig; dom.restore(); }
  await loadLog(LOG);
});

test("history: latest request wins when responses arrive out of order", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  const orig = globalThis.api, pending = {};
  globalThis.api = (url, o) => (url.startsWith("/api/transactions?") ? new Promise((r) => { pending[new URLSearchParams(url.split("?")[1]).get("symbol") || ""] = r; }) : orig(url, o));
  try {
    await inMode("history", async () => {
      const p0 = m.tlSetMode("history");
      if (pending[""]) pending[""](HVIEW(1, "INIT"));
      await p0;
      const a = m.tlSetFilter("symbol", "AAA"), b = m.tlSetFilter("symbol", "BBB");
      pending.BBB(HVIEW(2, "BBB")); await b;
      pending.AAA(HVIEW(3, "AAA")); await a;
      const ent = dom.els.tlEntries.innerHTML;
      assert.match(ent, /BBB/);
      assert.doesNotMatch(ent, /AAA|Loading…/);
      assert.match(ent, /2 transactions/);
      assert.match(m.tlHtml(BIG(3), ...PLAIN), /<div id="tlEntries"><p class="muted tl-count">2 transactions/);
    });
  } finally { globalThis.api = orig; dom.restore(); }
});

test("history parity: type options are the history types, accounts include the history view's, and a row count shows", async () => {
  await loadLog(BIG(3));
  const dom = fakeDom();
  const opts = (h, id) => [...h.match(new RegExp(`<select id="${id}".*?</select>`))[0].matchAll(/<option value="([^"]*)"/g)].map((x) => x[1]);
  await inMode("history", async () => {
    hist = { rows: [{ ...HROW(0), account: "Member_1_Hist" }], held: [{ account: "Member_1_Held", symbol: "X", purchase_date: "2025-01-02", shares: 1, price: 1 }] };
    m.tlSetFilter("symbol", "P1"); // edit mode: client-side only
    await m.tlSetMode("history");
    const h = m.tlHtml(BIG(3), ...PLAIN);
    assert.deepEqual(opts(h, "tlFType"), ["", "buy", "reinvest", "sell"]);
    for (const a of ["Member_1_Hist", "Member_1_Held", "Member_1_IRA"]) assert.ok(opts(h, "tlFAcct").includes(a), a);
    assert.ok(opts(h, "tlFYear").includes("2026"));
    assert.match(dom.els.tlEntries.innerHTML, /<p class="muted tl-count">1 transaction<\/p><table/);
    await m.tlSetMode("edit");
    const e = m.tlHtml(BIG(3), ...PLAIN);
    assert.ok(opts(e, "tlFType").includes("opening"));
    assert.ok(!opts(e, "tlFAcct").includes("Member_1_Hist"));
  });
  dom.restore();
});
