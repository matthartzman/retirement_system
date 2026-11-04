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
  assert.match(h, /Matt's IRA[^<]*<\/span>|Matt's IRA · managed|managed/);
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
