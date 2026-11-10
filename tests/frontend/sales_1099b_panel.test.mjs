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
  await import("../../frontend/js/dashboard_decomp_sales_ledger_ui.js");
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

describe("suggestions and return of capital", () => {
  test("renders advisory candidates and the possible return of capital label", () => {
    const html = m.bbReportRowHtml({ ...REPORT.rows[1], symbol: "ABCD", possible_return_of_capital: { amount: 50, fraction_of_basis: 0.04 },
      suggestions: [{ sale_id: 7, score: 88, reason: "same symbol; <i>x</i>" }] });
    assert.match(html, /Possible return of capital \(\$50\.00\)/);
    assert.match(html, /Ledger row 7, score 88: same symbol; &lt;i&gt;x/);
    assert.match(html, /nothing is applied/);
  });
  test("rows without them render as before", () => {
    assert.doesNotMatch(m.bbReportRowHtml(REPORT.rows[0]), /return of capital|Possible ledger rows/);
  });
});

describe("preview and control totals", () => {
  test("a tying corrected statement can be applied once the differences are reviewed", () => {
    m.bbMarkViewed(true);
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
    m.bbSetStatement("statement text");
    await m.bbPreviewStatement();
    assert.deepEqual(calls[0], ["/api/sales/1099b/preview", "POST", { broker: "vanguard", account: "Brokerage", content: "statement text" }]);
    await m.bbApply();
    assert.equal(calls.length, 1); // not reviewed yet: nothing applied
    m.bbMarkViewed(true);
    await m.bbApply();
    assert.deepEqual(calls[1], ["/api/sales/1099b/apply", "POST", { broker: "vanguard", account: "Brokerage", content: "statement text", replace: false }]);
  });
  test("replacing an earlier import asks first and sends replace true; declining sends nothing", async () => {
    globalThis.api = ((orig) => async (url, opts) => (url === "/api/sales/1099b/preview" ? (calls.push([url]), PREVIEW({ supersedes: { statement_id: 2, line_count: 1 } })) : orig(url, opts)))(globalThis.api);
    m.bbSetStatement("statement text");
    await m.bbPreviewStatement();
    m.bbMarkViewed(true);
    confirmAnswer = false;
    calls.length = 0;
    await m.bbApply();
    assert.equal(calls.length, 0);
    confirmAnswer = true;
    await m.bbApply();
    assert.equal(calls[0][2].replace, true);
  });
  test("exports the report CSV", async () => {
    m.bbSetStatement("statement text");
    await m.bbPreviewStatement();
    m.bbExportCsv();
    assert.deepEqual(downloads, [["1099b_difference_vanguard_2025.csv", "status,symbol\nchanged,ABCD\n"]]);
  });
});

describe("summary publish", () => {
  test("publishes b1099 with count 0 (no tied-account data yet); no slPublish does not throw", async () => {
    const pub = [];
    globalThis.slPublish = (k, s) => pub.push([k, s]);
    await m.bbLoadAccounts();
    assert.deepEqual(pub.at(-1), ["b1099", { count: 0, tone: "", text: "" }]);
    delete globalThis.slPublish;
    await assert.doesNotReject(m.bbLoadAccounts());
  });
});

