/**
 * Unit tests for roth_ui.mjs pure functions.
 *
 * Phase B Batch 2: Strategy/Roth tests conversion
 * Converts source-text matching assertions to behavior-based testing.
 *
 * Run with: npm test
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  isValidRothObjectiveMode,
  isValidIrmaaGuardrailMode,
  calculateRothHeadroom,
  shouldSuggestRothConversion,
  formatRothLabels,
  getRothUiSectionVisibility,
  validateRothStrategy,
  estimateRothConversionBenefit,
} from "../../frontend/js/modules/roth_ui.mjs";

describe("isValidRothObjectiveMode", () => {
  test("accepts valid roth objective modes", () => {
    assert.equal(isValidRothObjectiveMode("BALANCED"), true);
    assert.equal(isValidRothObjectiveMode("TAX_MINIMIZED"), true);
    assert.equal(isValidRothObjectiveMode("LEGACY_TARGETED"), true);
    assert.equal(isValidRothObjectiveMode("ROTH_FOCUSED"), true);
  });

  test("rejects invalid modes", () => {
    assert.equal(isValidRothObjectiveMode("INVALID"), false);
    assert.equal(isValidRothObjectiveMode("UNKNOWN"), false);
    assert.equal(isValidRothObjectiveMode(""), false);
    assert.equal(isValidRothObjectiveMode(null), false);
  });

  test("case-insensitive validation", () => {
    assert.equal(isValidRothObjectiveMode("balanced"), true);
    assert.equal(isValidRothObjectiveMode("Tax_Minimized"), true);
  });
});

describe("isValidIrmaaGuardrailMode", () => {
  test("accepts valid IRMAA guardrail modes", () => {
    assert.equal(isValidIrmaaGuardrailMode("NONE"), true);
    assert.equal(isValidIrmaaGuardrailMode("WARN"), true);
    assert.equal(isValidIrmaaGuardrailMode("PREVENT"), true);
  });

  test("rejects invalid modes", () => {
    assert.equal(isValidIrmaaGuardrailMode("UNKNOWN"), false);
    assert.equal(isValidIrmaaGuardrailMode(""), false);
  });
});

describe("calculateRothHeadroom", () => {
  test("calculates available roth conversion space", () => {
    // $1M total, $300K roth, max 50% → $200K headroom
    assert.equal(calculateRothHeadroom(1000000, 300000, 0.5), 200000);
  });

  test("returns zero when roth at limit", () => {
    // $1M total, $500K roth, max 50% → $0 headroom
    assert.equal(calculateRothHeadroom(1000000, 500000, 0.5), 0);
  });

  test("returns zero when roth exceeds limit", () => {
    // $1M total, $600K roth, max 50% → $0 headroom (can't go negative)
    assert.equal(calculateRothHeadroom(1000000, 600000, 0.5), 0);
  });

  test("uses default max roth percentage if not specified", () => {
    // Default 50%: $1M total, $400K roth → $100K headroom
    assert.equal(calculateRothHeadroom(1000000, 400000), 100000);
  });

  test("returns zero for invalid inputs", () => {
    assert.equal(calculateRothHeadroom(null, 100000), 0);
    assert.equal(calculateRothHeadroom(NaN, 100000), 0);
    assert.equal(calculateRothHeadroom(1000000, undefined), 0);
  });

  test("respects custom max percentage", () => {
    // $1M total, $300K roth, max 30% → $0 headroom
    assert.equal(calculateRothHeadroom(1000000, 300000, 0.3), 0);
    // $1M total, $200K roth, max 30% → $100K headroom
    assert.equal(calculateRothHeadroom(1000000, 200000, 0.3), 100000);
  });
});

describe("shouldSuggestRothConversion", () => {
  test("suggests conversion when score positive and headroom available", () => {
    const metrics = {
      score: 0.15,
      available_headroom: 50000,
    };
    assert.equal(shouldSuggestRothConversion(metrics), true);
  });

  test("does not suggest when score is negative", () => {
    const metrics = {
      score: -0.10,
      available_headroom: 50000,
    };
    assert.equal(shouldSuggestRothConversion(metrics), false);
  });

  test("does not suggest when headroom is zero", () => {
    const metrics = {
      score: 0.15,
      available_headroom: 0,
    };
    assert.equal(shouldSuggestRothConversion(metrics), false);
  });

  test("handles missing or invalid metrics", () => {
    assert.equal(shouldSuggestRothConversion(null), false);
    assert.equal(shouldSuggestRothConversion(undefined), false);
    assert.equal(shouldSuggestRothConversion({}), false);
  });
});

describe("formatRothLabels", () => {
  test("converts snake_case keys to Title Case", () => {
    const labels = {
      roth_objective_mode: "BALANCED",
      future_tax_rate_stress_pct: "10%",
    };
    const formatted = formatRothLabels(labels);

    assert.equal(formatted.roth_objective_mode, "Roth Objective Mode");
    assert.equal(formatted.future_tax_rate_stress_pct, "Future Tax Rate Stress Pct");
  });

  test("handles empty or invalid input", () => {
    assert.deepEqual(formatRothLabels(null), {});
    assert.deepEqual(formatRothLabels(undefined), {});
    assert.deepEqual(formatRothLabels({}), {});
  });
});

describe("getRothUiSectionVisibility", () => {
  test("shows basic section when objective mode present", () => {
    const config = { roth_objective_mode: "BALANCED" };
    const visibility = getRothUiSectionVisibility(config);
    assert.equal(visibility.basic, true);
    assert.equal(visibility.advanced, false);
    assert.equal(visibility.legacy, false);
  });

  test("shows advanced section when optimization weights present", () => {
    const config = {
      roth_optimize_terminal_tax_rate: 0.24,
      roth_optimize_terminal_weight: 0.6,
    };
    const visibility = getRothUiSectionVisibility(config);
    assert.equal(visibility.advanced, true);
    assert.equal(visibility.basic, false);
  });

  test("shows legacy section when legacy objective mode present", () => {
    const config = { roth_legacy_objective_mode: "BALANCED" };
    const visibility = getRothUiSectionVisibility(config);
    assert.equal(visibility.legacy, true);
  });

  test("shows IRMAA section when guardrail mode present", () => {
    const config = { irmaa_guardrail_mode: "WARN" };
    const visibility = getRothUiSectionVisibility(config);
    assert.equal(visibility.irmaa, true);
  });

  test("all sections hidden when config is empty", () => {
    const visibility = getRothUiSectionVisibility({});
    assert.equal(visibility.basic, false);
    assert.equal(visibility.advanced, false);
    assert.equal(visibility.legacy, false);
    assert.equal(visibility.irmaa, false);
  });

  test("handles invalid config", () => {
    const visibility = getRothUiSectionVisibility(null);
    assert.equal(visibility.basic, false);
  });
});

describe("validateRothStrategy", () => {
  test("accepts valid strategy", () => {
    const strategy = {
      roth_objective_mode: "BALANCED",
      roth_optimize_terminal_weight: 0.6,
      roth_optimize_tax_weight: 0.4,
      future_tax_rate_stress_pct: 0.1,
      heir_ordinary_tax_rate_assumption: 0.32,
    };
    const result = validateRothStrategy(strategy);
    assert.equal(result.valid, true);
    assert.equal(result.errors.length, 0);
  });

  test("rejects invalid objective mode", () => {
    const strategy = { roth_objective_mode: "UNKNOWN_MODE" };
    const result = validateRothStrategy(strategy);
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("objective mode")));
  });

  test("rejects weights not summing to ~1.0", () => {
    const strategy = {
      roth_optimize_terminal_weight: 0.3,
      roth_optimize_tax_weight: 0.3,
      // Sums to 0.6, not ~1.0
    };
    const result = validateRothStrategy(strategy);
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("weights sum")));
  });

  test("rejects percentages outside 0-1 range", () => {
    const strategy = { future_tax_rate_stress_pct: 1.5 };
    const result = validateRothStrategy(strategy);
    assert.equal(result.valid, false);
  });

  test("rejects invalid IRMAA guardrail mode", () => {
    const strategy = { irmaa_guardrail_mode: "UNKNOWN" };
    const result = validateRothStrategy(strategy);
    assert.equal(result.valid, false);
  });

  test("handles empty strategy", () => {
    const result = validateRothStrategy({});
    assert.equal(result.valid, true);
  });

  test("handles invalid strategy object", () => {
    const result = validateRothStrategy(null);
    assert.equal(result.valid, false);
  });
});

describe("estimateRothConversionBenefit", () => {
  test("returns positive benefit when future tax rate > current", () => {
    const benefit = estimateRothConversionBenefit(
      { pretax: 600000, roth: 400000 },
      { current_rate: 0.24, future_rate: 0.35 }
    );
    assert.ok(benefit > 0);
    assert.ok(benefit <= 1);
  });

  test("returns zero benefit when tax rates equal", () => {
    const benefit = estimateRothConversionBenefit(
      {},
      { current_rate: 0.24, future_rate: 0.24 }
    );
    assert.equal(benefit, 0);
  });

  test("returns zero benefit when future tax < current", () => {
    const benefit = estimateRothConversionBenefit(
      {},
      { current_rate: 0.32, future_rate: 0.24 }
    );
    assert.equal(benefit, 0);
  });

  test("normalizes benefit to 0-1 range", () => {
    // 20% spread = max benefit (1.0)
    const maxBenefit = estimateRothConversionBenefit(
      {},
      { current_rate: 0.12, future_rate: 0.32 }
    );
    assert.equal(maxBenefit, 1);

    // 10% spread = half benefit (0.5)
    const halfBenefit = estimateRothConversionBenefit(
      {},
      { current_rate: 0.22, future_rate: 0.32 }
    );
    assert.equal(halfBenefit, 0.5);
  });

  test("handles missing input", () => {
    assert.equal(estimateRothConversionBenefit(null, {}), 0);
    assert.equal(estimateRothConversionBenefit({}, null), 0);
  });
});
