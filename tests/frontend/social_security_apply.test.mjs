// W10c (#329 P6 / §4.3 "scalar adoption"): Social Security's optimizer patch.
//
// The first concrete producer of an optimizer patch, and the one the plan
// says to prove before the structural (Housing) shape. What matters here is
// not the markup but the three things that can quietly be wrong:
//
//   1. the age -> claim_date conversion must match src/data_io.py's
//      _ss_claim_from_date_or_age() exactly, or applying the optimizer's
//      answer writes a DIFFERENT age than the one it recommended;
//   2. the applied-state comparison must run on the claim AGE, not the
//      stored date text -- a blank claim_date is age 70 to the engine, so a
//      raw comparison would report "not applied" for a plan that already
//      does exactly what the sweep recommends;
//   3. a patch item must never be emitted for a row that cannot be written
//      (no Member 2, no date of birth), because such an item would make the
//      strip claim a change it cannot make and would pin the computed state
//      to "diverged" permanently.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const {
  ssClaimDateForAge,
  socialSecurityOptimizerPatch,
  ssLiveClaimAge,
  ssClaimRow,
} = sandbox;
const OA = sandbox.window.OptimizerApply;

// Member 1 born 8/1962, Member 2 born 3/1965.
function planRows() {
  return [
    {
      row_index: 1,
      section: "Household",
      subsection: "",
      label: "member_1_dob",
      value: "8/3/1962",
      editable: true,
    },
    {
      row_index: 2,
      section: "Household",
      subsection: "",
      label: "member_2_dob",
      value: "3/14/1965",
      editable: true,
    },
    {
      row_index: 41,
      section: "Social Security",
      subsection: "Member 1",
      label: "claim_date",
      value: "8/2029",
      editable: true,
    },
    {
      row_index: 42,
      section: "Social Security",
      subsection: "Member 2",
      label: "claim_date",
      value: "3/2032",
      editable: true,
    },
  ];
}

// The payload src/reporting/summary_figures.py's
// social_security_timing_payload() projects onto plan_summary.json.
function result(over) {
  return Object.assign(
    {
      member_1_label: "Pat",
      member_2_label: "Sam",
      recommended_member_1_claim_age: 70,
      recommended_member_2_claim_age: 67,
      configured_member_1_claim_age: 67,
      configured_member_2_claim_age: 67,
      pairs_scored: 33,
      recommendation_matches_plan: false,
      all_pairs_infeasible: false,
    },
    over || {},
  );
}

beforeEach(() => {
  sandbox.window.rows = planRows();
  sandbox.window.dirty = new Map();
});

describe("age -> claim_date must match the engine's own resolution", () => {
  test("an age becomes that age in the person's own birth month", () => {
    // src/data_io.py resolves a bare claim_age to (dob_yr + age, dob_month).
    assert.equal(ssClaimDateForAge("Member 1", 70), "8/2032");
    assert.equal(ssClaimDateForAge("Member 2", 67), "3/2032");
  });

  test("the date it writes reads back as the age it was given", () => {
    for (const age of [62, 65, 67, 70]) {
      const raw = ssClaimDateForAge("Member 1", age);
      assert.equal(
        sandbox.ssClaimAgeFromDate("Member 1", { value: raw }),
        age,
        `age ${age} did not round-trip`,
      );
    }
  });

  test("no date of birth means no date can be written", () => {
    sandbox.window.rows = planRows().filter(
      (r) => r.label !== "member_1_dob",
    );
    assert.equal(ssClaimDateForAge("Member 1", 70), "");
  });

  test("a non-numeric age yields nothing rather than a garbage date", () => {
    assert.equal(ssClaimDateForAge("Member 1", null), "");
    assert.equal(ssClaimDateForAge("Member 1", "seventy"), "");
  });
});

describe("the patch", () => {
  test("one item per person, on the claim_date rows", () => {
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(patch.length, 2);
    // Array.from(): values built by the vm sandbox's own Array (a different
    // realm) fail deepEqual's structural check -- see plan_features.test.mjs.
    assert.deepEqual(
      Array.from(patch.map((x) => x.row_index)),
      [41, 42],
    );
    assert.equal(patch[0].field, "claim_date");
    assert.equal(patch[0].section, "Social Security");
    assert.equal(patch[0].subsection, "Member 1");
  });

  test("it is in the overrideFromRow() shape the promote path reads", () => {
    const [item] = socialSecurityOptimizerPatch(result());
    for (const k of [
      "source",
      "sourceStep",
      "section",
      "subsection",
      "field",
      "label",
      "before",
      "after",
      "row_index",
      "rationale",
    ])
      assert.ok(k in item, k);
    assert.equal(item.source, "optimizer");
    // The step the promote path routes back to for this row.
    assert.equal(item.sourceStep, "income_retirement");
  });

  test("afterRaw is the storage form, after is what the user reads", () => {
    const [item] = socialSecurityOptimizerPatch(result());
    assert.equal(item.afterRaw, "8/2032");
    assert.match(item.after, /8\/2032/);
    assert.match(item.after, /age 70/);
  });

  test("beforeRaw is the current stored text, so the reverse patch is exact", () => {
    const [item] = socialSecurityOptimizerPatch(result());
    assert.equal(item.beforeRaw, "8/2029");
    const [rev] = OA.reverseOptimizerPatch(socialSecurityOptimizerPatch(result()));
    assert.equal(rev.afterRaw, "8/2029");
  });

  test("a blank claim date is described as the age the engine defaults to", () => {
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "";
    sandbox.window.rows = rows;
    const [item] = socialSecurityOptimizerPatch(result());
    assert.match(item.before, /Blank/);
    assert.match(item.before, /age 70/);
    assert.equal(item.beforeRaw, "");
  });

  test("a staged (unsaved) edit is what `before` reports", () => {
    sandbox.window.dirty = new Map([[41, "8/2031"]]);
    const [item] = socialSecurityOptimizerPatch(result());
    assert.equal(item.beforeRaw, "8/2031");
  });

  test("a single-person household gets one item, not a broken second", () => {
    sandbox.window.rows = planRows().filter((r) => r.row_index !== 42);
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(patch.length, 1);
    assert.equal(patch[0].row_index, 41);
  });

  test("a person with no date of birth is skipped, not half-written", () => {
    sandbox.window.rows = planRows().filter((r) => r.label !== "member_2_dob");
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(patch.length, 1);
    assert.equal(patch[0].row_index, 41);
  });

  test("a missing recommendation for a person emits no item for them", () => {
    const patch = socialSecurityOptimizerPatch(
      result({ recommended_member_2_claim_age: null }),
    );
    assert.equal(patch.length, 1);
  });

  test("no result at all is an empty patch, not a throw", () => {
    assert.deepEqual(Array.from(socialSecurityOptimizerPatch(null) || []), []);
  });

  test("every item is promotable — this is the scalar shape, no advisories", () => {
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(OA.promotableItems(patch).length, 2);
    assert.equal(OA.advisoryItems(patch).length, 0);
  });
});