describe("apply gating (Task 15)", () => {
  test("bbCanApply is true only when the totals tie (can_apply) and the report was viewed", () => {
    assert.equal(m.bbCanApply(PREVIEW(), true), true);
    assert.equal(m.bbCanApply(PREVIEW(), false), false);
    assert.equal(m.bbCanApply(PREVIEW({ can_apply: false }), true), false);
    assert.equal(m.bbCanApply(PREVIEW({ can_apply: false }), false), false);
    assert.equal(m.bbCanApply(null, true), false);
  });
  test("Apply is disabled with a visible reason until the box is ticked, then enabled", () => {
    m.bbMarkViewed(false);
    let html = m.bbPreviewHtml(PREVIEW());
    assert.match(html, /onclick="bbApply\(\)" disabled/);
    assert.match(html, /Review the differences and tick the box; totals must tie\./);
    assert.match(html, /<input type="checkbox"[^>]*onchange="bbMarkViewed\(this\.checked\)"[^>]*> I have reviewed this difference report/);
    m.bbMarkViewed(true);
    html = m.bbPreviewHtml(PREVIEW());
    assert.doesNotMatch(html, /onclick="bbApply\(\)" disabled/);
    assert.doesNotMatch(html, /Review the differences and tick the box/);
    assert.match(html, /<input type="checkbox"[^>]*checked/);
  });
  test("viewed resets when a new preview is built", async () => {
    m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage");
    await m.bbPreviewStatement();
    m.bbMarkViewed(true);
    assert.equal(m.bbCanApply(PREVIEW(), true), true);
    await m.bbPreviewStatement();
    assert.match(m.bbPreviewHtml(PREVIEW()), /onclick="bbApply\(\)" disabled/);
  });
  test("the diff, changes and control totals sit in the panel body, never inside a details", async () => {
    m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage");
    await m.bbPreviewStatement();
    const html = m.renderSalesBroker1099b();
    assert.doesNotMatch(html, /<details/);
    assert.match(html, /Difference report for 2025/);
    assert.match(html, /Control totals tie/);
    assert.doesNotMatch(html, /1 Source|2 Preview|3 Apply|aria-current="step"/);   // the step labels are gone
  });
  test("1099-B card has no paste textarea", () => {
    assert.doesNotMatch(m.renderSalesBroker1099b(), /<textarea|paste/i);
    assert.match(m.renderSalesBroker1099b(), /type="file"/);
  });
  test("1099-B account list is the taxable investment accounts only (no IRA, no checking)", async () => {
    const orig = globalThis.api;
    globalThis.api = async (url) => (url === "/api/sales/years" ? { success: true, years: [2026], taxable_accounts: ["Matt_Trust"], account_classes: {} } : orig(url));
    try {
      await m.bbLoadAccounts();
      const html = m.renderSalesBroker1099b();
      const opts = [...html.matchAll(/<option value="([^"]*)" ?[^>]*>/g)].map((x) => x[1]).filter((v) => v && v !== "etrade_gl" && v.includes("_"));
      assert.deepEqual(opts, ["Matt_Trust"]);
    } finally { globalThis.api = orig; }
  });
  test("s1099bAutoOpen is false before Feb 1 of the next year, true after it when no 1099-B is on file", () => {
    const none = { year: 2026, taxableSales: 4, has1099b: false };
    assert.equal(m.s1099bAutoOpen(2026, none, new Date(2027, 0, 31, 12)), false);
    assert.equal(m.s1099bAutoOpen(2026, none, new Date(2027, 1, 1)), true);
    assert.equal(m.s1099bAutoOpen(2026, { ...none, has1099b: true }, new Date(2027, 5, 1)), false);
    assert.equal(m.s1099bAutoOpen(2026, { ...none, taxableSales: 0 }, new Date(2027, 5, 1)), false);   // nothing sold: nothing to import
    assert.equal(m.s1099bAutoOpen(null, none, new Date(2027, 5, 1)), false);                           // All years
  });
  test("a failed apply keeps nothing applied: unticked apply posts nothing; replace confirm still asked after ticking", async () => {
    globalThis.api = ((orig) => async (url, opts) => (url === "/api/sales/1099b/preview" ? (calls.push([url]), PREVIEW({ supersedes: { statement_id: 2, line_count: 1 } })) : orig(url, opts)))(globalThis.api);
    m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage");
    await m.bbPreviewStatement();
    calls.length = 0;
    await m.bbApply();
    assert.equal(calls.length, 0);
    m.bbMarkViewed(true);
    confirmAnswer = false;
    await m.bbApply();
    assert.equal(calls.length, 0);
  });
  test("after a successful apply the next-step links show", async () => {
    globalThis.slNextStepHtml = (r) => `<nav class="sl-next">${r && r.wash ? "WASH" : ""}</nav>`;
    m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage");
    await m.bbPreviewStatement();
    m.bbMarkViewed(true);
    await m.bbApply();
    assert.match(m.renderSalesBroker1099b(), /WASH/);
    delete globalThis.slNextStepHtml;
  });
  test("the shell state text names a pending preview", async () => {
    m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage");
    await m.bbPreviewStatement();
    assert.match(m.bbStateText(), /Preview ready/);
  });
});

describe("stale preview guard (final review I4)", () => {
  // A preview request whose answer the test releases by hand.
  const deferredPreview = () => {
    const orig = globalThis.api;
    let release;
    globalThis.api = (url, opts) => {
      if (url !== "/api/sales/1099b/preview") return orig(url, opts);
      calls.push([url, opts && opts.method, JSON.parse(opts.body)]);
      return new Promise((r) => { release = () => r(PREVIEW()); });
    };
    return { release: () => release(), restore: () => { globalThis.api = orig; } };
  };
  test("an answer for the old account is dropped when the account changes while the preview is in flight", async () => {
    m.bbSetBroker("vanguard"); m.bbSetAccount("Brokerage"); m.bbSetStatement("statement text");
    const d = deferredPreview();
    try {
      const p = m.bbPreviewStatement();
      m.bbSetAccount("Other");
      d.release(); await p;
      assert.equal(m.bbStateText(), ""); // no preview kept
      assert.doesNotMatch(m.renderSalesBroker1099b(), /Difference report|Previewing/);
      assert.match(m.renderSalesBroker1099b(), /onclick="bbPreviewStatement\(\)" >Preview/); // not busy any more
      m.bbMarkViewed(true);
      calls.length = 0;
      await m.bbApply();
      assert.equal(calls.length, 0); // nothing applied with the new account
    } finally { d.restore(); }
  });
  test("an unchanged in-flight preview still lands and applies", async () => {
    m.bbSetBroker("vanguard"); m.bbSetAccount("Brokerage"); m.bbSetStatement("statement text");
    const d = deferredPreview();
    try {
      const p = m.bbPreviewStatement();
      d.release(); await p;
      assert.match(m.bbStateText(), /Preview ready/);
      m.bbMarkViewed(true);
      calls.length = 0;
      await m.bbApply();
      assert.deepEqual(calls[0], ["/api/sales/1099b/apply", "POST", { broker: "vanguard", account: "Brokerage", content: "statement text", replace: false }]);
    } finally { d.restore(); }
  });
  test("apply after an input change post-preview is refused", async () => {
    m.bbSetBroker("vanguard"); m.bbSetAccount("Brokerage"); m.bbSetStatement("statement text");
    await m.bbPreviewStatement();
    m.bbMarkViewed(true);
    m.bbSetBroker("etrade");
    calls.length = 0;
    await m.bbApply();
    assert.equal(calls.length, 0);
    m.bbSetBroker("vanguard");
  });
});

