/**
 * Unit tests for tax_helpers.mjs pure functions.
 *
 * Phase B Batch 3: Income/Taxes tests conversion
 * Converts source-text matching assertions to behavior-based testing.
 *
 * Run with: npm test
 */

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  estimateMarginalTaxRate,
  calculateIrmaaAdjustment,
  calculateSocialSecurityTaxablePercent,
  validateIncomeStream,
  calculateEffectiveTaxRate,
  estimateTaxImpactOfIncomeChange,
  triggersMedicareSurcharge,
  formatTaxAmount,
  calculateWithdrawalSequencingTax,
} from "../../frontend/js/modules/tax_helpers.mjs";

describe("estimateMarginalTaxRate", () => {
  test("returns 10% for income in lowest bracket (MFJ)", () => {
    // 2025 MFJ: 10% up to $23,500
    assert.equal(estimateMarginalTaxRate(10000, 2025, true), 0.1);
    assert.equal(estimateMarginalTaxRate(23500, 2025, true), 0.1);
  });

  test("returns 12% for income in second bracket (MFJ)", () => {
    // 2025 MFJ: 12% from $23,501 to $95,375
    assert.equal(estimateMarginalTaxRate(50000, 2025, true), 0.12);
    assert.equal(estimateMarginalTaxRate(95375, 2025, true), 0.12);
  });

  test("returns correct rate for high income", () => {
    // 2025 MFJ: 24% up to $231,250; 32% from $231,251-$578,125; 35% from $578,126-$696,000; 37% over $696,000
    assert.equal(estimateMarginalTaxRate(231250, 2025, true), 0.24);
    assert.equal(estimateMarginalTaxRate(250000, 2025, true), 0.32);
    assert.equal(estimateMarginalTaxRate(600000, 2025, true), 0.35);
    assert.equal(estimateMarginalTaxRate(750000, 2025, true), 0.37);
  });

  test("returns lower rates for single filers", () => {
    // Single brackets are tighter
    const mfjRate = estimateMarginalTaxRate(100000, 2025, true);
    const singleRate = estimateMarginalTaxRate(100000, 2025, false);
    assert.ok(singleRate >= mfjRate);
  });

  test("returns 0% for zero or negative income", () => {
    assert.equal(estimateMarginalTaxRate(0), 0);
    assert.equal(estimateMarginalTaxRate(-10000), 0);
  });

  test("returns 0% for invalid input", () => {
    assert.equal(estimateMarginalTaxRate(NaN), 0);
    assert.equal(estimateMarginalTaxRate(null), 0);
  });
});

describe("calculateIrmaaAdjustment", () => {
  test("returns standard tier for income below threshold", () => {
    const result = calculateIrmaaAdjustment(90000);
    assert.equal(result.tier, "Standard");
    assert.equal(result.monthly_adjustment, 0);
    assert.equal(result.percentage_increase, 0);
  });

  test("returns Tier 2 for income above first IRMAA threshold", () => {
    const result = calculateIrmaaAdjustment(115000);
    assert.equal(result.tier, "Tier 2");
    assert.ok(result.monthly_adjustment > 0);
    assert.ok(result.percentage_increase > 0);
  });

  test("returns Tier 5 for very high income", () => {
    const result = calculateIrmaaAdjustment(250000);
    assert.equal(result.tier, "Tier 5");
    assert.equal(result.monthly_adjustment, 385);
  });

  test("returns standard for zero or negative MAGI", () => {
    assert.equal(calculateIrmaaAdjustment(0).monthly_adjustment, 0);
    assert.equal(calculateIrmaaAdjustment(-50000).monthly_adjustment, 0);
  });
});

describe("calculateSocialSecurityTaxablePercent", () => {
  test("returns 0% when income below combined threshold", () => {
    const percent = calculateSocialSecurityTaxablePercent(20000, 15000);
    assert.equal(percent, 0);
  });

  test("returns partial percent when income moderate", () => {
    // Income $30k, SS $15k → some SS taxable
    const percent = calculateSocialSecurityTaxablePercent(30000, 15000);
    assert.ok(percent > 0);
    assert.ok(percent < 0.85);
  });

  test("returns max 85% when income very high", () => {
    const percent = calculateSocialSecurityTaxablePercent(200000, 20000);
    assert.equal(percent, 0.85);
  });

  test("returns 0% for invalid inputs", () => {
    assert.equal(calculateSocialSecurityTaxablePercent(0, 15000), 0);
    assert.equal(calculateSocialSecurityTaxablePercent(NaN, 15000), 0);
    assert.equal(calculateSocialSecurityTaxablePercent(30000, 0), 0);
  });
});

describe("validateIncomeStream", () => {
  test("accepts valid income stream", () => {
    const stream = {
      start_age: 62,
      end_age: 90,
      amount: 30000,
    };
    const result = validateIncomeStream(stream);
    assert.equal(result.valid, true);
    assert.equal(result.errors.length, 0);
  });

  test("rejects invalid start age", () => {
    const stream = {
      start_age: -5,
      end_age: 90,
      amount: 30000,
    };
    const result = validateIncomeStream(stream);
    assert.equal(result.valid, false);
    assert.ok(result.errors.some((e) => e.includes("start age")));
  });

  test("rejects end age before start age", () => {
    const stream = {
      start_age: 70,
      end_age: 65,
      amount: 30000,
    };
    const result = validateIncomeStream(stream);
    assert.equal(result.valid, false);
  });

  test("rejects negative amount", () => {
    const stream = {
      start_age: 62,
      amount: -10000,
    };
    const result = validateIncomeStream(stream);
    assert.equal(result.valid, false);
  });

  test("warns on suspiciously large amount", () => {
    const stream = {
      start_age: 62,
      amount: 1000000,
    };
    const result = validateIncomeStream(stream);
    assert.ok(result.errors.some((e) => e.includes("unusually large")));
  });

  test("handles null stream", () => {
    const result = validateIncomeStream(null);
    assert.equal(result.valid, false);
  });
});

