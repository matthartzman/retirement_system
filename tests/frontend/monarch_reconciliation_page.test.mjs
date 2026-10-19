// R4 of the reconciliation page: the pure HTML helpers of dashboard_decomp_monarch_reconciliation.js
// and the nav/step wiring that makes the page reachable under Reports & Review.
import { test, describe, before } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const JS = path.join(HERE, "..", "..", "frontend", "js");
const read = (f) => fs.readFileSync(path.join(JS, f), "utf8");

let m;
before(async () => {
  // The module uses the page's bare globals and registers its helpers on window.
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  globalThis.window = globalThis;
  globalThis.document = { getElementById: () => null };
  globalThis.api = async () => ({});
  m = await import("../../frontend/js/dashboard_decomp_monarch_reconciliation.js");
});

const ROW = (over) => ({
  id: "setup:Checking", label: "Checking", group: "Cash, cards and loans", status: "differs", updatable: true,
  app_value: 13000, monarch_value: 13894.27, difference: 894.27, monarch_accounts: [], auto_matched: true, report_reason: null,
  write: { kind: "setup_account", ref: "Checking", field: "Current Value", old: "13000", new: "13894.27" }, ...over,
});
const DATA = (rows, extra) => ({
  has_balances: true, as_of: "2026-10-14", latest: "2026-10-14", dates: ["2026-10-14", "2026-10-13"], rows, unmatched: [],
  app_targets: [{ id: "setup:Checking", label: "Checking", role: "Cash / spending" }, { id: "plan:home", label: "Home value (plan input)", role: "" }],
  import: { status: "ok" }, last_ok_import: { latest_date: "2026-10-14" }, ...extra,
});

describe("formatting", () => {
  test("money and signed differences", () => {
    assert.equal(m.rcMoney(1234.5), "$1,234.50");
    assert.equal(m.rcMoney(-10021.2), "-$10,021.20");
    assert.equal(m.rcMoney(null), "—");
    assert.match(m.rcDiffHtml(894.27), /rc-up.*\+\$894\.27/);
    assert.match(m.rcDiffHtml(-5), /rc-down.*-\$5\.00/);
    assert.equal(m.rcDiffHtml(null), "—");
  });
});

describe("rows", () => {
  test("a differing updatable row has a checkbox wired to rcToggle", () => {
    const html = m.rcRowHtml(ROW(), true);
    assert.match(html, /<input type="checkbox" data-id="setup:Checking"/);
    assert.match(html, /onchange="rcToggle\(this\.dataset\.id, this\.checked\)" checked/);
    assert.match(html, /\$13,000\.00/);
    assert.match(html, /\+\$894\.27/);
  });

  test("report-only rows have no checkbox and show their reason", () => {
    const html = m.rcRowHtml(ROW({ id: "setup:Brokerage", status: "report_only", updatable: false, report_reason: "Investment accounts are valued from holdings", write: null }), false);
    assert.ok(!html.includes("<input"));
    assert.match(html, /Report only/);
    assert.match(html, /valued from holdings/);
  });

  test("matched Monarch accounts are listed with how they matched", () => {
    const html = m.rcRowHtml(ROW({ auto_matched: false, monarch_accounts: [{ account: "Car A", balance: 1, closed: false, balance_date: "2026-10-14" }, { account: "Car B", balance: 2, closed: true, balance_date: "2026-10-12" }] }), false, "2026-10-14");
    assert.match(html, /Car A[^<]*<button[^>]*>✕<\/button> \+ Car B \(closed\) \(balance from 2026-10-12\) <button/);
    assert.match(html, /matched by you/);
  });

  test("labels are escaped", () => {
    const html = m.rcRowHtml(ROW({ id: 'x"><img>', label: "<b>Bad</b>" }), false);
    assert.ok(!html.includes("<img>") && !html.includes("<b>Bad"));
  });
});