describe("focus-safe review box and state (Task 15 fix)", () => {
  const els = {};
  const withDom = async (fn) => {
    const prev = globalThis.document;
    let repaints = 0;
    els.bbRoot = { querySelector: () => null, set innerHTML(v) { repaints++; }, get innerHTML() { return ""; } };
    els.bbApplyBtn = { disabled: true }; els.bbApplyReason = { textContent: "x" }; els["sl-sec-state-b1099"] = { textContent: "" };
    globalThis.document = { getElementById: (id) => els[id] || null };
    try { await fn(() => repaints); } finally { globalThis.document = prev; }
  };
  const previewed = async () => { m.bbSetStatement("statement text"); m.bbSetAccount("Brokerage"); await m.bbPreviewStatement(); };
  test("ticking the box toggles Apply and the reason in place, without repainting the root", async () => {
    await withDom(async (repaints) => {
      await previewed();
      const before = repaints();
      m.bbMarkViewed(true);
      assert.equal(repaints(), before);
      assert.equal(els.bbApplyBtn.disabled, false);
      assert.equal(els.bbApplyReason.textContent, "");
      m.bbMarkViewed(false);
      assert.equal(els.bbApplyBtn.disabled, true);
      assert.match(els.bbApplyReason.textContent, /tick the box/);
    });
  });
  test("Apply is described by the single reason sentence", () => {
    m.bbMarkViewed(false);
    const html = m.bbPreviewHtml(PREVIEW({ can_apply: false }));
    assert.match(html, /id="bbApplyBtn" aria-describedby="bbApplyReason"/);
    assert.equal((html.match(/tick the box|Apply is off/g) || []).length, 1);
  });
  test("shell state shows the pending preview and clears after apply", async () => {
    globalThis.slNextStepHtml = () => "";
    await withDom(async () => {
      await previewed();
      assert.match(els["sl-sec-state-b1099"].textContent, /Preview ready/);
      m.bbMarkViewed(true);
      await m.bbApply();
      assert.equal(els["sl-sec-state-b1099"].textContent, "");
    });
    delete globalThis.slNextStepHtml;
  });
  test("the post-apply links clear when the account, broker, text or file changes", async () => {
    for (const change of [() => m.bbSetAccount("Brokerage"), () => m.bbSetBroker("etrade"), () => m.bbSetStatement("other")]) {
      globalThis.slNextStepHtml = (r) => (r ? "<nav>NEXT</nav>" : "");
      await previewed(); m.bbMarkViewed(true); await m.bbApply();
      assert.match(m.renderSalesBroker1099b(), /NEXT/);
      change();
      assert.doesNotMatch(m.renderSalesBroker1099b(), /NEXT/);
    }
    delete globalThis.slNextStepHtml;
    m.bbSetBroker("vanguard");
  });
});

describe("wash sales in the tie report", () => {
  test("same-account amounts are compared and cross-account amounts say they are on no 1099-B", () => {
    const h = m.bbWashHtml({ same_account: [{ sale_key: "Trust|WXYZ|2025-10-15", broker: 60, computed: 40 }], cross_account: [{ sale_key: "Trust|WXYZ|2025-10-15", amount: 20, label: "Spouse Roth" }] });
    assert.match(h, /<th class="rc-num">Broker reported<\/th><th class="rc-num">Computed here<\/th>/);
    assert.match(h, /\$60\.00<\/td><td class="rc-num">\$40\.00/);
    assert.match(h, /not on any 1099-B: your return must include these/);
    assert.match(h, /Spouse Roth/);
    assert.equal(m.bbWashHtml({ same_account: [], cross_account: [] }), "");
    assert.equal(m.bbWashHtml(null), "");
  });
});
