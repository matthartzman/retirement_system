// WP12.6: the Rental Properties page helpers (dashboard_decomp_rental_properties.js): value
// parsing and display, field-tier visibility, the draft cleaner, summary strip, warnings (dismissible,
// "Why?"), table and phone cards, the Convert my home panel (rent only, no suggestion), the off
// state ("Off · N rows entered"), the nav gate, and the detail tabs with Show advanced.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const w = sandbox.window;

const DATA = {
  success: true, enabled: true, count: 2, max_properties: 20,
  properties: [
    { name: "Duplex", kind: "standalone", purchase_price: 350000, monthly_rent: 2500, improvements: [], overrides: [] },
    { name: "Our house", kind: "converted_home", conversion_year: 2028, improvements: [], overrides: [] },
  ],
  table: [
    { name: "Duplex", kind: "standalone", value: 450000, annual_rent: 30000, operating_expenses: 9000, net_yield: 0.0467, sale_year: 2040 },
    { name: "Our house", kind: "converted_home", value: 612000, annual_rent: 38400, operating_expenses: 4000, net_yield: null, sale_year: null },
  ],
  warnings: [
    { id: "double_count:Duplex:duplex", kind: "double_count", level: "warn", title: "Possible double count.", text: "Matches by name.", property: "Duplex", action: "other_assets" },
    { id: "passive_limit:2029", kind: "passive_limit", level: "warn", title: "Loss limited by passive rule.", text: "2029: $9,800 suspended.", action: "why", detail: "The allowance shrinks over $100,000." },
    { id: "section_121:Our house", kind: "section_121", level: "bad", title: "Section 121 test fails.", text: "Warning only.", property: "Our house", action: "open_property" },
  ],
  summary: { year: 2027, net_cash_flow: 21350, taxable_rental_income: 6120, suspended_loss: 11800, equity: 412000, by_property: { Duplex: { accumulated_depreciation: 88400, suspended_loss: 0 } } },
  estimate: { available: true, label: "Estimate from your property entries, not from the last build", magi: 0, years: { first: 2026, last: 2030 } },
  home: { available: true, label: "Primary residence", value_today: 1000000, adjusted_basis: 500000, appreciation: 0.03, conversion_year: 2028, value_at_conversion: 1070000 },
  field_tiers: { property: { monthly_rent: "advanced", active_participation: "advanced", placed_in_service_year: "expert", property_tax_growth: "expert", prior_suspended_loss: "expert" } },
};

beforeEach(() => {
  sandbox.planModuleTaxonomy = () => ({ modules: { rental_property_income: { tier: "advanced", name: "Rental Properties" } } });
  sandbox.currentPlanTier = () => "advanced";
});

describe("values", () => {
  test("money and percent formatting", () => {
    assert.equal(sandbox.rentalMoney(21350.4), "$21,350");
    assert.equal(sandbox.rentalMoney(-9800), "-$9,800");
    assert.equal(sandbox.rentalPct(0.051), "5.1%");
    assert.equal(sandbox.rentalPct(null), "");
  });
  test("a percent is always typed as a percent", () => {
    assert.equal(sandbox.rentalParseInput("pct", "5"), 0.05);
    assert.equal(sandbox.rentalParseInput("pct", "5%"), 0.05);
    assert.equal(sandbox.rentalParseInput("pct", " 2.5 "), 0.025);
    assert.equal(sandbox.rentalParseInput("pct", "abc"), "abc"); // the server refuses it with its message
    assert.equal(sandbox.rentalDisplayValue("pct", 0.025), "2.5");
    assert.equal(sandbox.rentalParseInput("money", "$350,000"), "$350,000");
    assert.equal(sandbox.rentalParseInput("money", "  "), null);
    assert.equal(sandbox.rentalParseInput("bool", "no"), false);
  });
  test("converted-home depreciation basis: lesser of value and basis, land excluded (default 20%)", () => {
    assert.equal(sandbox.rentalConvertedBasis(612000, 502875, null), 502875 * 0.8);
    assert.equal(sandbox.rentalConvertedBasis(400000, 500000, 0.25), 300000);
  });
});

