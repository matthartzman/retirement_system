// Brokerage activity import panel (dashboard_decomp_broker_import.js) and the ledger row actions it relies on.
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
let sl;
const calls = [];
before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.window = globalThis;
  globalThis.accountDisplayLabel = (a) => String(a).replace(/^Member_1_/, "Matt's ");
  globalThis.document = { getElementById: () => null };
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/sales/broker/imports") return { success: true, imports: [], accounts: ["Member_1_HSA"] };
    if (url === "/api/sales/broker/commit") return { success: true, rows_new: 3, lots_added: 1, confirmed: [1], queued: [] };
    return { success: true };
  };
  sl = await import("../../frontend/js/dashboard_decomp_sales_ledger.js");
  m = await import("../../frontend/js/dashboard_decomp_broker_import.js");
});
beforeEach(() => { calls.length = 0; });

const PREVIEW = {
  needs_account: false, received: 4, will_write: [{}, {}, {}], already_imported: 1, date_from: "2026-01-16", date_to: "2026-09-30",
  account: "Member_1_HSA", tax_class: "hsa", errors: [], warnings: ["SHRT: the holdings would end at -20 shares."],
  counts: { lots_add: 1, lots_present: 1, orders: 2, orders_ready: 1, income_rows: 2 },
  lots: [{ run_date: "2026-05-12", kind: "buy", symbol: "TOTL", shares: 10, price: 100, action: "add" },
    { run_date: "2026-09-18", kind: "reinvest", symbol: "TOTL", shares: 2, price: 100.5, action: "present", lot_date: "2026-09-17", price_diff: 0.1 }],
  orders: [{ trade_date: "2026-08-12", symbol: "TOTL", shares: 6.5, proceeds: 682.47, status: "ready",
    lots: [{ shares: 5, purchase_date: "2025-12-30", origin: "holdings" }, { shares: 1.5, purchase_date: "2026-05-12", origin: "import" }] },
  { trade_date: "2026-05-11", symbol: "SHRT", shares: 20, proceeds: 999.95, status: "no_lots", lots_short: 20 }],
  income_totals: { dividend: 205.62 }, monarch_covered: [],
};

describe("preview", () => {
  test("shows lots, orders with their lots, income and warnings, and the commit button", () => {
    const h = m.biPreviewHtml(PREVIEW);
    assert.match(h, /3 new, 1 already imported/);
    assert.match(h, /New lot/);
    assert.match(h, /Already in holdings \(2026-09-17, price differs by \$0\.10\)/);
    assert.match(h, /5 from 2025-12-30; 1\.5 from 2026-05-12 \(new\)/);
    assert.match(h, /No lots/);
    assert.match(h, /Dividend \$205\.62/);
    assert.match(h, /SHRT: the holdings/);
    assert.match(h, /Import 3 rows/);
  });
  test("asks for the account when the file name gives none", () => {
    assert.match(m.biPreviewHtml({ needs_account: true }), /Choose the plan account/);
  });
  test("error rows block the import", () => {
    const h = m.biPreviewHtml({ ...PREVIEW, errors: [{ line: 9, error: "a trade row has no quantity" }] });
    assert.match(h, /Line 9: a trade row has no quantity/);
    assert.doesNotMatch(h, /biCommit/);
  });
});

describe("broker and per-account pickers", () => {
  const HINTS = [{ hint: "vanguard:1111", account: null, rows: 6 }, { hint: "vanguard:2222", account: "Member_2_Roth", rows: 5 }];
  test("asks for an account per account hint, preselecting remembered ones", () => {
    const h = m.biHintPickersHtml(HINTS, ["Member_2_IRA", "Member_2_Roth"], {});
    assert.equal((h.match(/<select/g) || []).length, 2);
    assert.match(h, /Plan account for vanguard:1111 \(6 rows\)/);
    assert.match(h, /biSetHintAccount\('vanguard:2222', this\.value\)/);
    assert.match(h, /value="Member_2_Roth" selected/);
    assert.equal(m.biHintPickersHtml([HINTS[0]], [], {}), "");
    assert.match(m.biPreviewHtml({ needs_account: true, hints: HINTS }), /for each account in this file/);
  });
  test("a multi-account preview shows the account on lots and sales", () => {
    const h = m.biPreviewHtml({ ...PREVIEW, broker: "vanguard", account: "Member_2_IRA, Member_2_Roth", tax_class: null, hints: HINTS,
      lots: PREVIEW.lots.map((l) => ({ ...l, account: "Member_2_IRA" })), orders: PREVIEW.orders.map((o) => ({ ...o, account: "Member_2_Roth" })) });
    assert.match(h, /<th>Account<\/th>/);
    assert.match(h, /<td>Member_2_IRA<\/td><td>2026-05-12/);
    assert.match(h, /<td>Member_2_Roth<\/td><td>2026-08-12/);
    assert.match(h, /Vanguard, accounts Member_2_IRA, Member_2_Roth\./);
  });
  test("the broker and account map are sent with the request", async () => {
    m.biSetBroker("vanguard");
    m.biSetHintAccount("vanguard:1111", "Member_2_IRA");
    await m.biPreviewFile();
    assert.equal(calls[0][0], "/api/sales/broker/preview");
    assert.equal(calls[0][2].broker, "vanguard");
    assert.deepEqual(calls[0][2].accounts, { "vanguard:1111": "Member_2_IRA" });
    m.biSetBroker("");
    calls.length = 0;
    await m.biCommit();
    assert.equal(calls[0][2].broker, "");
  });
});

