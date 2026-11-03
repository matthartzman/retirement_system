// Plan step 5.2 UI: HTML helpers and fetch calls of dashboard_decomp_sales_1099b.js (1099-B import on the Sales Ledger page).
import { test, describe, before, beforeEach } from "node:test";
import assert from "node:assert/strict";

let m;
const calls = [];
let confirmAnswer = true;
let downloads = [];
const field = (o = {}) => ({ ledger: 100, official: 120, delta: 20, ...o });
const REPORT = {
  tax_year: 2025,
  totals: { changed: 1, unchanged: 0, not_previously_entered: 1, no_1099b_line: 1, wash_disallowed: 60, proceeds_delta: 20, basis_delta: 0, gain_delta: 20 },
  rows: [
    { status: "changed", symbol: "ABCD", date_sold: "2025-09-10", quantity: 10, kind: "lot", sale_ids: [1], changed: ["proceeds", "gain"], wash_disallowed: 60, note: "",
      fields: { proceeds: field(), basis: field({ official: null, note: "broker did not report basis; ledger value kept" }), gain: field(), holding_period: { ledger: "short", official: "long" } } },
    { status: "not_previously_entered", symbol: null, date_sold: "2025-12-03", quantity: 5000, kind: "line", sale_ids: [], changed: [], wash_disallowed: 0, note: "no ledger row; will be added as source 1099b",
      fields: { proceeds: field({ ledger: 0 }), basis: field({ ledger: 0 }), gain: field({ ledger: 0 }), holding_period: { ledger: null, official: "long" } } },
    { status: "no_1099b_line", symbol: "ZZZ", date_sold: "2025-04-01", quantity: 1, kind: "ledger", sale_ids: [3], changed: [], wash_disallowed: 0, note: "no 1099-B line",
      fields: { proceeds: field({ official: null }), basis: field({ official: null }), gain: field({ official: null }), holding_period: { ledger: "short", official: null } } },
  ],
};
const PREVIEW = (o = {}) => ({
  success: true, can_apply: true, received: 2, account: "Brokerage", tax_year: 2025, broker: "vanguard", errors: [], warnings: [],
  meta: { corrected: true, statement_date: "2026-03-14" }, control_totals: { status: "ok", gaps: [] },
  report: REPORT, report_csv: "status,symbol\nchanged,ABCD\n", supersedes: null, changes_since_previous: [], ...o,
});

before(async () => {
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  globalThis.document = { getElementById: () => null };
  globalThis.confirm = () => confirmAnswer;
  globalThis.downloadBlob = (name, text) => downloads.push([name, text]);
  globalThis.api = async (url, opts) => {
    calls.push([url, opts && opts.method, opts && opts.body ? JSON.parse(opts.body) : null]);
    if (url === "/api/sales/broker/imports") return { accounts: ["Brokerage"] };
    if (url === "/api/sales/1099b/preview") return PREVIEW();
    if (url === "/api/sales/1099b/apply") return { success: true, statement_id: 4, corrected: 3, added: 1, superseded: null };
    return { success: true };
  };
  m = await import("../../frontend/js/dashboard_decomp_sales_1099b.js");
});
beforeEach(() => { calls.length = 0; downloads = []; confirmAnswer = true; });

describe("difference report", () => {
  test("shows ledger to official figures with the delta, the term change and the wash-sale column", () => {
    const html = m.bbReportRowHtml(REPORT.rows[0]);
    assert.match(html, /Changed/);
    assert.match(html, /\$100\.00 &rarr; \$120\.00 <span class="muted">\(\+\$20\.00\)/);
    assert.match(html, /short &rarr; long/);
    assert.match(html, /<td class="rc-num">\$60\.00<\/td>/);
    assert.match(html, /broker did not report basis; ledger value kept/);
  });
  test("a line with no symbol is labelled, and unreported ledger rows keep their status", () => {
    assert.match(m.bbReportRowHtml(REPORT.rows[1]), /Not previously entered[\s\S]*\(no symbol\)/);
    assert.match(m.bbReportRowHtml(REPORT.rows[2]), /No 1099-B line/);
  });
  test("totals list the counts and the wash-sale total", () => {
    const html = m.bbTotalsHtml(REPORT.totals);
    assert.match(html, /1 changed/);
    assert.match(html, /1 not previously entered/);
    assert.match(html, /1 ledger rows with no 1099-B line/);
    assert.match(html, /Wash-sale loss disallowed \(column 1g\): \$60\.00/);
  });
  test("an empty report says so", () => {
    assert.match(m.bbReportHtml({ tax_year: 2025, rows: [], totals: {} }), /Nothing to compare/);
  });
  test("escapes statement text", () => {
    assert.doesNotMatch(m.bbReportRowHtml({ ...REPORT.rows[1], symbol: "<b>x</b>" }), /<b>x/);
  });
});