describe("field tiers", () => {
  test("Expert fields hide until Show advanced, unless the plan is Expert; Standard fields always show", () => {
    assert.equal(sandbox.rentalFieldVisible("advanced", "advanced", false), true);
    assert.equal(sandbox.rentalFieldVisible("advanced", "standard", false), true); // the feature's own tier
    assert.equal(sandbox.rentalFieldVisible("expert", "advanced", false), false);
    assert.equal(sandbox.rentalFieldVisible("expert", "advanced", true), true);
    assert.equal(sandbox.rentalFieldVisible("expert", "expert", false), true);
  });
});

describe("draft", () => {
  test("blanks dropped, converted-home keys removed, empty child rows dropped", () => {
    const out = sandbox.rentalCleanDraft({
      name: "X", kind: "converted_home", purchase_price: "5", sale_year: "2040", conversion_year: "2028", monthly_rent: "",
      improvements: [{ year: "", amount: "" }, { year: "2024", amount: "100", month: null }],
      overrides: [{ year: "" }, { year: "2030", gross_rent: "1", notes: "" }],
    });
    assert.deepEqual(JSON.parse(JSON.stringify(out)), { name: "X", kind: "converted_home", conversion_year: "2028", improvements: [{ year: "2024", amount: "100" }], overrides: [{ year: "2030", gross_rent: "1" }] });
  });
});

