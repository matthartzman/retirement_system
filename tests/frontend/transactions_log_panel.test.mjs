// Transaction log panel (dashboard_decomp_transactions_log.js): start, add/revise/void, transfer, drift banner.
import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { installInAppConfirm, resetInAppConfirm, confirmState } from "./inapp_confirm_stub.mjs";

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
  await installInAppConfirm();
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
  m = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
});
// Swap the in-app confirm dialog for one test (fn(message) answers it; undefined = no dialog exists) and always put the
// original back (no leakage into later tests).
async function withConfirm(fn, body) {
  const orig = globalThis.showInAppConfirm;
  if (fn === undefined) delete globalThis.showInAppConfirm;
  else globalThis.showInAppConfirm = async (msg) => fn(msg);
  try { await body(); } finally { globalThis.showInAppConfirm = orig; }
}
beforeEach(() => { calls.length = 0; });

const LOG = {
  started: true,
  rows: [{ txn_id: 7, txn_date: "2026-05-12", account: "Member_1_IRA", type: "buy", symbol: "TOTL", shares: 10, price: 100, source: "manual", note: "<i>x</i>" }],
  open: [{ lot_txn_id: 7, account: "Member_1_IRA", symbol: "TOTL", purchase_date: "2026-05-12", price: 100, shares: 4 }],
  drift: [{ account: "Member_1_IRA", symbol: "ZZZ", purchase_date: "2024-06-01", holdings_shares: 9, log_shares: 7, reason: "the holdings have more shares than the log" }],
};

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
  m.tlApplyFilters({});
}
const PLAIN = [];

test("not started shows the start button only", () => {
  const h = m.tlHtml({ started: false, rows: [], open: [], drift: [] });
  assert.match(h, /Start the transaction log/);
  assert.doesNotMatch(h, /Add transaction/);
});

