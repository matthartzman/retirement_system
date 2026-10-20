// WI-009 (FIN-002): the Monte Carlo KPI label per Roth policy.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sb = loadDashboardSandbox();
const base = { mc_approximation_status: "TOLERANCE_BOUNDED", mc_parity_tolerance_pp: 5 };
import vm from "node:vm";
const demonstrated = vm.runInContext("MC_TOLERANCE_DEMONSTRATED_POLICIES", sb);

describe("Monte Carlo headline disclosure", () => {
  test("headline states its own success definition", () => {
    const d = sb.mcSuccessDisclosure(base, "none");
    assert.match(d.label, /funded as asked/);
    assert.match(d.title, /Roth as a last resort/);
  });

  for (const policy of ["none", "fill_to_bracket", "optimize_terminal_tax"]) {
    test(`label for ${policy} matches its measured status`, () => {
      const d = sb.mcSuccessDisclosure(base, policy);
      if (demonstrated.includes(policy)) {
        assert.match(d.label, /±5pp/);
        assert.doesNotMatch(d.label, /directional/);
      } else {
        assert.match(d.label, /directional/);
        assert.doesNotMatch(d.label, /±/);
      }
    });
  }

  test("unmeasured policies never carry a tolerance label", () => {
    for (const policy of ["fixed_dollar", "fill_to_irmaa", "made_up"]) {
      assert.doesNotMatch(sb.mcSuccessDisclosure(base, policy).label, /±/);
    }
  });

  test("approximate status without tolerance is directional; EXACT has no suffix", () => {
    assert.match(sb.mcSuccessDisclosure({ mc_approximation_status: "APPROXIMATE" }, "none").label, /directional/);
    const e = sb.mcSuccessDisclosure({ mc_approximation_status: "EXACT" }, "none");
    assert.doesNotMatch(e.label, /directional|±/);
  });

  test("secondary within-tier figure is gone from the tile", () => {
    assert.doesNotMatch(sb.planKpiMetricsHtml.toString(), /without using Roth for extras/);
  });
});