describe("list page", () => {
  test("summary strip: four cards, selectable year, labelled estimate, suspended loss highlighted", () => {
    const html = sandbox.rentalSummaryHtml(DATA, 128000);
    assert.equal((html.match(/review-card/g) || []).length, 4);
    assert.match(html, /\$21,350<\/b><span>Annual net cash flow \(2027\)/);
    assert.match(html, /review-card warn"><b>\$11,800/);
    assert.match(html, /Estimate from your property entries/);
    assert.match(html, /<option value="2027" selected>/);
    assert.match(html, /value="128000"/);
  });
  test("warnings: dismissible per session, Why? shows the detail, converted-home failure is a warning only", () => {
    const html = sandbox.rentalWarningsHtml(DATA.warnings, new Set(["double_count:Duplex:duplex"]), "passive_limit:2029", false);
    assert.doesNotMatch(html, /Possible double count/);
    assert.match(html, /The allowance shrinks over \$100,000\./);
    assert.match(html, /rp-warn bad/);
    assert.match(html, /Warning only\./);
    assert.match(html, /rpOpen\('Our house'\)/);
    const read = sandbox.rentalWarningsHtml(DATA.warnings, new Set(), "", true);
    assert.doesNotMatch(read, /Dismiss|rpOpen/);
    assert.equal(sandbox.rentalWarningsHtml([], new Set(), "", false), "");
  });
  test("double-count warning offers Review Other Assets", () => {
    assert.match(sandbox.rentalWarningsHtml(DATA.warnings, new Set(), "", false), /setStep\('assets_special'\)">Review Other Assets/);
  });
  test("table and phone cards carry the same rows and actions; read-only has none", () => {
    const html = sandbox.rentalTableHtml(DATA, false);
    assert.equal((html.match(/rpDuplicate\('Duplex'\)/g) || []).length, 2); // table row + card
    assert.match(html, /\$30,000\/yr/);
    assert.match(html, /4\.7%/);
    assert.match(html, /Converted home/);
    assert.match(html, /2 of 20 properties\. Net yield = \(rent - operating expenses\) \/ value\./);
    assert.doesNotMatch(sandbox.rentalTableHtml(DATA, true), /rpOpen|rpDuplicate|rpRemove/);
  });
});

describe("convert my home", () => {
  test("pre-filled from the plan's home; rent is asked, never suggested", () => {
    const html = sandbox.rentalConvertPanelHtml({ year: "2028", value: "1070000", prefill: 1070000, rent: "" }, DATA.home);
    assert.match(html, /Primary residence/);
    assert.match(html, /value="2028"/);
    assert.match(html, /value="1070000"/);
    assert.match(html, /\$400,000/); // min(1,070,000, 500,000) x 80%
    assert.match(html, /id="rpConvRent"[^>]*value=""/);
    assert.match(html, /Move to Schedule E/);
    assert.match(html, /Section 121 applies to this property only/);
    assert.doesNotMatch(html, /[Ss]uggested|0\.52/);
    assert.equal(sandbox.rentalConvertPanelHtml(null, DATA.home), "");
  });
});

describe("off state", () => {
  test("Off · N rows entered, engine ignores it, turn-on and preview; no data means no preview button", () => {
    sandbox.offRowsLabel = (n) => "Off · " + n + (n === 1 ? " row" : " rows") + " entered";
    sandbox.engineIgnoredWarning = () => "While Rental Properties is off, the projection ignores it. Your entries are kept.";
    const html = sandbox.rentalOffHtml({ ...DATA, enabled: false }, false);
    assert.match(html, /Rental Properties: Off · 2 rows entered/);
    assert.match(html, /Your 2 properties are kept but not used/);
    assert.match(html, /Turn on Rental Properties/);
    assert.match(html, /Preview what it would add/);
    assert.match(html, /Tier: Advanced\./);
    assert.doesNotMatch(html, /rp-table/);
    assert.match(sandbox.rentalOffHtml({ ...DATA, enabled: false }, true), /rp-table/);
    const none = sandbox.rentalOffHtml({ enabled: false, count: 0 }, false);
    assert.doesNotMatch(none, /Preview what it would add/);
    assert.match(none, /Nothing is entered yet/);
  });
});

describe("nav gate", () => {
  test("hidden while off with no data; kept (off state) while data is stored; shown when on", () => {
    sandbox.setRentalKeptCount(0);
    assert.equal(sandbox.stepGatedByOptionalModule("rental_properties", () => false), true);
    assert.equal(sandbox.stepGatedByOptionalModule("rental_properties", () => true), false);
    const off = () => false;
    sandbox.optionalFunctionEnabled = off; // not reached with a custom isOn; the default path reads the plan
    sandbox.setRentalKeptCount(3);
    assert.equal(sandbox.rentalKeptCount(), 3);
    assert.equal(sandbox.stepGatedByOptionalModule("rental_properties"), false);
    sandbox.setRentalKeptCount(0);
  });
});

describe("detail page", () => {
  const draft = () => ({ name: "Duplex", kind: "standalone", active_participation: true, purchase_price: 350000, land_share: 0.2, improvements: [{ year: 2024, amount: 14000 }], overrides: [] });
  test("Basics shows Standard fields, no Expert badge; tabs and Show advanced control present", () => {
    const html = sandbox.rentalDetailHtml(draft(), DATA);
    for (const t of ["Basics", "Income", "Expenses", "Financing", "Tax", "Sale", "Overrides"]) assert.match(html, new RegExp(">" + t + "</button>"));
    assert.match(html, /Show advanced/);
    assert.match(html, /Purchase price/);
    assert.match(html, /Showing Standard fields only\./);
  });
  test("converted home swaps in its own group and computes the depreciation basis", () => {
    const html = sandbox.rentalDetailHtml({ ...draft(), kind: "converted_home", value_at_conversion: 612000, adjusted_basis_at_conversion: 502875 }, DATA);
    assert.match(html, /Converted home only/);
    assert.match(html, /Linked home/);
    assert.match(html, /\$402,300/);
    assert.doesNotMatch(html, /Purchase price/);
  });
  test("Tax tab: active participation is Standard (default Yes); placed-in-service and improvements are Expert", () => {
    w.rpTabSet = undefined;
    sandbox.rpTabSet("tax");
    let html = sandbox.rentalDetailHtml(draft(), DATA);
    assert.match(html, /Active participation/);
    assert.match(html, /<option value="yes" selected>/);
    assert.doesNotMatch(html, /Placed in service|Capital improvements/);
    sandbox.rpToggleAdvanced();
    html = sandbox.rentalDetailHtml(draft(), DATA);
    assert.match(html, /Placed in service/);
    assert.match(html, /Capital improvements/);
    assert.match(html, /class="badge exp">Expert/);
    assert.match(html, /\$88,400/);
    sandbox.rpToggleAdvanced();
    sandbox.rpTabSet("basics");
  });
});
