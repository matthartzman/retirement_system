// Transaction log panel (dashboard_decomp_transactions_log.js): start, add/revise/void, transfer, drift banner.
import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  globalThis.document = { getElementById: () => null };
  globalThis.confirm = () => true;
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/transactions/log") return LOG;
    return { success: true };
  };
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
  await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
  m = await import("../../frontend/js/dashboard_decomp_transactions_log.js");
});
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
  const els = {}, focused = [], live = {};
  const get = (id) => (els[id] ||= { id, innerHTML: "", focus() { focused.push(id); }, scrollIntoView() { focused.push("scroll:" + id); } });
  globalThis.document = { getElementById: get };
  globalThis.slAnnounce = (t) => { live.text = t; };
  return { els, focused, live, restore() { globalThis.document = { getElementById: () => null }; delete globalThis.slAnnounce; } };
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