describe("preview and control totals", () => {
  test("a tying corrected statement can be applied", () => {
    const html = m.bbPreviewHtml(PREVIEW());
    assert.match(html, /CORRECTED statement dated 2026-03-14/);
    assert.match(html, /Control totals tie/);
    assert.doesNotMatch(html, /onclick="bbApply\(\)" disabled/);
    assert.match(html, /Apply official numbers/);
  });
  test("a gap shows the difference and turns Apply off", () => {
    const gaps = [{ term: "long", covered: true, column: "proceeds", statement: 100, detail: 90, difference: 10 }];
    const html = m.bbPreviewHtml(PREVIEW({ can_apply: false, control_totals: { status: "mismatch", gaps }, errors: [{ line: 0, error: "Control totals do not match" }] }));
    assert.match(html, /long covered proceeds: statement \$100\.00, lines \$90\.00 \(difference \$10\.00\)/);
    assert.match(html, /onclick="bbApply\(\)" disabled/);
  });
  test("a superseded earlier import is announced with the changes since it", () => {
    const html = m.bbPreviewHtml(PREVIEW({ supersedes: { statement_id: 2, applied_at: "2026-02-01", corrected: false, line_count: 7 },
      changes_since_previous: [{ change: "changed", symbol: "ABCD", date_sold: "2025-09-10", fields: { gain: { old: 1, new: 3, delta: 2 } } }] }));
    assert.match(html, /Applying this one replaces it/);
    assert.match(html, /gain \$1\.00 &rarr; \$3\.00/);
    assert.match(html, /Replace earlier import and apply/);
  });
});

describe("calls", () => {
  test("preview needs an account and a statement", async () => {
    await m.bbPreviewStatement();
    assert.equal(calls.length, 0);
  });
  test("preview posts pasted text with the chosen broker and account, then apply posts it with replace false", async () => {
    m.bbSetBroker("vanguard");
    m.bbSetAccount("Brokerage");
    m.bbSetText("statement text");
    await m.bbPreviewStatement();
    assert.deepEqual(calls[0], ["/api/sales/1099b/preview", "POST", { broker: "vanguard", account: "Brokerage", content: "statement text" }]);
    await m.bbApply();
    assert.deepEqual(calls[1], ["/api/sales/1099b/apply", "POST", { broker: "vanguard", account: "Brokerage", content: "statement text", replace: false }]);
  });
  test("replacing an earlier import asks first and sends replace true; declining sends nothing", async () => {
    globalThis.api = ((orig) => async (url, opts) => (url === "/api/sales/1099b/preview" ? (calls.push([url]), PREVIEW({ supersedes: { statement_id: 2, line_count: 1 } })) : orig(url, opts)))(globalThis.api);
    m.bbSetText("statement text");
    await m.bbPreviewStatement();
    confirmAnswer = false;
    calls.length = 0;
    await m.bbApply();
    assert.equal(calls.length, 0);
    confirmAnswer = true;
    await m.bbApply();
    assert.equal(calls[0][2].replace, true);
  });
  test("exports the report CSV", async () => {
    m.bbSetText("statement text");
    await m.bbPreviewStatement();
    m.bbExportCsv();
    assert.deepEqual(downloads, [["1099b_difference_vanguard_2025.csv", "status,symbol\nchanged,ABCD\n"]]);
  });
});
