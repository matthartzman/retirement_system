// WI-031 / QA-008: behavioural tests for the estate and insurance panel
// handlers in dashboard_decomp_estate_insurance.js.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const row = (label, value) => ({ label, value, effective_value: value });

describe("estate subsection classification", () => {
  test("fixed estate blocks are not state-like; state names and trust accounts handled", () => {
    for (const s of ["Federal", "gifting", "Trust_Structure", "qtip_trust", "sn_trust"])
      assert.equal(sandbox.stateLikeEstateSubsection(s), false, s);
    assert.equal(sandbox.stateLikeEstateSubsection("trust_account_1"), false);
    assert.equal(sandbox.stateLikeEstateSubsection("Illinois"), true);
  });
});

describe("inferPolicyType", () => {
  test("maps subsection names and explicit type rows to policy types", () => {
    assert.equal(sandbox.inferPolicyType("umbrella_1", []), "Umbrella");
    assert.equal(sandbox.inferPolicyType("disability_a", []), "Disability");
    assert.equal(sandbox.inferPolicyType("life_term", []), "Life");
    assert.equal(sandbox.inferPolicyType("x", [row("policy_type", "Long-Term Care")]), "Long-Term Care");
  });
});

describe("add/delete insurance policy", () => {
  let calls, messages;
  beforeEach(() => {
    calls = [];
    messages = [];
    sandbox.saveBeforeStructuralChange = async () => true;
    sandbox.loadAll = async () => {};
    sandbox.renderMain = () => {};
    sandbox.showMessage = (m, k) => messages.push([m, k]);
    sandbox.showInAppConfirm = async () => true;
    sandbox.illustrationPlanYears = () => [2030, 2031];
    sandbox.api = async (url, opts) => {
      calls.push({ url, body: opts && JSON.parse(opts.body) });
      return { message: "ok", section: "life_2" };
    };
  });

  test("adding a Life policy posts the chosen type and seeds illustration years", async () => {
    sandbox.setNewInsurancePolicyType("Life");
    await sandbox.addInsurancePolicy();
    assert.equal(calls[0].url, "/api/insurance-policy/add");
    assert.equal(calls[0].body.policy_type, "Life");
    assert.equal(calls[1].url, "/api/life-illustration/seed");
    assert.deepEqual(calls[1].body, { policy_key: "life_2", years: [2030, 2031] });
  });

  test("adding a non-Life policy does not seed illustrations", async () => {
    sandbox.setNewInsurancePolicyType("Umbrella");
    await sandbox.addInsurancePolicy();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].body.policy_type, "Umbrella");
  });

  test("add is aborted when the pre-change save is refused", async () => {
    sandbox.saveBeforeStructuralChange = async () => false;
    await sandbox.addInsurancePolicy();
    assert.equal(calls.length, 0);
  });

  test("delete posts the subsection only after confirmation", async () => {
    await sandbox.deleteInsurancePolicy(null, "umbrella_1");
    assert.deepEqual(calls[0], { url: "/api/insurance-policy/delete", body: { subsection: "umbrella_1" } });
    calls.length = 0;
    sandbox.showInAppConfirm = async () => false;
    await sandbox.deleteInsurancePolicy(null, "umbrella_1");
    assert.equal(calls.length, 0);
  });
});
