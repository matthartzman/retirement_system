// The Social Security claim_age input was replaced by claim_date (MM/YYYY),
// with claim age calculated and displayed instead of entered directly --
// see src/data_io.py's _ss_claim_from_date_or_age() for the backend half of
// this. These test the pure MM/YYYY <-> <input type="month"> conversion
// helpers and the calculated-age derivation.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const {
  claimDateToMonthInputValue,
  monthInputValueToClaimDate,
  ssClaimAgeFromDate,
  ssTrueAgeFromDate,
} = sandbox;

describe("claim date <-> <input type=month> conversion", () => {
  test("M/YYYY converts to the native month input's YYYY-MM", () => {
    assert.equal(claimDateToMonthInputValue("6/2029"), "2029-06");
  });

  test("MM/YYYY converts to YYYY-MM", () => {
    assert.equal(claimDateToMonthInputValue("06/2029"), "2029-06");
  });

  test("blank stays blank", () => {
    assert.equal(claimDateToMonthInputValue(""), "");
  });

  test("the native month input's YYYY-MM converts back to M/YYYY", () => {
    assert.equal(monthInputValueToClaimDate("2029-06"), "6/2029");
  });

  test("round-trips without drift", () => {
    const stored = "8/2032";
    const inputValue = claimDateToMonthInputValue(stored);
    assert.equal(monthInputValueToClaimDate(inputValue), stored);
  });
});

describe("ssClaimAgeFromDate", () => {
  test("derives the calculated claim age from claim_date and DOB", () => {
    // rows is `let`, not `var` -- only sandbox.window.rows = ... actually
    // reaches the module-scope `rows` findEditableRow reads (see
    // housing_cost_reestimate.test.mjs for the same pattern).
    sandbox.window.rows = [
      { section: "Household", subsection: "", label: "member_1_dob", value: "8/3/1962" },
    ];
    const claimDateRow = { value: "1/2028" };
    // 2028 claim year - 1962 birth year = 66
    assert.equal(ssClaimAgeFromDate("Member 1", claimDateRow), 66);
  });

  test("defaults to 70 when claim_date is blank", () => {
    assert.equal(ssClaimAgeFromDate("Member 1", { value: "" }), 70);
  });

  test("defaults to 70 when there is no claim_date row at all", () => {
    assert.equal(ssClaimAgeFromDate("Member 1", null), 70);
  });
});

describe("ssTrueAgeFromDate", () => {
  // Ticket 317: a January claim shown as "Age 66" for a person who doesn't
  // turn 66 until May is wrong -- the badge under the claim-date input must
  // account for birth month, not just claim_year - dob_year like the
  // SSA-table-lookup claim_age does.
  test("claim month before birth month: not yet had the birthday this year", () => {
    sandbox.window.rows = [
      { section: "Household", subsection: "", label: "member_1_dob", value: "5/12/1961" },
    ];
    // Claims 1/2027: birthday hasn't happened yet in 2027, so still 65, not 66.
    assert.equal(ssTrueAgeFromDate("Member 1", { value: "1/2027" }), 65);
  });

  test("claim month on birth month: birthday has happened", () => {
    sandbox.window.rows = [
      { section: "Household", subsection: "", label: "member_1_dob", value: "5/12/1961" },
    ];
    assert.equal(ssTrueAgeFromDate("Member 1", { value: "5/2027" }), 66);
  });

  test("claim month after birth month: birthday already passed this year", () => {
    sandbox.window.rows = [
      { section: "Household", subsection: "", label: "member_1_dob", value: "5/12/1961" },
    ];
    assert.equal(ssTrueAgeFromDate("Member 1", { value: "9/2027" }), 66);
  });

  test("defaults to 70 when claim_date is blank", () => {
    assert.equal(ssTrueAgeFromDate("Member 1", { value: "" }), 70);
  });
});