describe("groups", () => {
  const rows = [
    ROW(), ROW({ id: "setup:Same", label: "Same", status: "match", updatable: false, difference: 0 }),
    ROW({ id: "plan:home", label: "Home value (plan input)", group: "Plan inputs" }),
    ROW({ id: "setup:Inv", label: "Inv", group: "Investments (report only)", status: "report_only", updatable: false }),
  ];

  test("matching rows are hidden until asked for, with a count", () => {
    const hidden = m.rcGroupsHtml(DATA(rows), new Set(), false);
    assert.ok(!hidden.includes("data-row=\"setup:Same\""));
    assert.match(hidden, /1 matching hidden/);
    assert.ok(m.rcGroupsHtml(DATA(rows), new Set(), true).includes('data-row="setup:Same"'));
  });

  test("groups appear in the fixed order and offer select/clear all", () => {
    const html = m.rcGroupsHtml(DATA(rows), new Set(["setup:Checking"]), false);
    const order = ["Cash, cards and loans", "Plan inputs", "Investments (report only)"].map((g) => html.indexOf(`<h3>${g}</h3>`));
    assert.ok(order.every((i) => i >= 0) && order[0] < order[1] && order[1] < order[2]);
    assert.match(html, /rcSelectGroup\(&quot;Cash, cards and loans&quot;, false\)">Clear/);
    assert.match(html, /rcSelectGroup\(&quot;Plan inputs&quot;, true\)">Select all differences/);
  });

  test("a group where everything matches says so", () => {
    const html = m.rcGroupsHtml(DATA([ROW({ status: "match", updatable: false, difference: 0 })]), new Set(), false);
    assert.match(html, /Everything here matches/);
  });

  test("no rows at all", () => {
    assert.match(m.rcGroupsHtml(DATA([]), new Set(), false), /No accounts to compare yet/);
  });
});

describe("summary, preview, unmatched, log", () => {
  test("summary counts statuses", () => {
    const s = m.rcSummary([{ status: "differs" }, { status: "differs" }, { status: "match" }, { status: "report_only" }, { status: "not_in_monarch" }], [{}, {}]);
    assert.deepEqual(s, { differs: 2, match: 1, reportOnly: 1, notInMonarch: 1, notInApp: 2 });
  });

  test("preview lists old to new, warns for plan inputs, and disables Apply when empty", () => {
    const html = m.rcPreviewHtml({ changes: [
      { id: "setup:Checking", label: "Checking", kind: "setup_account", old: "13000", new: "13894.27", app_value: 13000, monarch_value: 13894.27 },
      { id: "plan:home", label: "Home value (plan input)", kind: "plan:home", old: "", new: "1279500.00", app_value: 0, monarch_value: 1279500 },
    ], rejected: [{ id: "setup:Inv", reason: "Investment accounts are valued from holdings" }] });
    assert.match(html, /Update 2 numbers from the import/);
    assert.match(html, /13000.*13894\.27/s);
    assert.match(html, /blank/);
    assert.match(html, /Rebuild after applying/);
    assert.match(html, /setup:Inv: Investment accounts/);
    assert.match(html, /Apply 2 changes/);
    const empty = m.rcPreviewHtml({ changes: [], rejected: [] });
    assert.match(empty, /Nothing to update/);
    assert.match(empty, /disabled/);
    assert.equal(m.rcPreviewHtml(null), "");
  });

  test("a setup-only preview has no plan-input warning", () => {
    assert.ok(!m.rcPreviewHtml({ changes: [{ id: "a", label: "A", kind: "setup_account", old: "1", new: "2", app_value: 1, monarch_value: 2 }], rejected: [] }).includes("Rebuild after"));
  });

  test("unmatched Monarch accounts get a match picker with app targets and Ignore", () => {
    const html = m.rcUnmatchedHtml(DATA([], { unmatched: [{ account_key: "mystery", label: "Mystery <1>", monarch_value: 77, closed: false }] }));
    assert.match(html, /data-key="mystery"/);
    assert.match(html, /value="ignore"/);
    assert.match(html, /value="plan:home"/);
    assert.match(html, /Mystery &lt;1&gt;/);
    assert.equal(m.rcUnmatchedHtml(DATA([])), "");
  });

  test("change log shows Undo only for changes not yet undone", () => {
    const html = m.rcLogHtml([
      { id: 2, applied_at: "2026-10-14T04:00:00+00:00", label: "Checking", old_value: "13000", new_value: "13894.27", monarch_date: "2026-10-14", undone_at: null },
      { id: 1, applied_at: "2026-10-13T04:00:00+00:00", label: "Visa", old_value: "", new_value: "5.00", monarch_date: "2026-10-13", undone_at: "2026-10-13T05:00:00+00:00" },
    ]);
    assert.equal((html.match(/rcUndo\(/g) || []).length, 1);
    assert.match(html, /data-id="2"/);
    assert.match(html, /undone/);
    assert.match(m.rcLogHtml([]), /No updates from the import yet/);
  });

  test("a rejected latest import is surfaced with its reason", () => {
    assert.match(m.rcImportNote(DATA([], { import: { status: "rejected", detail: "stale export" } })), /rejected \(stale export\).*2026-10-14/);
    assert.equal(m.rcImportNote(DATA([])), "");
  });
});

describe("page body", () => {
  const state = (over) => ({ data: DATA([ROW()]), loading: false, error: "", message: null, selected: new Set(), preview: null, showMatched: false, tolerance: 1, log: [], ...over });

  test("loading, error and not-yet-imported states", () => {
    assert.match(m.rcBodyHtml(state({ data: null, loading: true })), /Loading the comparison/);
    assert.match(m.rcBodyHtml(state({ error: "boom" })), /boom.*Retry/s);
    assert.match(m.rcBodyHtml(state({ data: { has_balances: false } })), /No account balances have been imported/);
  });

  test("the preview button counts only selected updatable rows", () => {
    assert.match(m.rcBodyHtml(state()), /Preview update from import \(0 selected\)"?[^>]*>|disabled>Preview update from import \(0 selected\)/);
    const html = m.rcBodyHtml(state({ selected: new Set(["setup:Checking", "gone"]) }));
    assert.match(html, /Preview update from import \(1 selected\)/);
    assert.ok(!/disabled>Preview update from import \(1/.test(html));
  });

  test("the as-of picker lists dates with the latest marked, and a message shows", () => {
    const html = m.rcBodyHtml(state({ message: { text: "Updated 1 number", error: false } }));
    assert.match(html, /<option value="2026-10-14" selected>2026-10-14 \(latest\)/);
    assert.match(html, /Updated 1 number/);
    assert.match(html, /Change log/);
  });

  test("renderMonarchReconciliation returns the root container", () => {
    globalThis.setTimeout = () => 0;
    assert.match(m.renderMonarchReconciliation(), /id="rcRoot"/);
  });
});

describe("wiring", () => {
  test("the step is registered under Reports & Review, dispatched, helped and loaded", () => {
    const dash = read("dashboard.js");
    assert.match(dash, /id: "monarch_reconciliation",\s+group: "Reports & Review",\s+title: "Account Reconciliation"/);
    assert.match(dash, /activeStep === "monarch_reconciliation"\) content \+= renderMonarchReconciliation\(\)/);
    assert.match(dash, /monarch_reconciliation: pageHelp\(/);
    const html = fs.readFileSync(path.join(JS, "..", "index.html"), "utf8");
    assert.match(html, /js\/dashboard_decomp_monarch_reconciliation\.js\?v=1/);
  });

  test("every handler the markup calls is registered on window", () => {
    const src = read("dashboard_decomp_monarch_reconciliation.js");
    const called = new Set([...src.matchAll(/onchange="(rc\w+)\(|onclick="(rc\w+)\(|onclick="(loadMonarchReconciliation)\(/g)].map((x) => x[1] || x[2] || x[3]));
    for (const fn of called) assert.equal(typeof globalThis[fn], "function", `${fn} is not on window`);
  });
});

describe("review fixes", () => {
  test("each matched Monarch account has a remove-match control (by-name matches switch to ignore)", () => {
    const html = m.rcRowHtml(ROW({ monarch_accounts: [{ account_key: "chk", account: "Checking", balance: 1, closed: false, balance_date: "2026-10-14", auto: true },
      { account_key: "car", account: "Car", balance: 2, closed: false, balance_date: "2026-10-14", auto: false }] }), false, "2026-10-14");
    assert.match(html, /data-key="chk" data-auto="1"[^>]*onclick="rcUnmatch\(this\.dataset\.key, this\.dataset\.auto\)"/);
    assert.match(html, /data-key="car" data-auto=""/);
  });

  test("rcUnmatch ignores a by-name match and clears a saved one", async () => {
    const calls = [];
    globalThis.api = async (url, opts) => { calls.push([url, JSON.parse(opts && opts.body || "{}")]); return { success: true }; };
    globalThis.document = { getElementById: () => null };
    await m.rcUnmatch("chk", "1");
    await m.rcUnmatch("car", "");
    const maps = calls.filter((c) => c[0] === "/api/reconcile/map").map((c) => c[1]);
    assert.deepEqual(maps, [{ account_key: "chk", target: "ignore" }, { account_key: "car", target: null }]);
  });

  test("ignored Monarch accounts are listed with a way back", () => {
    const html = m.rcIgnoredHtml({ ignored_accounts: [{ account_key: "mystery", label: "Mystery <1>" }] });
    assert.match(html, /Ignored imported accounts \(1\)/);
    assert.match(html, /Mystery &lt;1&gt;/);
    assert.match(html, /rcMap\(this\.dataset\.key, ''\)/);
    assert.equal(m.rcIgnoredHtml({}), "");
  });

  test("re-entering the page refetches once the cached comparison is stale", async () => {
    let timers = 0;
    globalThis.setTimeout = () => { timers += 1; return 0; };
    globalThis.api = async () => ({ success: true, has_balances: false, rows: [], unmatched: [], dates: [], log: [] });
    globalThis.document = { getElementById: () => ({ innerHTML: "" }) };
    await m.loadMonarchReconciliation();
    timers = 0;
    m.renderMonarchReconciliation();
    assert.equal(timers, 0, "fresh data is not refetched");
    const realNow = Date.now;
    Date.now = () => realNow() + 60000;
    try {
      m.renderMonarchReconciliation();
    } finally {
      Date.now = realNow;
    }
    assert.equal(timers, 1, "stale data is refetched");
  });
});

describe("M4: inbox, policy, closed accounts, automatic updates", () => {
  const rows = [
    ROW({ id: "a", label: "Ask row", policy: "ask", monarch_accounts: [{ account_key: "k1", account: "K1", balance: 1 }] }),
    ROW({ id: "b", label: "Auto held", policy: "auto", auto_hold: "Plan-start input: confirm it here before it changes." }),
    ROW({ id: "c", label: "Auto clean", policy: "auto", auto_hold: null }),
    ROW({ id: "d", label: "App wins", policy: "app", status: "report_only", updatable: false }),
  ];

  test("the inbox lists ask rows and held auto rows, not clean auto, report-only or dismissed ones", () => {
    const { diffs } = m.rcInboxItems(DATA(rows));
    assert.deepEqual(diffs.map((r) => r.id), ["a", "b"]);
    assert.deepEqual(m.rcInboxItems(DATA(rows), new Set(["a@13894.27"])).diffs.map((r) => r.id), ["b"]);
  });

  test("items hidden by Ignore this time are counted and a Show hidden button brings them back", () => {
    const gone = new Set(["a@13894.27"]);
    assert.equal(m.rcInboxItems(DATA(rows), gone).hidden, 1);
    assert.match(m.rcInboxHtml(DATA(rows), gone), /1 hidden by[\s\S]*rcRestoreDismissed\(\)/);
    assert.ok(!m.rcInboxHtml(DATA(rows)).includes("rcRestoreDismissed"));
    const only = [rows[0]];
    assert.match(m.rcInboxHtml(DATA(only), gone), /Nothing needs a decision[\s\S]*Show hidden/);
  });

  test("each inbox row offers the four choices and shows why an auto change is held", () => {
    const html = m.rcInboxHtml(DATA(rows));
    for (const act of ["update", "ignore", "always", "app"]) assert.ok(html.includes("rcDecide('" + act + "'"), act);
    assert.match(html, /Plan-start input: confirm it here/);
  });

  test("an empty inbox says nothing needs a decision", () => {
    assert.match(m.rcInboxHtml(DATA([ROW({ status: "match", updatable: false })])), /Nothing needs a decision/);
  });

  test("closed accounts holding money are flagged; empty closed ones are quiet", () => {
    const data = DATA([], { unmatched: [{ account_key: "x", label: "Old brokerage", status: "closed_with_balance", monarch_value: 5000, closed_since: "2026-01-02" }],
      closed_accounts: [{ account_key: "y", label: "Old IRA", last_date: "2026-01-02" }] });
    assert.match(m.rcInboxHtml(data), /still show a balance[\s\S]*Old brokerage[\s\S]*mark done/);
    assert.doesNotMatch(m.rcInboxHtml(data), /Old IRA/);
    assert.match(m.rcClosedHtml(data), /Old IRA/);
  });

  test("the policy select lists the four policies and carries the account keys", () => {
    const html = m.rcPolicyHtml(rows[0]);
    assert.match(html, /<option value="ask" selected>Ask me/);
    for (const v of ["auto", "app", "ignore"]) assert.match(html, new RegExp(`value="${v}"`));
    assert.match(html, /data-keys="k1"/);
    assert.match(m.rcPolicyHtml(ROW({ monarch_accounts: [] })), /—/);
  });

  test("the banner counts automatic updates from the last 7 days and offers Undo all", () => {
    const now = Date.parse("2026-10-15T12:00:00Z");
    const log = [{ source: "auto", applied_at: "2026-10-14T04:00:00+00:00" }, { source: "auto", applied_at: "2026-09-01T04:00:00+00:00" },
      { source: "manual", applied_at: "2026-10-14T04:00:00+00:00" }, { source: "auto", applied_at: "2026-10-14T04:00:00+00:00", undone_at: "x" }];
    assert.match(m.rcAutoBannerHtml(log, now), /1 number was updated automatically[\s\S]*rcUndoAuto/);
    assert.equal(m.rcAutoBannerHtml([], now), "");
  });

  test("the page defaults to the inbox tab and the All mappings tab shows policy and the CSV import", () => {
    const state = (tab) => ({ data: DATA(rows), selected: new Set(), showMatched: false, tolerance: 1, log: [], tab, dismissed: new Set() });
    assert.match(m.rcBodyHtml(state("inbox")), /Needs a decision \(2\)/);
    assert.doesNotMatch(m.rcBodyHtml(state("inbox")), /Import mapping CSV/);
    const all = m.rcBodyHtml(state("all"));
    assert.match(all, /<th>Policy<\/th>/);
    assert.match(all, /Import mapping CSV/);
  });
});

describe("M4 review fix: parked accounts", () => {
  test("accounts matched to something the page cannot update are listed apart, not in the inbox", () => {
    const data = DATA([], { parked_accounts: [{ account_key: "a", label: "Annuity - Matt", ref: "SS, Pensions, & Annuities|Matt Single Annuity", policy: "app" }] });
    assert.match(m.rcParkedHtml(data), /Annuity - Matt[\s\S]*Matt Single Annuity/);
    assert.equal(m.rcParkedHtml(DATA([])), "");
    assert.match(m.rcInboxHtml(data), /Nothing needs a decision/);
  });
});
