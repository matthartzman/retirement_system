// Roth guardrail panel: ranking, binding badges, controls bound to setting
// rows, and the measured what-if row. Pure functions via the dashboard sandbox.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const g = () => ({
  years: [
    {
      year: 2027, amount: 50893, binding: "LTCG rate tier", secondary: "NIIT threshold",
      caps: [
        { id: "ltcg", name: "LTCG rate tier", cap: 50893 },
        { id: "niit", name: "NIIT threshold", cap: 192559 },
        { id: "bracket", name: "32% bracket", cap: 523602 },
        { id: "balance", name: "IRA balance", cap: 1796225 },
        { id: "pct", name: "Annual IRA percentage cap", cap: 1796225 },
      ],
    },
    { year: 2030, amount: 90000, caps: [{ id: "bracket", name: "32% bracket", cap: 90000 }, { id: "ltcg", name: "LTCG rate tier", cap: 300000 }] },
  ],
  whatif: {
    ltcg: { extra_converted: 458855, lifetime_tax_pv_change: -29958, terminal_wealth_pv_change: 27513, lcv_change: 27513 },
    niit: { extra_converted: 913302, lifetime_tax_pv_change: 576, terminal_wealth_pv_change: -58458, lcv_change: -58458 },
  },
  baseline: { lcv: 9310224 },
  settings: { switches: { irmaa: true, ltcg: true, niit: true } },
  options: { irmaa: { TIER_2: 274000 }, ltcg: { "0%": 98900, "15%": 613700 }, niit: 250000 },
});
const ctx = (over = {}) => ({
  year: 2027, order: [], manual: false,
  idx: (k) => ({ roth_ltcg_band: 7, roth_ltcg_headroom_usage_pct: 8, roth_ltcg_guardrail: 6 }[k] ?? null),
  val: (k) => ({ roth_ltcg_band: "auto", roth_ltcg_headroom_usage_pct: "95.00%" }[k] ?? ""),
  ...over,
});

test("ranks by dollars, lowest first, IRA balance excluded", () => {
  const { rgRankRows } = loadDashboardSandbox();
  const { rows } = rgRankRows(g(), 2027, [], false);
  assert.equal(rows.filter((r) => r.active).map((r) => r.id).join(","), "ltcg,niit,bracket,pct");
  assert.ok(!rows.some((r) => r.id === "balance"));
  assert.equal(rows[0].binding, "now");
  assert.equal(rows[1].binding, "next");
});

test("a guardrail with no cap that year drops to the bottom as Not this year", () => {
  const { rgRankRows } = loadDashboardSandbox();
  const { rows } = rgRankRows(g(), 2030, [], false);
  const niit = rows.find((r) => r.id === "niit");
  assert.equal(niit.active, false);
  assert.equal(rows[rows.length - 1].active, false);
});

test("manual order wins over dollars but badges still follow dollars", () => {
  const { rgRankRows } = loadDashboardSandbox();
  const { rows } = rgRankRows(g(), 2027, ["pct", "bracket", "niit", "ltcg"], true);
  assert.equal(rows[0].id, "pct");
  assert.equal(rows.find((r) => r.id === "ltcg").binding, "now");
});

test("what-if verdict uses the measured net lifetime value", () => {
  const { rgWhatIf } = loadDashboardSandbox();
  assert.equal(rgWhatIf(g(), "ltcg").verdict, "ok");
  assert.equal(rgWhatIf(g(), "niit").verdict, "keep");
  assert.equal(rgWhatIf(g(), "bracket"), null);
});

test("panel prints all four what-if numbers on one row and dropdown dollar values", () => {
  const { rothGuardrailPanelHtml } = loadDashboardSandbox();
  const html = rothGuardrailPanelHtml(g(), ctx());
  assert.match(html, /class="rg-whatif"/);
  for (const label of ["Extra converted", "Lifetime tax \\(PV\\)", "After-tax terminal wealth \\(PV\\)", "Net lifetime value"])
    assert.match(html, new RegExp(label));
  assert.match(html, /\+\$458,855/);
  assert.match(html, /0% band · income to \$98,900/);
  assert.match(html, /editValue\(7,this\.value,this\)/);
  assert.doesNotMatch(html, /Move up|Move down/);
});

test("no guardrail data renders nothing", () => {
  const { rothGuardrailPanelHtml } = loadDashboardSandbox();
  assert.equal(rothGuardrailPanelHtml(null, ctx()), "");
  assert.equal(rothGuardrailPanelHtml({ years: [] }, ctx()), "");
});
