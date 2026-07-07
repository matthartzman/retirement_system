/**
 * Roth Conversion UI Helper Functions
 *
 * Pure functions for Roth conversion strategy rendering and validation.
 * Extracted from dashboard.js for testability and reusability.
 */

/**
 * Validate roth objective mode value
 * @param {string} mode - The roth objective mode (e.g., "BALANCED", "TAX_MINIMIZED")
 * @returns {boolean} True if valid mode
 */
export function isValidRothObjectiveMode(mode) {
  if (!mode) return false;
  const validModes = [
    "BALANCED",
    "TAX_MINIMIZED",
    "LEGACY_TARGETED",
    "ROTH_FOCUSED",
  ];
  return validModes.includes(String(mode).trim().toUpperCase());
}

/**
 * Validate IRMAA guardrail mode
 * @param {string} mode - The IRMAA guardrail mode
 * @returns {boolean} True if valid mode
 */
export function isValidIrmaaGuardrailMode(mode) {
  const validModes = ["NONE", "WARN", "PREVENT"];
  return validModes.includes(String(mode).toUpperCase());
}

/**
 * Calculate roth conversion headroom
 * @param {number} totalNw - Total net worth
 * @param {number} rothNw - Current Roth net worth
 * @param {number} maxRothPct - Maximum Roth percentage (0-1)
 * @returns {number} Available headroom in dollars
 */
export function calculateRothHeadroom(totalNw, rothNw, maxRothPct = 0.5) {
  if (!Number.isFinite(totalNw) || !Number.isFinite(rothNw)) {
    return 0;
  }
  const maxRoth = totalNw * maxRothPct;
  return Math.max(0, maxRoth - rothNw);
}

/**
 * Determine if Roth conversion should be suggested
 * @param {object} metrics - Roth strategy metrics object
 * @returns {boolean} True if conversion is recommended
 */
export function shouldSuggestRothConversion(metrics) {
  if (!metrics || typeof metrics !== "object") {
    return false;
  }

  // Suggest conversion if score is positive and headroom available
  const score = metrics.score || 0;
  const headroom = metrics.available_headroom || 0;

  return score > 0 && headroom > 0;
}

/**
 * Format roth labels for display
 * @param {object} labels - Object with roth label keys
 * @returns {object} Formatted labels ready for UI display
 */
export function formatRothLabels(labels) {
  if (!labels || typeof labels !== "object") {
    return {};
  }

  const formatted = {};
  for (const [key, value] of Object.entries(labels)) {
    // Convert snake_case to Title Case
    const titleCased = String(key)
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");

    formatted[key] = titleCased;
  }

  return formatted;
}

/**
 * Get roth UI section visibility based on plan config
 * @param {object} config - Plan configuration object
 * @returns {object} Visibility flags for roth UI sections
 */
export function getRothUiSectionVisibility(config) {
  if (!config || typeof config !== "object") {
    return {
      basic: false,
      advanced: false,
      legacy: false,
      irmaa: false,
    };
  }

  return {
    basic: Boolean(
      config.roth_objective_mode || config.roth_headroom_usage_pct
    ),
    advanced: Boolean(
      config.roth_optimize_terminal_tax_rate ||
        config.roth_optimize_terminal_weight
    ),
    legacy: Boolean(config.roth_legacy_objective_mode),
    irmaa: Boolean(
      config.irmaa_guardrail_mode || config.roth_irmaa_headroom_usage_pct
    ),
  };
}

/**
 * Validate roth strategy consistency
 * @param {object} strategy - Roth strategy object with mode, weights, rates
 * @returns {object} Validation result { valid: boolean, errors: string[] }
 */
export function validateRothStrategy(strategy) {
  const errors = [];

  if (!strategy || typeof strategy !== "object") {
    return { valid: false, errors: ["Invalid strategy object"] };
  }

  // Validate objective mode
  const mode = strategy.roth_objective_mode || strategy.objective_mode;
  if (mode && !isValidRothObjectiveMode(mode)) {
    errors.push(`Invalid roth objective mode: ${mode}`);
  }

  // Validate weights sum approximately to 1.0 (if provided)
  if (
    strategy.roth_optimize_terminal_weight ||
    strategy.roth_optimize_tax_weight
  ) {
    const tw = Number(strategy.roth_optimize_terminal_weight) || 0;
    const taxw = Number(strategy.roth_optimize_tax_weight) || 0;
    const total = tw + taxw;

    if (total > 0 && (total < 0.9 || total > 1.1)) {
      errors.push(
        `Roth weights sum to ${total.toFixed(2)}, expected ~1.0`
      );
    }
  }

  // Validate percentages are 0-1
  const percentFields = [
    "future_tax_rate_stress_pct",
    "future_tax_risk_weight",
    "inheritance_tax_burden_weight",
    "heir_ordinary_tax_rate_assumption",
    "pre_tax_bequest_penalty_pct",
    "bequest_preference_bonus_pct",
    "survivor_tax_risk_weight",
    "roth_optimize_terminal_tax_rate",
  ];

  for (const field of percentFields) {
    const value = Number(strategy[field]);
    if (!Number.isNaN(value) && (value < 0 || value > 1)) {
      errors.push(`${field} should be 0-1, got ${value}`);
    }
  }

  // Validate IRMAA guardrail mode
  if (strategy.irmaa_guardrail_mode && !isValidIrmaaGuardrailMode(strategy.irmaa_guardrail_mode)) {
    errors.push(`Invalid IRMAA guardrail mode: ${strategy.irmaa_guardrail_mode}`);
  }

  return {
    valid: errors.length === 0,
    errors: errors,
  };
}

/**
 * Estimate roth conversion benefit
 * @param {object} currentAllocation - Current pre-tax/roth allocation
 * @param {object} projectedTaxRate - Projected tax rates (current, future)
 * @returns {number} Estimated tax savings from conversion (0-1 scale)
 */
export function estimateRothConversionBenefit(currentAllocation, projectedTaxRate) {
  if (!currentAllocation || !projectedTaxRate) {
    return 0;
  }

  const currentTax = Number(projectedTaxRate.current_rate) || 0.24;
  const futureTax = Number(projectedTaxRate.future_rate) || 0.32;
  const taxSpread = futureTax - currentTax;

  // Benefit is positive if future tax rate > current rate
  // Normalized to 0-1 range (assume 0-20% spread is realistic)
  if (taxSpread <= 0) return 0;
  return Math.min(1, taxSpread / 0.2);
}