test("started log shows friendly names, escapes notes and saves immediately; drift lives on the ledger, not here", () => {
  const h = m.tlHtml(LOG);
  assert.match(h, /Matt's IRA/);
  assert.match(h, /Changes here save immediately\./);
  assert.doesNotMatch(h, /The log and the holdings differ|managed/i);
  assert.doesNotMatch(h, /<i>x<\/i>/);
  assert.match(m.tlHealthHtml({ ...LOG, drift: [] }), /agrees with the holdings/);
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

test("summary: health counts drifting accounts, log counts rows, not started is bad; paint without slPublish is safe", async () => {
  const pub = {};
  globalThis.slPublish = (k, s) => { pub[k] = s; };
  await m.tlLoad();
  assert.deepEqual(pub.health, { count: 1, tone: "bad", text: "drift: 1 accounts" });
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
  assert.match(h, /<a href="#holdings\/activity\?account=Member_1_IRA&amp;symbol=S0&amp;back=sales">Show in Activity<\/a>/);
  m.tlShowAllHealth(true);
  assert.equal((m.tlHealthHtml({ ...LOG, drift: DRIFT7 }).match(/<li>/g) || []).length, 7);
  m.tlShowAllHealth(false);
  assert.match(m.tlHealthHtml({ ...LOG, drift: [] }), /agrees with the holdings/);
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
  for (const t of ["Year", "Account", "Symbol", "Type"]) assert.match(h, new RegExp(`<label for="tlF[A-Za-z]+">${t} `));
});

test("layout: both drawers sit above the filters and the entries", async () => {
  const h = m.tlHtml(BIG(3), ...PLAIN);
  const at = (re) => h.search(re);
  assert.ok(at(/＋ Add transaction/) > 0 && at(/＋ Add transaction/) < at(/⇄ Transfer/));
  assert.ok(at(/⇄ Transfer/) < at(/class="sl-filters tl-filters"/));
  assert.ok(at(/class="sl-filters tl-filters"/) < at(/id="tlEntries"/));
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
  assert.equal(startBtns(window.slHealthSlotHtml()), 1);
  assert.equal(startBtns(m.renderTransactionLog()), 1);                 // Activity carries its own Start prompt when the log is not started
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
test("void uses the in-app confirm: cancel posts nothing; no dialog available fails closed", async () => {
  await loadLog(LOG);
  calls.length = 0;
  await withConfirm(() => false, async () => assert.equal(await m.tlVoid(7), false));
  assert.equal(calls.length, 0);
  await withConfirm(undefined, async () => assert.equal(await m.tlVoid(7), false));
  assert.equal(calls.filter((c) => c[0] === "/api/transactions/7/void").length, 0);
  await withConfirm(() => true, () => m.tlVoid(7));
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

// ---- Activity on Investment Holdings (Sales Ledger v3) ----
const CASH_LOG = () => ({ ...LOG, rows: [
  { txn_id: 20, txn_date: "2026-11-02", account: "Member_1_IRA", type: "opening", symbol: "CASH", shares: 500, price: 1, source: "backfill", note: "" },
  { txn_id: 21, txn_date: "2026-11-02", account: "Member_1_IRA", type: "opening", symbol: "TOTL", shares: 4, price: 100, source: "backfill", note: "" },
  ...LOG.rows] });

test("cash opening rows are hidden by default and counted in the toolbar; the box shows them", async () => {
  await loadLog(CASH_LOG());
  const h = m.tlHtml(CASH_LOG());
  assert.equal(rowIds(h).includes(20), false);
  assert.equal(rowIds(h).includes(21), true);
  assert.match(h, /Show cash opening rows \(1\)/);
  m.tlSetFilter("showCashOpening", true);
  assert.equal(rowIds(m.tlHtml(CASH_LOG())).includes(20), true);
  assert.deepEqual(m.tlFilterRows(CASH_LOG().rows, { showCashOpening: false }).map((r) => r.txn_id), [21, 7]);
  m.tlApplyFilters({});
});

test("no managed checkboxes or chips are rendered, and no history mode", async () => {
  await loadLog(LOG);
  const h = m.tlHtml(LOG);
  assert.doesNotMatch(h, /type="checkbox"[^>]*data-managed|tl-managed|Managed accounts|History &amp; held|tlModeEdit|Held only/);
  assert.equal(typeof m.tlSetManaged, "undefined");
  assert.equal(typeof m.tlSetMode, "undefined");
});

test("Void is inside the edit dialog, not on the table rows", async () => {
  await loadLog(LOG);
  assert.doesNotMatch(m.tlHtml(LOG), /Void this transaction|tlVoid\(/);
  const dom = fakeDom();
  m.tlEditRow(7);
  const h = m.tlHtml(LOG);
  assert.match(h, /Void this transaction/);
  assert.match(h, /tlVoid\(7\)/);
  assert.equal((h.match(/tlVoid\(/g) || []).length, 1);
  m.tlCancel();
  dom.restore();
});

test("a sale row links to Sales Ledger › Sales", async () => {
  const log = { ...LOG, rows: [{ ...LOG.rows[0], txn_id: 9, type: "sell" }] };
  assert.match(m.tlHtml(log), /<a href="#sales_ledger\?tab=ledger">Sale in Sales Ledger<\/a>/);
  assert.doesNotMatch(m.tlHtml(LOG), /Sale in Sales Ledger/);
});

test("Activity shows a bank-account cleanup banner when the preview is non-empty; Clean up asks, then posts the explicit list", async () => {
  const orig = globalThis.api;
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/transactions/log") return LOG;
    if (url === "/api/transactions/bank-cleanup" && !opts) return { success: true, accounts: [{ account: "Business_Checking", managed: false, opening_rows: [3] }, { account: "Family_Checking", managed: true, opening_rows: [4] }] };
    return { success: true };
  };
  try {
    await m.tlLoad();
    const h = m.tlHtml(LOG);
    assert.match(h, /2 bank accounts have log rows that do not belong here: Business_Checking, Family_Checking/);
    calls.length = 0;
    await withConfirm(() => false, () => m.tlCleanBank());
    assert.equal(calls.filter((c) => c[1] === "POST").length, 0);
    await withConfirm(() => true, () => m.tlCleanBank());
    assert.deepEqual(calls.find((c) => c[1] === "POST"), ["/api/transactions/bank-cleanup", "POST", { accounts: ["Business_Checking", "Family_Checking"] }]);
  } finally { globalThis.api = orig; }
  await m.tlLoad();
  assert.doesNotMatch(m.tlHtml(LOG), /bank account/);
});

test("a deep link applies its filters; source=backfill reveals the backfilled cash opening rows", () => {
  m.tlApplyFilters({ account: "Member_1_IRA", type: "opening", year: "2026", source: "backfill" });
  const h = m.tlHtml(CASH_LOG());
  assert.deepEqual(rowIds(h), [21, 20]);
  assert.match(h, /id="tlFYear"[^>]*>[^]*?<option value="2026" selected>/);
  m.tlApplyFilters({});
});