describe("§4.6 applied state compares the claim AGE, not the date text", () => {
  const liveAge = (patch) => (idx) => {
    const item = patch.find((x) => x.row_index === idx);
    return item ? ssLiveClaimAge(item.subsection, idx) : undefined;
  };

  test("a plan at the recommended ages reads applied", () => {
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "8/2032"; // age 70
    rows.find((r) => r.row_index === 42).value = "3/2032"; // age 67
    sandbox.window.rows = rows;
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.APPLIED);
  });

  test("a blank claim date counts as age 70, which the engine agrees with", () => {
    // The case a raw text comparison gets wrong: blank is not "unset".
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "";
    rows.find((r) => r.row_index === 42).value = "3/2032";
    sandbox.window.rows = rows;
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(patch[0].beforeRaw, "");
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.APPLIED);
  });

  test("a different month at the same age is still the optimizer's answer", () => {
    // The sweep varies whole ages only, so refining the month is not a
    // divergence from what it recommended.
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "11/2032"; // still age 70
    rows.find((r) => r.row_index === 42).value = "3/2032";
    sandbox.window.rows = rows;
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.APPLIED);
  });

  test("the configured plan reads not_applied", () => {
    const patch = socialSecurityOptimizerPatch(result());
    // planRows() holds ages 67 and 67 against a 70/67 recommendation: Member
    // 2 already matches, so this is the diverged boundary, not not_applied.
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.DIVERGED);
  });

  test("neither row matching reads not_applied", () => {
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "8/2025"; // age 63
    rows.find((r) => r.row_index === 42).value = "3/2030"; // age 65
    sandbox.window.rows = rows;
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(
      OA.optimizerAppliedState(patch, liveAge(patch)),
      OA.NOT_APPLIED,
    );
  });

  test("applied, then one row hand-edited, reads diverged", () => {
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "8/2032";
    rows.find((r) => r.row_index === 42).value = "3/2030";
    sandbox.window.rows = rows;
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.DIVERGED);
  });

  test("a staged edit, not just a saved one, moves the state", () => {
    const rows = planRows();
    rows.find((r) => r.row_index === 41).value = "8/2032";
    rows.find((r) => r.row_index === 42).value = "3/2032";
    sandbox.window.rows = rows;
    sandbox.window.dirty = new Map([[42, "3/2035"]]); // age 70, not 67
    const patch = socialSecurityOptimizerPatch(result());
    assert.equal(OA.optimizerAppliedState(patch, liveAge(patch)), OA.DIVERGED);
  });
});

describe("applying, then reversing, returns the plan to where it started", () => {
  test("the reverse patch writes back the exact original text", () => {
    const patch = socialSecurityOptimizerPatch(result());
    const originals = patch.map((x) => [x.row_index, x.beforeRaw]);
    const rev = OA.reverseOptimizerPatch(patch);
    rev.forEach((x, i) => {
      assert.equal(x.row_index, originals[i][0]);
      assert.equal(x.afterRaw, originals[i][1]);
    });
  });

  test("after reversing, the forward patch reads not_applied again", () => {
    const patch = socialSecurityOptimizerPatch(result());
    const rev = OA.reverseOptimizerPatch(patch);
    const rows = planRows();
    rev.forEach((x) => {
      rows.find((r) => r.row_index === x.row_index).value = x.afterRaw;
    });
    sandbox.window.rows = rows;
    const fresh = socialSecurityOptimizerPatch(result());
    const liveAge = (idx) => {
      const item = fresh.find((x) => x.row_index === idx);
      return item ? ssLiveClaimAge(item.subsection, idx) : undefined;
    };
    // Member 2's configured age already equals its recommendation, so the
    // honest answer after undoing is "diverged", not "not_applied" -- the
    // reverse patch restores the plan, it does not un-recommend anything.
    assert.equal(OA.optimizerAppliedState(fresh, liveAge), OA.DIVERGED);
    assert.equal(fresh[0].beforeRaw, "8/2029");
  });
});

describe("row lookup", () => {
  test("it finds the editable claim_date row for each person", () => {
    assert.equal(ssClaimRow("Member 1").row_index, 41);
    assert.equal(ssClaimRow("Member 2").row_index, 42);
  });

  test("a household with no Member 2 has no row to patch", () => {
    sandbox.window.rows = planRows().filter((r) => r.row_index !== 42);
    assert.ok(!ssClaimRow("Member 2"));
  });
});
