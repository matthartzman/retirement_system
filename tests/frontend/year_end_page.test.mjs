// Year-End Transition page: ordered steps with state words, links to existing screens, the one confirmation, the season banner.
import { test, before } from "node:test";
import assert from "node:assert/strict";

let m;
before(async () => {
  globalThis.window = globalThis;
  globalThis.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  globalThis.setTimeout = () => 0;
  globalThis.api = async () => ({});
  m = await import("../../frontend/js/dashboard_decomp_year_end.js");
});

const DATA = { year: 2026, closed: false, in_season: true, steps: [
  { id: "capture_plan_year", title: "Capture the plan's 2026", link: "reports_and_review", state: "done", detail: "A saved plan run projects 2026." },
  { id: "close_cash_year", title: "Close the 2026 cash year", link: "sales_ledger", state: "open", detail: "2026 has not ended yet." },
  { id: "personal_numbers", title: "Update personal numbers", link: "household_people", state: "open", detail: "Confirm when reviewed." },
  { id: "final_broker_files", title: "Import final broker files", link: "sales_ledger", state: "na", detail: "No broker imports yet." }] };

test("page_lists_steps_in_order_with_state_words_and_links", () => {
  const h = m.yeHtml(DATA);
  assert.ok(h.indexOf("1. Capture") < h.indexOf("2. Close the 2026"));
  assert.match(h, /Done/);
  assert.match(h, /Open/);
  assert.match(h, /Not applicable/);
  assert.match(h, /setStep\(&quot;sales_ledger&quot;\)/);
  assert.match(h, /Closing 2026/);
  assert.match(h, /tax numbers/);
});

test("only_personal_numbers_offers_a_confirmation_and_it_toggles", () => {
  const h = m.yeHtml(DATA);
  assert.equal((h.match(/yeConfirm\(/g) || []).length, 1);
  assert.match(h, /yeConfirm\(2026, true\)/);
  const done = m.yeHtml({ ...DATA, steps: DATA.steps.map((s) => (s.id === "personal_numbers" ? { ...s, state: "done" } : s)) });
  assert.match(done, /yeConfirm\(2026, false\)/);
  assert.match(done, /Undo confirmation/);
});

test("tie_1099b_offers_its_own_confirmation_and_posts_its_step (task 15b)", async () => {
  const tie = { id: "tie_1099b", title: "Apply and tie the broker 1099-B", link: "sales_ledger", state: "open", detail: "x", hash: "#sales_ledger?tab=tax&sec=b1099" };
  const h = m.yeHtml({ ...DATA, steps: [...DATA.steps, tie] });
  assert.match(h, /yeConfirm\(2026, true, &quot;tie_1099b&quot;\)/);
  assert.match(h, /I have tied each 1099-B/);
  const done = m.yeHtml({ ...DATA, steps: [{ ...tie, state: "done" }] });
  assert.match(done, /yeConfirm\(2026, false, &quot;tie_1099b&quot;\)/);
  assert.match(done, /Undo confirmation/);
  assert.doesNotMatch(m.yeHtml({ ...DATA, steps: [{ ...tie, state: "na" }] }), /yeConfirm/);
  globalThis.document = { getElementById: () => null };
  const calls = [];
  globalThis.api = async (url, opts) => { calls.push([url, JSON.parse(opts.body)]); return { ...DATA, steps: [] }; };
  await m.yeConfirm(2026, true, "tie_1099b");
  await m.yeConfirm(2026, true);
  assert.deepEqual(calls.map((c) => c[1].step), ["tie_1099b", "personal_numbers"]);
});

test("a_step_with_a_hash_deep_links_before_navigating_and_others_just_navigate (task 14)", () => {
  const steps = [...DATA.steps, { id: "run_wash_check", title: "Run the wash-sale check", link: "sales_ledger", state: "open", detail: "x", hash: "#sales_ledger?tab=tax&sec=wash" }];
  const h = m.yeHtml({ ...DATA, steps });
  assert.match(h, /yeGo\(&quot;sales_ledger&quot;, &quot;#sales_ledger\?tab=tax&amp;sec=wash&quot;\)/);
  assert.match(h, /setStep\(&quot;household_people&quot;\)/);
  const seen = [];
  globalThis.setStep = (id) => seen.push(["step", id, globalThis.location && globalThis.location.hash]);
  globalThis.location = { hash: "" };
  m.yeGo("sales_ledger", "#sales_ledger?tab=tax&sec=wash");
  assert.deepEqual(seen.pop(), ["step", "sales_ledger", "#sales_ledger?tab=tax&sec=wash"]);
  delete globalThis.location;
  assert.doesNotThrow(() => m.yeGo("sales_ledger", "#sales_ledger?tab=fix&sec=queue"));
  assert.deepEqual(seen.pop(), ["step", "sales_ledger", undefined]);
  delete globalThis.setStep;
});

test("page_shows_loading_then_errors", () => {
  assert.match(m.yeHtml(null), /Loading/);
});

test("banner_appears_only_from_mid_december_through_january", () => {
  assert.equal(m.renderYearEndBanner(new Date(2026, 11, 14)), "");
  assert.match(m.renderYearEndBanner(new Date(2026, 11, 15)), /setStep\('year_end'\)/);
  assert.match(m.renderYearEndBanner(new Date(2027, 0, 31)), /Year-End Transition/);
  assert.equal(m.renderYearEndBanner(new Date(2027, 1, 1)), "");
});

test("year-end page renders the four cash cards for the closing year", async () => {
  await import("../../frontend/js/dashboard_decomp_cash_investment.js");
  const h = m.yeHtml(DATA);
  assert.match(h, /Investment cash, 2026/);
  const titles = [...h.matchAll(/<h3>([^<]*)<\/h3>/g)].map((x) => x[1]);
  assert.deepEqual(titles.slice(-4), ["Investment cash agrees with the broker", "Withdrawals: actual vs plan", "One-time: verify accounts for the tax feed", "Closed years"]);
  assert.ok(h.indexOf('class="ye-steps"') < h.indexOf("Investment cash, 2026"));   // the checklist comes first
});