describe("imports and income", () => {
  test("an applied import offers Revert", () => {
    const h = m.biImportsHtml([{ import_id: 4, account: "A", date_from: "2026-01-01", date_to: "2026-09-30", rows_new: 3, status: "applied" },
      { import_id: 5, account: "A", rows_new: 0, status: "reverted" }]);
    assert.equal((h.match(/biRevert\(4\)/g) || []).length, 1);
    assert.doesNotMatch(h, /biRevert\(5\)/);
  });
  test("income check lists months and one-sided rows", () => {
    const h = m.biIncomeHtml({ monarch_accounts: ["hsa"], totals: { matched: 2, broker: 205.62, monarch: 205.53, difference: 0.09 },
      months: [{ month: "2026-09", broker: 201.12, monarch: 201, difference: 0.12 }],
      broker_only: [{ run_date: "2026-09-30", symbol: "FDRXX", amount: 0.12 }], monarch_only: [] });
    assert.match(h, /2 matched/);
    assert.match(h, /Only in the broker file:<\/strong> 2026-09-30 FDRXX \$0\.12/);
    assert.match(h, /sl-down/);
  });
});

describe("calls", () => {
  test("commit sends the chosen method only when confirming", async () => {
    m.biSetMethod("hifo");
    m.biSetAccount("Member_1_HSA");
    await m.biCommit();
    assert.equal(calls[0][0], "/api/sales/broker/commit");
    assert.equal(calls[0][2].confirm_method, "");
    m.biSetConfirm(true);
    calls.length = 0;
    await m.biCommit();
    assert.equal(calls[0][2].confirm_method, "hifo");
  });
});

describe("ledger row actions", () => {
  const S = (o) => ({ sale_id: 7, sale_date: "2026-06-10", account: "A", symbol: "X", shares: 1, proceeds: 1, fees: 0, basis: 1,
    gain: 0, holding_period: "long", status: "confirmed", ...o });
  test("manual rows can be edited; queue rows go back to the queue; 1099-B rows can only be voided", () => {
    assert.match(sl.slRowHtml(S({ source: "manual" })), /slEdit\(7\).*slVoid\(7\)/);
    assert.match(sl.slRowHtml(S({ source: "broker" })), /slRequeue\(7\)/);
    assert.doesNotMatch(sl.slRowHtml(S({ source: "broker" })), /slVoid/);
    assert.match(sl.slRowHtml(S({ source: "1099b" })), /slVoid\(7\)/);
  });
  test("requeue posts to the sale's requeue route", async () => {
    await sl.slRequeue(7);
    assert.equal(calls[0][0], "/api/sales/7/requeue");
  });
});

describe("account in file", () => {
  test("the plan account picker offers 'Account in file' and sends no single account for it", async () => {
    assert.match(m.renderBrokerImport(), /Account in file/);
    m.biSetAccount("__in_file__");
    calls.length = 0;
    await m.biPreviewFile();
    const body = calls.find((c) => c[0] === "/api/sales/broker/preview")[2];
    assert.equal(body.account, "");
    m.biSetAccount("");
  });
});

describe("friendly account names", () => {
  test("plan account pull-downs show the friendly name and keep the internal value", async () => {
    m.biSetBroker("");
    await m.biLoadImports();
    const h = m.renderBrokerImport();
    assert.match(h, /<option value="Member_1_HSA" [^>]*>Matt&#39;s HSA|<option value="Member_1_HSA" [^>]*>Matt's HSA/);
  });
});

describe("single-account file that names no plan account", () => {
  test("shows a picker for it so the preview and Import button can follow", () => {
    const one = [{ hint: "fidelity:X1", account: null, rows: 3 }];
    assert.equal(m.biHintPickersHtml(one, ["Roth"], {}), "");
    const h = m.biHintPickersHtml(one, ["Roth"], {}, true);
    assert.equal((h.match(/<select/g) || []).length, 1);
    assert.match(h, /biSetHintAccount\('fidelity:X1', this\.value\)/);
    assert.match(m.biPreviewHtml({ needs_account: true, hints: one }), /picker above/);
  });
});

describe("unreadable files and the imports table", () => {
  test("a preview with errors and no counts renders the errors instead of throwing", () => {
    const h = m.biPreviewHtml({ errors: [{ line: 0, error: "This file's layout is not recognized; choose the broker." }], will_write: [], hints: [] });
    assert.match(h, /layout is not recognized/);
    assert.doesNotMatch(h, /Line 0/);
    assert.match(m.biPreviewHtml({ errors: [], will_write: [] }), /could be read/);
  });
  test("imports sort by the clicked heading, newest first by default", () => {
    const list = [{ import_id: 1, account: "B", rows_new: 5, status: "applied" }, { import_id: 2, account: "A", rows_new: 9, status: "reverted" }];
    const ids = (h) => [...h.matchAll(/<tr><td>(\d+)<\/td>/g)].map((x) => x[1]).join(",");
    assert.equal(ids(m.biImportsHtml(list)), "2,1");
    m.biSortBy("rows_new");
    assert.equal(ids(m.biImportsHtml(list)), "1,2");
    m.biSortBy("rows_new");
    assert.equal(ids(m.biImportsHtml(list)), "2,1");
    assert.match(m.biImportsHtml(list), /aria-sort="descending"/);
  });
  test("the imports list is a collapsed section by default", () => {
    assert.match(m.renderBrokerImport(), /<details\s+ontoggle/);
    m.biToggleImports(true);
    assert.match(m.renderBrokerImport(), /<details open/);
    m.biToggleImports(false);
  });
});