describe("calculateEffectiveTaxRate", () => {
  test("calculates effective rate correctly", () => {
    // $100k income, $24k taxes → 24% effective rate
    const rate = calculateEffectiveTaxRate(100000, 24000);
    assert.equal(rate, 0.24);
  });

  test("caps at 1.0 when taxes > income", () => {
    const rate = calculateEffectiveTaxRate(50000, 75000);
    assert.equal(rate, 1);
  });

  test("returns 0% for zero tax", () => {
    assert.equal(calculateEffectiveTaxRate(100000, 0), 0);
  });

  test("returns 0% for zero or negative income", () => {
    assert.equal(calculateEffectiveTaxRate(0, 10000), 0);
    assert.equal(calculateEffectiveTaxRate(-50000, 10000), 0);
  });

  test("returns 0% for invalid input", () => {
    assert.equal(calculateEffectiveTaxRate(NaN, 10000), 0);
  });
});

describe("estimateTaxImpactOfIncomeChange", () => {
  test("calculates tax impact of income increase", () => {
    // Increase income $50k at 24% marginal rate → $12k additional tax
    const impact = estimateTaxImpactOfIncomeChange(100000, 150000, 0.24);
    assert.equal(impact, 12000);
  });

  test("returns 0 for income decrease", () => {
    // Decreasing income → no additional tax
    const impact = estimateTaxImpactOfIncomeChange(150000, 100000, 0.24);
    assert.equal(impact, 0);
  });

  test("uses default marginal rate 24%", () => {
    const impact = estimateTaxImpactOfIncomeChange(100000, 110000);
    assert.equal(impact, 2400); // $10k * 24%
  });

  test("handles invalid inputs", () => {
    assert.equal(estimateTaxImpactOfIncomeChange(NaN, 150000), 0);
    assert.equal(estimateTaxImpactOfIncomeChange(100000, NaN), 0);
  });
});

describe("triggersMedicareSurcharge", () => {
  test("triggers for MFJ above $103,000", () => {
    assert.equal(triggersMedicareSurcharge(110000, "MFJ"), true);
    assert.equal(triggersMedicareSurcharge(103000, "MFJ"), false);
  });

  test("triggers for Single above $87,000", () => {
    assert.equal(triggersMedicareSurcharge(90000, "Single"), true);
    assert.equal(triggersMedicareSurcharge(87000, "Single"), false);
  });

  test("returns false for zero MAGI", () => {
    assert.equal(triggersMedicareSurcharge(0), false);
  });

  test("returns false for invalid MAGI", () => {
    assert.equal(triggersMedicareSurcharge(NaN), false);
  });
});

describe("formatTaxAmount", () => {
  test("formats currency with default no decimals", () => {
    assert.equal(formatTaxAmount(5000), "$5,000");
    assert.equal(formatTaxAmount(1000000), "$1,000,000");
  });

  test("formats with specified decimals", () => {
    assert.equal(formatTaxAmount(5000.5, 2), "$5,000.50");
    assert.equal(formatTaxAmount(1234.567, 2), "$1,234.57");
  });

  test("returns '—' for invalid input", () => {
    assert.equal(formatTaxAmount(NaN), "—");
    assert.equal(formatTaxAmount(null), "—");
  });
});

describe("calculateWithdrawalSequencingTax", () => {
  test("pretax withdrawals are fully taxable", () => {
    const result = calculateWithdrawalSequencingTax(
      { pretax: 1, roth: 0, taxable: 0 },
      100000,
      0.24
    );
    assert.equal(result.pretaxTax, 24000);
    assert.equal(result.rothTax, 0);
  });

  test("roth withdrawals have no tax", () => {
    const result = calculateWithdrawalSequencingTax(
      { pretax: 0, roth: 1, taxable: 0 },
      100000,
      0.24
    );
    assert.equal(result.rothTax, 0);
    assert.equal(result.pretaxTax, 0);
  });

  test("taxable withdrawals partially taxable (50% gains assumption)", () => {
    const result = calculateWithdrawalSequencingTax(
      { pretax: 0, roth: 0, taxable: 1 },
      100000,
      0.24
    );
    // 50% gains × 24% rate × $100k = $12k
    assert.equal(result.taxableTax, 12000);
  });

  test("combined allocation splits tax", () => {
    const result = calculateWithdrawalSequencingTax(
      { pretax: 0.5, roth: 0.3, taxable: 0.2 },
      100000,
      0.24
    );
    // Pretax: $50k × 24% = $12k
    // Roth: $30k × 0% = $0
    // Taxable: $20k × 50% × 24% = $2.4k
    assert.equal(result.pretaxTax, 12000);
    assert.equal(result.totalTax, 14400);
  });

  test("handles zero withdrawal", () => {
    const result = calculateWithdrawalSequencingTax(
      { pretax: 1, roth: 0, taxable: 0 },
      0,
      0.24
    );
    assert.equal(result.totalTax, 0);
  });
});
